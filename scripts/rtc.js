
let peer = new RTCPeerConnection();
let channel = new BroadcastChannel("video_stream");

var receivedVideo;
var isInitialDifferenceSet = false;
var initialDifference;


clearPage();
addBannerMessage('Tab opened by YTOC extension to funnel overlay video audio through. Do not close until you are done using YTOC extension.');


function requestNewStreamIfOutOfSync(timestamp) {

    if (!receivedVideo || receivedVideo.readyState < 2) {
        return;
    }

    if (!isInitialDifferenceSet) {
        //assuming secondary stream is always behind
        initialDifference = receivedVideo.currentTime - timestamp;
        isInitialDifferenceSet = true;
    }

    let diff = receivedVideo.currentTime - timestamp;
    diff = Math.abs(diff - initialDifference);

    if (diff > 0.5) {
        channel.postMessage({ resend: true });
    }

}


peer.ontrack = event => {

    console.log('peer.ontrack event');

    if (!receivedVideo) {
        //TODO: Only receive and play audio instead of the full video
        receivedVideo = document.createElement("video");
        receivedVideo.autoplay = true;
        receivedVideo.muted = false;
        receivedVideo.style.display = 'none';
        document.body.appendChild(receivedVideo);
    }

    if (receivedVideo.srcObject !== event.streams[0]) {
        receivedVideo.srcObject = event.streams[0];
    }

    isInitialDifferenceSet = false;

};

peer.onicecandidate = event => {
    if (event.candidate) {
        channel.postMessage({ candidate: event.candidate.toJSON() });
    }
};

channel.onmessage = event => {
    if (event.data.offer) {
        peer.setRemoteDescription(new RTCSessionDescription(event.data.offer))
            .then(() => peer.createAnswer())
            .then(answer => peer.setLocalDescription(answer))
            .then(() => channel.postMessage({ answer: peer.localDescription.toJSON() }))
            .catch(error => console.error("Receiver: Error handling offer", error));
    } else if (event.data.candidate) {
        peer.addIceCandidate(new RTCIceCandidate(event.data.candidate))
            .catch(error => console.error("Receiver: Error adding ICE candidate", error));
    } else if (event.data.timestamp) {
        requestNewStreamIfOutOfSync(event.data.timestamp);
    } else if (event.data.play) {
        //receivedVideo.play();
        //give split sec for stream to be replaced so it doesn't sound janky
        setTimeout(() => {
            receivedVideo.muted = false;
        }, 300);
    } else if (event.data.pause) {
        //receivedVideo.pause();
        receivedVideo.muted = true;
    }
};


function clearPage() {

    //clear page
    document.getElementsByTagName('HTML')[0].remove();
    let newHTML = document.createElement('HTML');
    document.appendChild(newHTML);

    //clear window key
    if (window.key) {
        window.key = undefined;
    }

    //clear all timeouts
    var id = window.setTimeout(function () { }, 0);
    while (id--) {
        window.clearTimeout(id);
    }

    //replace head
    let newHead = document.createElement('head');
    newHTML.appendChild(newHead);

    //replace body
    let newBody = document.createElement('body');
    newHTML.appendChild(newBody);

}


function addBannerMessage(message) {

    var link = document.createElement('link');
    link.href = 'https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap';
    link.rel = 'stylesheet';
    document.head.appendChild(link);

    var banner = document.createElement('div');
    banner.id = 'custom-banner';

    banner.innerText = message;

    banner.style.position = 'fixed';
    banner.style.top = '0';
    banner.style.left = '0';
    banner.style.width = '100%';
    banner.style.backgroundColor = 'black';
    banner.style.color = 'red';
    banner.style.textAlign = 'center';
    banner.style.padding = '5px';
    banner.style.zIndex = '1000';
    banner.style.fontSize = '20px';
    banner.style.fontFamily = 'Roboto, Arial, sans-serif';
    banner.style.boxShadow = '0 2px 4px rgba(0,0,0,0.2)';

    document.body.style.marginTop = '35px';

    document.body.appendChild(banner);

}
