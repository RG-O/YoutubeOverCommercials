
var constraints;
var media;
var videoElement;
var canvas;
var ctx;
var viewing = false;


chrome.runtime.onMessage.addListener(function (message) {
    if (message.target == 'offscreen') {
        if (message.action == 'start-viewing') {
            constraints = message.constraints;
            startViewing(constraints);
        } else if (message.action == 'stop-viewing') {
            stopViewing();
        } else if (message.action == 'close') {
            window.close();
        }
    }
});


async function startViewing(constraints) {

    if (!viewing) {

        viewing = true;

        media = await navigator.mediaDevices.getUserMedia(constraints);

        videoElement = document.createElement('video');
        videoElement.srcObject = media;
        videoElement.muted = true;
        videoElement.play();

        canvas = document.createElement('canvas');
        canvas.width = constraints.video.mandatory.maxWidth;
        canvas.height = constraints.video.mandatory.maxHeight;
        ctx = canvas.getContext('2d', { willReadFrequently: true });

    }

}


chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
    if (message.target == 'offscreen') {
        if (message.action == 'capture-screenshot') {

            if (viewing) {

                //TODO: verify I am grabbing the exact pixel here
                ctx.drawImage(videoElement, message.coordinates.x, message.coordinates.y, 1, 1, 0, 0, 1, 1);

                let pixelColor = ctx.getImageData(0, 0, 1, 1).data;
                pixelColor = { r: pixelColor[0], g: pixelColor[1], b: pixelColor[2] };

                sendResponse({ pixelColor: pixelColor });

            } else {

                //startViewing(constraints);

                //return pixel color as white
                let pixelColor = { r: 255, g: 255, b: 255 };
                sendResponse({ pixelColor: pixelColor });

            }

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
        });

    }

}
