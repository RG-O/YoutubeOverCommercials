
var isFirefox = true; //********************

var overlayVideoType;
var shouldHideYTBackground;
var overlayHostName;
var isOtherSiteTroubleshootMode;
var isOverlayVideoZoomMode;
var commercialDetectionMode;
var isCorrectOverlayFrame = true;
var shouldShuffleYTPlaylist;
var maxPlaylistVideoNumber;
var playlistVideosPlayedArray = [];


//grab user set values and then run initialCommercialState() right when script is injected (assuming script is injected after frame had some time to load)
chrome.storage.sync.get([
    'overlayVideoType',
    'shouldHideYTBackground',
    'overlayHostName',
    'isOtherSiteTroubleshootMode',
    'isOverlayVideoZoomMode',
    'commercialDetectionMode',
    'shouldShuffleYTPlaylist'
], (result) => {

    overlayVideoType = result.overlayVideoType ?? 'yt-playlist';
    shouldHideYTBackground = result.shouldHideYTBackground ?? true;
    overlayHostName = result.overlayHostName ?? 'www.youtube.com';
    isOtherSiteTroubleshootMode = result.isOtherSiteTroubleshootMode ?? false;
    isOverlayVideoZoomMode = result.isOverlayVideoZoomMode ?? false;
    commercialDetectionMode = result.commercialDetectionMode ?? 'auto-pixel-normal';
    //adjusting to updated settings for people that have already downloaded the extension (people set to opposite pixel mode will need to reselect in updated settings)
    if (commercialDetectionMode === 'auto') {
        commercialDetectionMode = 'auto-pixel-normal';
    }
    shouldShuffleYTPlaylist = result.shouldShuffleYTPlaylist ?? false;

    //making sure if requested overlay video isn't a yt video and has same domain as main/background video that script wasn't loaded into that main video frame
    if (overlayHostName != 'www.youtube.com') {
        if (typeof mainVideoCollection !== 'undefined') {
            //TODO: is this second check necessary if we already know mainVideoCollection is defined? would the frames share this variable?
            if (mainVideoCollection == document.getElementsByTagName('video')) {
                isCorrectOverlayFrame = false;
                return;
            }
        }
    }

    //set marker on potential overlays so the Live Thread Ticker browser extension knows not to apply
    if (document.getElementsByTagName('body')[0]) {
        let lttBlocker = document.createElement("span");
        lttBlocker.id = 'YTOC-LTT-Blocker';
        document.getElementsByTagName('body')[0].appendChild(lttBlocker);
    }

    //TODO: separate isOverlayVideoZoomMode into two settings, one that can zoom the video tag and the other that zooms on iframe (user could use both)
    if (isOverlayVideoZoomMode && window.location.hostname == overlayHostName && overlayHostName != 'www.youtube.com') {
        //make sure we are in iframe to make sure we don't zoom in on primary video if that is also in an iframe
        if (inIFrame()) {
            setTimeout(() => {
                let iFrame = document.getElementsByTagName('iframe')[0];

                if (iFrame) {
                    zoomInOnElement(iFrame);

                    if (shouldHideYTBackground) {
                        iFrame.style.background = 'transparent';

                        let parent = iFrame.parentElement;
                        while (parent) {
                            parent.style.background = 'transparent';
                            parent = parent.parentElement;
                        }
                    }
                }
            }, 1000);
        }
    }

    if (window.location.hostname == overlayHostName || (isOtherSiteTroubleshootMode && overlayHostName != 'www.youtube.com')) {
        waitForElement('video').then(() => {
            setTimeout(() => {
                initialCommercialState();
            }, 500);
        });
    } else {
        isCorrectOverlayFrame = false;
    }

});


chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
    if (message.action == 'overlay_commercial_state') {
        if (isCorrectOverlayFrame) {
            startCommercialState();
        }
    } else if (message.action == 'overlay_non_commercial_state') {
        if (isCorrectOverlayFrame) {
            stopCommercialState();
        }
    }
});


function initialCommercialState() {

    //initial click or play on the overlay video
    if (overlayHostName == 'www.youtube.com' && document.getElementsByClassName('video-stream html5-main-video')[0]) {
        document.getElementsByClassName('video-stream html5-main-video')[0].click();
    } else if (overlayHostName != 'tv.youtube.com') {

        if (isOtherSiteTroubleshootMode) {

            let overlayVideoCollection = document.getElementsByTagName('video');
            for (let i = 0; i < overlayVideoCollection.length; i++) {
                overlayVideoCollection[i].play();
            }

        } else if (document.getElementsByTagName('video')[0]) {

            document.getElementsByTagName('video')[0].play();

        }

    } //else do nothing because yttv plays automatically

    //hide scrollbar in case it shows for some non YT site because it might if the iframe is too small
    if (overlayHostName != 'www.youtube.com') {

        let hideScollStyle = document.createElement("style");
        hideScollStyle.textContent = `
            ::-webkit-scrollbar {
                display: none;
            }
        `;
        let insertLocation = document.getElementsByTagName('body')[0];
        insertLocation.appendChild(hideScollStyle);
        //TODO: do special scrollbar hiding for firefox?

    }

    //waiting a second for video to load to run some checks and stuff
    setTimeout(() => {

        let myYTOCVideo;
        if (overlayHostName == 'tv.youtube.com') {
            myYTOCVideo = document.getElementsByClassName('video-stream html5-main-video')[0];
        } else {
            myYTOCVideo = document.getElementsByTagName('video')[0];
        }

        if (myYTOCVideo && shouldHideYTBackground) {
            myYTOCVideo.style.background = 'transparent';

            let parent = myYTOCVideo.parentElement;
            while (parent) {
                parent.style.background = 'transparent';
                parent = parent.parentElement;
            }
        }

        if (isOverlayVideoZoomMode) {
            //make sure we are in iframe to make sure we don't zoom in on primary video //TODO: may not actually be needed here because we already confirmed this is not where the primary video is
            if (inIFrame()) {
                let overlayVideoCollection = document.getElementsByTagName('video');
                for (let i = 0; i < overlayVideoCollection.length; i++) {
                    zoomInOnElement(overlayVideoCollection[i]);
                    //make sure user can still controll video while zoomed in
                    //clear controls first
                    overlayVideoCollection[i].removeAttribute('controls');
                    //then set controls viewable on hover
                    overlayVideoCollection[i].addEventListener('mouseenter', function () {
                        toggleVideoControls(this);
                    });
                    overlayVideoCollection[i].addEventListener('mouseleave', function () {
                        toggleVideoControls(this);
                    });
                }
            }
        }

        //unmute if started out muted for yt
        if (overlayHostName == 'www.youtube.com') {

            if (document.getElementsByClassName('ytp-mute-button')[0] && document.querySelector('[title="Unmute (m)"]')) {
                document.getElementsByClassName('ytp-mute-button')[0].click();
            }

            if (document.getElementsByClassName('ytp-pause-overlay-container')[0]) {
                document.getElementsByClassName('ytp-pause-overlay-container')[0].remove();
            }

            if (shouldShuffleYTPlaylist) {
                if (document.getElementsByClassName('ytp-playlist-menu-button-text')[0]) {
                    let playlistCount = document.getElementsByClassName('ytp-playlist-menu-button-text')[0].textContent;
                    let firstVideo = [playlistCount.split('/')[0]];
                    maxPlaylistVideoNumber = playlistCount.split('/')[1];
                    playlistVideosPlayedArray = Array.from({ length: maxPlaylistVideoNumber }, (_, i) => i + 1);
                    playlistVideosPlayedArray.splice(firstVideo - 1, 1);
                    document.getElementsByClassName('ytp-playlist-menu-button')[0].click();
                    setTimeout(() => {
                        document.getElementsByClassName('ytp-playlist-menu-button')[0].click();
                    }, 500);
                }
            }
            
        }

        //TODO: add button on top of overlay video  if in live mode that asks if user would like video to play PiP while main video is not commercial, disapear if not clicked after x time

        //checking if video is paused even though it is just about about ready to play, indicating something is preventing it from doing so
        if (myYTOCVideo && myYTOCVideo.paused && myYTOCVideo.readyState > 2) {

            let elm = document.createElement("div");
            elm.textContent = "Detected that video cannot auto start due to reasons. Please manually play video, pause video, and then play video again. Doing so will allow the extension to work properly from here on out. Sorry for the inconvenience! This message will soon disapear.";
            elm.style.setProperty("color", "red", "important");
            elm.style.setProperty("background-color", "white", "important");
            elm.style.setProperty("z-index", "2147483647", "important");
            elm.style.setProperty("position", "absolute", "important");

            //TODO: set at very top level insead of video level
            let insertLocation = myYTOCVideo.parentNode;
            insertLocation = insertLocation.parentNode;
            let firstChild = insertLocation.firstChild;
            insertLocation.insertBefore(elm, firstChild);

            //slowly removing message
            setTimeout(() => {

                elm.style.setProperty("animation", "fadeOut ease 15s");
                elm.style.setProperty("animation-fill-mode", "forwards");
                let fadeStyle = document.createElement("style");
                fadeStyle.textContent = `
                    @keyframes fadeOut {
                        0% {
                        opacity: 1;
                        }
                        100% {
                        opacity: 0;
                        }
                    }
                `;
                elm.appendChild(fadeStyle);

                setTimeout(() => {
                    elm.remove();
                }, 15000);

            }, 15000);

        }

        //if commercial detection mode is in auto audio, play audio from overlay video in seperate tab as to not inadvertently trigger audio detection on main tab
        if (commercialDetectionMode === 'auto-audio' && !isFirefox) {

            //waiting another second to give new tab a chance to load
            setTimeout(() => {

                console.log('Initiating RTCPeerConnection');

                var stream;
                try {
                    if (myYTOCVideo.captureStream) {
                        stream = myYTOCVideo.captureStream();
                    } else if (myYTOCVideo.mozCaptureStream) {
                        stream = myYTOCVideo.mozCaptureStream();
                    } else {
                        alert(`Message from Live Commercial Blocker Extension: Videos from ${overlayHostName} not eligible for overlay while in Audio Detection mode. Please try to use a different video source, a different Overlay Type, or a different Mode of Detection.`);
                        return;
                    }
                } catch (error) {
                    console.error("Live Commercial Blocker: An error occurred while trying to captureStream:", error.message);
                    alert(`Message from Live Commercial Blocker Extension: Videos from ${overlayHostName} not eligible for overlay while in Audio Detection mode. Please try to use a different video source, a different Overlay Type, or a different Mode of Detection.`);
                    return;
                }

                let peer = new RTCPeerConnection();
                let channel = new BroadcastChannel("video_stream");
                let connectionTimeout;

                //displaying message to user if there is an issue funnelling audio to other tab.
                function startConnectionTimeout() {
                    connectionTimeout = setTimeout(() => {
                        alert(`Message from Live Commercial Blocker Extension: Due to technical limitations, audio from overlay ${overlayHostName} videos cannot be played over this website while in Audio Level Low Commercial Detection Mode. Please try a different Overlay Type or Commercial Detection Mode.`);
                    }, 4000);
                }

                //TODO: send audio only or at least only play audio on other tab
                stream.getTracks().forEach(track => peer.addTrack(track, stream));

                peer.onicecandidate = event => {
                    if (event.candidate) {
                        channel.postMessage({ candidate: event.candidate.toJSON() });
                    }
                };

                //constaintly comparing timestamps to keep video/audio in sync as well as switch streams when video changes //TODO: is there a better way to do this?
                setInterval(() => {
                    if (myYTOCVideo && !myYTOCVideo.paused) {
                        channel.postMessage({ timestamp: myYTOCVideo.currentTime });
                    }
                }, 250);

                peer.createOffer()
                    .then(offer => peer.setLocalDescription(offer))
                    .then(() => {
                        channel.postMessage({ offer: peer.localDescription.toJSON() })
                        startConnectionTimeout();
                    })
                    .catch(error => console.error("Sender: Error creating offer", error));

                channel.onmessage = event => {
                    console.log('channel.onmessage event');
                    if (event.data.answer) {
                        peer.setRemoteDescription(new RTCSessionDescription(event.data.answer))
                            .then(() => clearTimeout(connectionTimeout)) //clearing timeout because connection was successful
                            .catch(error => console.error("Sender: Error setting remote description", error));
                    } else if (event.data.candidate) {
                        peer.addIceCandidate(new RTCIceCandidate(event.data.candidate))
                            .catch(error => console.error("Sender: Error adding ICE candidate", error));
                    } else if (event.data.resend) {
                        resendStream();
                    }
                };

                function resendStream() {

                    let newStream;
                    if (myYTOCVideo.captureStream) {
                        newStream = myYTOCVideo.captureStream();
                    } else if (myYTOCVideo.mozCaptureStream) {
                        newStream = myYTOCVideo.mozCaptureStream();
                    }

                    peer.getSenders().forEach(sender => peer.removeTrack(sender));
                    newStream.getTracks().forEach(track => peer.addTrack(track, newStream));

                    peer.createOffer()
                        .then(offer => peer.setLocalDescription(offer))
                        .then(() => channel.postMessage({ offer: peer.localDescription.toJSON() }))
                        .catch(error => console.error("Error renegotiating", error));

                }

                myYTOCVideo.addEventListener('playing', function () {
                    channel.postMessage({ play: true });
                });

                myYTOCVideo.addEventListener('pause', function () {
                    channel.postMessage({ pause: true });
                });

                //to mute in current tab without letting the other tab know //TODO: is there a better way to do this?
                const audioCtx = new AudioContext();
                const source = audioCtx.createMediaElementSource(myYTOCVideo);
                const dest = audioCtx.createMediaStreamDestination();
                source.connect(dest);

            }, 250);

        }


    }, 2500);

}

//plays or unmutes overlay video
function startCommercialState() {

    if (overlayHostName == 'www.youtube.com') {

        if (overlayVideoType == 'yt-live' && document.getElementsByClassName('ytp-mute-button')[0] && document.querySelector('[title="Unmute (m)"]')) {

            document.getElementsByClassName('ytp-mute-button')[0].click();

        } else if (overlayVideoType != 'yt-live' && document.getElementsByTagName('video')[0].paused) {

            if (shouldShuffleYTPlaylist && document.getElementsByClassName('ytp-video-menu-item-index')[0]) {
                document.getElementsByClassName('ytp-video-menu-item-index')[getRandomVideoNumber() - 1].click();
            } else {
                document.getElementsByTagName('video')[0].play();
            }
            

        }

    } else {

        if (overlayVideoType == 'other-live') {

            if (overlayHostName == 'tv.youtube.com' && document.querySelector('[aria-label="Unmute (m)"]')) {

                document.querySelector('[aria-label="Unmute (m)"]').click();

            } else if (overlayHostName != 'tv.youtube.com') {

                if (isOtherSiteTroubleshootMode) {

                    let overlayVideoCollection = document.getElementsByTagName('video');
                    for (let i = 0; i < overlayVideoCollection.length; i++) {
                        overlayVideoCollection[i].muted = false;
                    }

                } else if (document.getElementsByTagName('video')[0]) {

                    document.getElementsByTagName('video')[0].muted = false;

                }
            }

        } else if (overlayHostName == 'tv.youtube.com' && document.querySelector('[aria-label="Play (k)"]')) {

            document.querySelector('[aria-label="Play (k)"]').click();

        } else if (isOtherSiteTroubleshootMode) {

            let overlayVideoCollection = document.getElementsByTagName('video');
            for (let i = 0; i < overlayVideoCollection.length; i++) {
                if (overlayVideoCollection[i].paused) {
                    overlayVideoCollection[i].play();
                }
            }

        } else if (document.getElementsByTagName('video')[0].paused) {

            document.getElementsByTagName('video')[0].play();

        }

    }

}

//pauses or mutes overlay video
function stopCommercialState() {

    if (overlayHostName == 'www.youtube.com') {

        if (overlayVideoType == 'yt-live' && document.getElementsByClassName('ytp-mute-button')[0] && document.querySelector('[title="Mute (m)"]')) {

            document.getElementsByClassName('ytp-mute-button')[0].click();

        } else if (overlayVideoType != 'yt-live' && !document.getElementsByTagName('video')[0].paused) {

            document.getElementsByTagName('video')[0].pause();

        } //else do nothing

    } else {

        if (overlayVideoType == 'other-live') {

            if (overlayHostName == 'tv.youtube.com' && document.querySelector('[aria-label="Mute (m)"]')) {

                document.querySelector('[aria-label="Mute (m)"]').click();

            } else if (overlayHostName != 'tv.youtube.com') {

                if (isOtherSiteTroubleshootMode) {

                    let overlayVideoCollection = document.getElementsByTagName('video');
                    for (let i = 0; i < overlayVideoCollection.length; i++) {
                        overlayVideoCollection[i].muted = true;
                    }

                } else if (document.getElementsByTagName('video')[0]) {

                    document.getElementsByTagName('video')[0].muted = true;

                }

            }

        } else if (overlayHostName == 'tv.youtube.com' && document.querySelector('[aria-label="Pause (k)"]')) {

            document.querySelector('[aria-label="Pause (k)"]').click();

        } else if (isOtherSiteTroubleshootMode) {

            let overlayVideoCollection = document.getElementsByTagName('video');
            for (let i = 0; i < overlayVideoCollection.length; i++) {
                if (!overlayVideoCollection[i].paused) {
                    overlayVideoCollection[i].pause();
                }
            }

        } else if (!document.getElementsByTagName('video')[0].paused) {

            document.getElementsByTagName('video')[0].pause();

        }

    }

}


//sets iframe to take up the full frame
function zoomInOnElement(zoomElement) {
    zoomElement.style.setProperty("visibility", "visible", "important");
    zoomElement.style.setProperty("position", "fixed", "important");
    zoomElement.style.setProperty("top", "0", "important");
    zoomElement.style.setProperty("left", "0", "important");
    zoomElement.style.setProperty("min-width", "0", "important");
    zoomElement.style.setProperty("min-height", "0", "important");
    zoomElement.style.setProperty("width", "100%", "important");
    zoomElement.style.setProperty("height", "100%", "important");
    zoomElement.style.setProperty("padding", "0", "important");
    zoomElement.style.setProperty("border-width", "0", "important");
    zoomElement.style.setProperty("z-index", "2147483647", "important");
}


function resetPlaylistVideosPlayedArray() {
    playlistVideosPlayedArray = Array.from({ length: maxPlaylistVideoNumber }, (_, i) => i + 1);
}


function getRandomVideoNumber() {
    if (playlistVideosPlayedArray.length === 0) {
        resetPlaylistVideosPlayedArray();
    }
    const index = Math.floor(Math.random() * playlistVideosPlayedArray.length);
    //removes the video number from array when it returns it
    return playlistVideosPlayedArray.splice(index, 1)[0];
}


function inIFrame() {
    try {
        return window.self !== window.top;
    } catch (e) {
        return true;
    }
}


function toggleVideoControls(video) {
    if (video.hasAttribute('controls')) {
        video.removeAttribute('controls');
    } else {
        video.setAttribute('controls', 'controls');
    }
}


function waitForElement(target) {
    return new Promise(resolve => {
        if (document.querySelector(target)) {
            return resolve(document.querySelector(target));
        }

        const observer = new MutationObserver(mutations => {
            if (document.querySelector(target)) {
                observer.disconnect();
                resolve(document.querySelector(target));
            }
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
    });
}