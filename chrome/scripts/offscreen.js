
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
        } else if (message.action == 'start-viewing-logo-advanced') {
            constraints = message.constraints;
            startViewing(constraints);
        } else if (message.action == 'start-listening') {
            constraints = message.constraints;
            startListening(constraints);
        } else if (message.action == 'stop-viewing') {
            //not currently being used, as offscreen is just closed and reopened in order to pause and resume viewing tab
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

        viewing = true;

    }

}


function createCanvas(width, height) {
    canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    //canvas.width = 30; //debug-high
    //canvas.height = 30; //debug-high
    ctx = canvas.getContext('2d', { willReadFrequently: true });
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

                if (!canvas) {
                    createCanvas(1, 1);
                }

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


//separated from above due to async reasons
chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
    if (message.target == 'offscreen') {
        if (message.action == 'capture-logo-advanced') {
            if (viewing) {
                if (!canvas) {
                    console.log(message.dimensions);
                    createCanvas(message.dimensions.width, message.dimensions.height);
                }

                ctx.drawImage(videoElement, message.coordinates.x, message.coordinates.y, message.dimensions.width, message.dimensions.height, 0, 0, message.dimensions.width, message.dimensions.height);
                let logoScreenshotBase64 = canvas.toDataURL('image/png'); //debug-high

                const fetchStart = performance.now();
                fetch("http://localhost:64143/advanced-logo-analysis", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        image: logoScreenshotBase64,
                        request: message.request,
                        commercial: message.isCommercialState
                    })
                })
                    .then(response => response.json())
                    .then(logoAnalysisResponse => {
                        //return jsonify({
                        //    "status": "ready",
                        //    "logo": match,
                        //    "confidence": float(similarity),
                        //    "current_edge_preview": image_to_base64(current_edge.astype(np.uint8)),
                        //    "mask_preview": image_to_base64(avg_edge_mask),
                        //    "diff_preview": image_to_base64(diff.astype(np.uint8))
                        //})
                        const fetchEnd = performance.now();
                        const fetchTime = ((fetchEnd - fetchStart) / 1000).toFixed(3);
                        //console.log(data);
                        sendResponse({ logoAnalysisResponse: logoAnalysisResponse, fetchTime: fetchTime, wasSuccessfulCall: true });
                    })
                    .catch(error => {
                        //TODO: send current state if error
                        //console.error("Error:", error); //TODO: comment this out?
                        sendResponse({ wasSuccessfulCall: false });
                    });
            } else {
                sendResponse({ logoAnalysisResponse: null });
            }

            return true; //keep message channel open for async response
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
