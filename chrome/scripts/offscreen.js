
var constraints;
var media;
var videoElement;
var canvas;
var ctx;
var viewing = false;
var audioContext;
var audioSource;
var audioAnalyzer;
var audioDataArray;
var isAudioConnected = false;


chrome.runtime.onMessage.addListener(function (message) {
    if (message.target == 'offscreen') {
        if (message.action == 'start-viewing') {
            constraints = message.constraints;
            startViewing(constraints);
        } else if (message.action == 'start-listening') {
            constraints = message.constraints;
            startListening(constraints);
        } else if (message.action == 'stop-viewing') {
            stopViewing();
        } else if (message.action == 'resume-viewing') {
            //does not currently work, need to close and reopen offscreen in order to pause and resume viewing tab
            startViewing(constraints);
        } else if (message.action == 'disconnect-tab-audio') {
            if (isAudioConnected) {
                audioSource.disconnect(audioContext.destination);
                isAudioConnected = false;
            }
        } else if (message.action == 'connect-tab-audio') {
            if (!isAudioConnected) {
                audioSource.connect(audioContext.destination);
                isAudioConnected = true;
            }
        } else if (message.action == 'close') {
            window.close();
        }
    }
});


async function startViewing(constraints) {

    if (!viewing) {

        media = await navigator.mediaDevices.getUserMedia(constraints);

        videoElement = document.createElement('video');
        videoElement.srcObject = media;
        videoElement.muted = true;
        videoElement.play();

        canvas = document.createElement('canvas');
        canvas.width = 1;
        canvas.height = 1;
        //canvas.width = 30; //debug-high
        //canvas.height = 30; //debug-high
        ctx = canvas.getContext('2d', { willReadFrequently: true });

        viewing = true;

    }

}


async function startListening(constraints) {

    if (!viewing) {

        media = await navigator.mediaDevices.getUserMedia(constraints);

        audioContext = new AudioContext();
        audioSource = audioContext.createMediaStreamSource(media);
        audioAnalyzer = audioContext.createAnalyser();
        audioAnalyzer.fftSize = 512;
        audioAnalyzer.minDecibels = -127;
        audioAnalyzer.maxDecibels = 0;
        audioAnalyzer.smoothingTimeConstant = 0;
        audioSource.connect(audioAnalyzer);
        //make sure audio still plays for user
        audioSource.connect(audioContext.destination);
        isAudioConnected = true;

        audioDataArray = new Uint8Array(audioAnalyzer.frequencyBinCount);

        viewing = true;

    }

}


chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
    if (message.target == 'offscreen') {
        if (message.action == 'capture-screenshot') {

            if (viewing) {

                ctx.drawImage(videoElement, message.coordinates.x, message.coordinates.y, 1, 1, 0, 0, 1, 1);
                //ctx.drawImage(videoElement, message.coordinates.x, message.coordinates.y, 30, 30, 0, 0, 30, 30); //debug-high
                //let image = canvas.toDataURL('image/png'); //debug-high

                let pixelColorUnformated = ctx.getImageData(0, 0, 1, 1).data;
                let pixelColor = { r: pixelColorUnformated[0], g: pixelColorUnformated[1], b: pixelColorUnformated[2] };

                //sendResponse({ pixelColor: pixelColor, image: image, myCoordinates: message.coordinates }); //debug-high
                sendResponse({ pixelColor: pixelColor });

            } else {

                //startViewing(constraints);

                //return pixel color as white
                let pixelColor = { r: 255, g: 255, b: 255 };
                sendResponse({ pixelColor: pixelColor });

            }

        } else if (message.action == 'capture-audio-level') {

            audioAnalyzer.getByteFrequencyData(audioDataArray);
            let volumeSum = 0;
            for (const volume of audioDataArray) {
                volumeSum += volume;
            }
            let averageVolume = volumeSum / audioDataArray.length;
            let audioLevel = Math.round(averageVolume * 100 / 127);

            sendResponse({ audioLevel: audioLevel });

        }
    }
});


function stopViewing() {

    if (viewing) {

        viewing = false;

        //TODO: is pausing really necessary at all here?
        videoElement.pause();

        media.getTracks().forEach(function (track) {
            track.stop();
            //track.enabled = false;
        });

        //media = undefined;

    }

}
