
var videoElement;
var canvas;
var ctx;
var viewing = false;


chrome.runtime.onMessage.addListener(function (message) {
    if (message.target == 'offscreen') {
        if (message.action == 'start-recording') {
            if (!viewing) {
                viewing = true;
                startViewing(message.constraints);
            }
        }
    }
});


async function startViewing(constraints) {

    const media = await navigator.mediaDevices.getUserMedia(constraints);

    videoElement = document.createElement('video');
    videoElement.srcObject = media;
    videoElement.muted = true;
    videoElement.play();

    canvas = document.createElement('canvas');
    canvas.width = constraints.video.mandatory.maxWidth;
    canvas.height = constraints.video.mandatory.maxHeight;
    ctx = canvas.getContext('2d', { willReadFrequently: true });

}



chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
    if (message.target == 'offscreen') {
        if (message.action == 'capture-screenshot') {

            ctx.drawImage(videoElement, message.coordinates.x, message.coordinates.y, 1, 1, 0, 0, 1, 1);

            let pixelColor = ctx.getImageData(0, 0, 1, 1).data;
            pixelColor = { r: pixelColor[0], g: pixelColor[1], b: pixelColor[2] };

            sendResponse({ pixelColor: pixelColor });

        }
    }
});


//function stopViewing() {

//    media.getTracks().forEach(function (track) {
//        track.stop();
//    });

//}