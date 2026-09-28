
var constraints;
var media;
var videoElement;
var canvas;
var pluginCanvas;
var previousPluginScreenshotMaxWidth = 0;
var previousPluginScreenshotMaxHeight = 0;
var ctx;
var viewing = false;
var audioContext;
var audioSource;
var audioAnalyzer;
var audioDataArray;
var isAudioConnected = false;
var pluginWSScript;

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
        } else if (message.action == 'start-listening-microphone') {
            insertDoubleClapDetectorScript();
        } else if (message.action == 'stop-viewing') {
            stopViewing(true);
        } else if (message.action == 'stop-listening') {
            stopViewing(false);
        } else if (message.action == 'resume-viewing') {
            //does not currently work, start-viewing works to resume
            startViewing(constraints);
        } else if (message.action == 'disconnect-tab-audio') {
            if (isAudioConnected) {
                audioSource.disconnect(audioContext.destination);
                isAudioConnected = false;
            }
        } else if (message.action == 'connect-tab-audio') {
            //TODO: set pluginCommercialTriggerWSOpenedBy, pluginOverlayWSOpenedBy, and dualWSOpenedBy here so offscreen isn't closed after grabbing manifests
            if (!isAudioConnected) {
                audioSource.connect(audioContext.destination);
                isAudioConnected = true;
            }
        } else if (message.action == 'connect-to-ws-plugins') {
            launchPluginWSScript(message.payload);
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


function createPluginCanvas(width, height) {
    pluginCanvas = document.createElement('canvas');
    pluginCanvas.width = width;
    pluginCanvas.height = height;
    ctx = pluginCanvas.getContext('2d', { willReadFrequently: true });
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


function insertDoubleClapDetectorScript() {
    setTimeout(() => {
        let script = document.createElement('script');
        script.src = "/scripts/double-clap-detector.js";
        document.body.appendChild(script);
    }, 100);
}


function launchPluginWSScript(payload) {
    //TODO: figure out if overlay or trigger or both
    if (!pluginWSScript) {
        pluginWSScript = document.createElement('script');
        pluginWSScript.src = "/scripts/plugin-ws-client.js";
        //pluginWSScript.type = "module";
        document.body.appendChild(pluginWSScript);
        pluginWSScript.addEventListener('load', function () {
            ws.initWSPlugins(payload);
        });
    } else {
        ws.initWSPlugins(payload);
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

        } else if (message.action == 'capture-screenshot-plugin') {

            if (viewing) {
                const trimTopPercent = message.options.trimOptionsPercentages.top ?? 0;
                const trimRightPercent = message.options.trimOptionsPercentages.right ?? 0;
                const trimBottomPercent = message.options.trimOptionsPercentages.bottom ?? 0;
                const trimLeftPercent = message.options.trimOptionsPercentages.left ?? 0;

                const MAX_WIDTH = message.options.maxDimensionsPixels.width ?? 500;
                const MAX_HEIGHT = message.options.maxDimensionsPixels.height ?? 300;

                const videoWidth = videoElement.videoWidth;
                const videoHeight = videoElement.videoHeight;

                // Calculate how many pixels to trim from each side
                const trimTop = videoHeight * (trimTopPercent / 100);
                const trimRight = videoWidth * (trimRightPercent / 100);
                const trimBottom = videoHeight * (trimBottomPercent / 100);
                const trimLeft = videoWidth * (trimLeftPercent / 100);

                // Calculate the source area AFTER trimming
                const sourceX = trimLeft;
                const sourceY = trimTop;
                const sourceWidth = videoWidth - trimLeft - trimRight;
                const sourceHeight = videoHeight - trimTop - trimBottom;

                // Scale the trimmed image to fit within the maximum dimensions
                const scale = Math.min(
                    MAX_WIDTH / sourceWidth,
                    MAX_HEIGHT / sourceHeight,
                    1 // Prevent upscaling smaller images
                );

                const screenshotWidth = Math.round(sourceWidth * scale);
                const screenshotHeight = Math.round(sourceHeight * scale);

                if (
                    !pluginCanvas ||
                    pluginCanvas.width !== screenshotWidth ||
                    pluginCanvas.height !== screenshotHeight
                ) {
                    createPluginCanvas(screenshotWidth, screenshotHeight);
                }

                previousPluginScreenshotMaxWidth = MAX_WIDTH;
                previousPluginScreenshotMaxHeight = MAX_HEIGHT;

                // Draw only the trimmed portion of the video
                ctx.drawImage(
                    videoElement,
                    sourceX,
                    sourceY,
                    sourceWidth,
                    sourceHeight,
                    0,
                    0,
                    screenshotWidth,
                    screenshotHeight
                );

                pluginCanvas.toBlob((blob) => {
                    if (blob && pluginWSScript) {
                        ws.sendMessageToWSPlugins(blob);
                    }
                }, "image/jpeg", 0.8);

            } else {

                //startViewing(constraints);
                //TODO: something

            }

        }
    }
});


//separated from above due to async reasons
chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
    if (message.target == 'offscreen') {
        if (message.action == 'capture-logo-advanced') {
            if (viewing) {
                if (!canvas) {
                    createCanvas(message.dimensions.width, message.dimensions.height);
                }

                ctx.drawImage(videoElement, message.coordinates.x, message.coordinates.y, message.dimensions.width, message.dimensions.height, 0, 0, message.dimensions.width, message.dimensions.height);
                const logoScreenshotBase64 = canvas.toDataURL('image/png');

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
                        sendResponse({ logoAnalysisResponse: logoAnalysisResponse, wasSuccessfulCall: true });
                    })
                    .catch(error => {
                        sendResponse({ wasSuccessfulCall: false });
                    });
            } else {
                sendResponse({ logoAnalysisResponse: null });
            }

            return true; //keep message channel open for async response
        }
    }
});


function stopViewing(isVideo) {

    if (viewing) {

        viewing = false;

        if (isVideo) {
            //TODO: is pausing really necessary at all here?
            videoElement.pause();
            videoElement.remove();
        }

        media.getTracks().forEach(function (track) {
            track.stop();
            track.enabled = false;
        });

        media = undefined;

    }

}
