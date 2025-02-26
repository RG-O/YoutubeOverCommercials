
//TODO: add second way of initiating this by user clicking button in extension popup that then starts listening for full screen
//TODO: remove most &&s on if statements and seperate them to make it more readable

//sending message to content.js when user plugs in keyboard shortcut
chrome.commands.onCommand.addListener(function (command) {
    if (command === "execute_shortcut") {
        chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
            chrome.tabs.sendMessage(tabs[0].id, { action: "execute_manual_switch_function" });
        });
    }
});

//listining for messages from content.js
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === "initial_execute_overlay_video_interaction") {

        //grab user set values
        chrome.storage.sync.get(['shouldHideYTBackground', 'overlayHostName', 'isOtherSiteTroubleshootMode', 'isOverlayVideoZoomMode', 'commercialDetectionMode'], (result) => {

            let shouldHideYTBackground = result.shouldHideYTBackground ?? true;
            let overlayHostName = result.overlayHostName ?? 'www.youtube.com';
            let isOtherSiteTroubleshootMode = result.isOtherSiteTroubleshootMode ?? false;
            let isOverlayVideoZoomMode = result.isOverlayVideoZoomMode ?? false;
            let commercialDetectionMode = result.commercialDetectionMode ?? 'auto-pixel-normal';
            //adjusting to updated settings for people that have already downloaded the extension (people set to opposite pixel mode will need to reselect in updated settings)
            if (commercialDetectionMode === 'auto') {
                commercialDetectionMode = 'auto-pixel-normal';
            }

            //TODO: inject an entire js file into the overlay video and then message functions in it, would that be better?
            //injecting initialCommercialState() into all frames on the active tab
            chrome.scripting.executeScript({
                target: { tabId: sender.tab.id, allFrames: true },
                func: initialCommercialState,
                args: [shouldHideYTBackground, overlayHostName, isOtherSiteTroubleshootMode, isOverlayVideoZoomMode, commercialDetectionMode]
            });

        });

    } else if (message.action === "execute_overlay_video_non_commercial_state") {

        //grab user set values
        chrome.storage.sync.get(['overlayVideoType', 'overlayHostName', 'isOtherSiteTroubleshootMode'], (result) => {

            let overlayVideoType = result.overlayVideoType ?? 'yt-playlist';
            let overlayHostName = result.overlayHostName ?? 'www.youtube.com';
            let isOtherSiteTroubleshootMode = result.isOtherSiteTroubleshootMode ?? false;

            //injecting stopCommercialState() into all frames on the active tab
            chrome.scripting.executeScript({
                target: { tabId: sender.tab.id, allFrames: true },
                func: stopCommercialState,
                args: [overlayVideoType, overlayHostName, isOtherSiteTroubleshootMode]
            });

        });

    } else if (message.action === "execute_overlay_video_commercial_state") {

        //grab user set values
        chrome.storage.sync.get(['overlayVideoType', 'overlayHostName', 'isOtherSiteTroubleshootMode'], (result) => {

            let overlayVideoType = result.overlayVideoType ?? 'yt-playlist';
            let overlayHostName = result.overlayHostName ?? 'www.youtube.com';
            let isOtherSiteTroubleshootMode = result.isOtherSiteTroubleshootMode ?? false;

            //injecting startCommercialState() into all frames on the active tab
            chrome.scripting.executeScript({
                target: { tabId: sender.tab.id, allFrames: true },
                func: startCommercialState,
                args: [overlayVideoType, overlayHostName, isOtherSiteTroubleshootMode]
            });

        });

    } else if (message.action === "open_spotify") {

        //open spotify in an inactive pinned tab
        chrome.tabs.create({
            pinned: true,
            active: true,
            url: 'https://open.spotify.com/',
        },
            (tab) => {

                //waiting a little for the spotify tab to show because firefox doesn't seem to let you inject into tabs that aren't showing yet
                setTimeout(() => {

                    //saving tab id to chrome storage to avoid global variables clearing out in service worker //TODO: figure out if better way for this
                    chrome.storage.sync.set({ spotifyTabID: tab.id });

                    chrome.scripting.executeScript({
                        target: { tabId: tab.id, allFrames: true },
                        files: ["scripts/spotify.js"]
                    });

                }, 2500);

            }
        );

    } else if (message.action === "close_spotify") {

        chrome.storage.sync.get(['spotifyTabID'], (result) => {

            if (result.spotifyTabID) {

                chrome.tabs.query({}, function (tabs) {

                    let exists = tabs.some(tab => tab.id === result.spotifyTabID);
                    if (exists) {
                        chrome.tabs.remove(result.spotifyTabID);
                    }

                });

            }

        });

    } else if (message.action === "execute_music_non_commercial_state") {

        //grab user set values
        chrome.storage.sync.get(['overlayVideoType', 'spotifyTabID'], (result) => {

            let overlayVideoType = result.overlayVideoType ?? 'yt-playlist';

            if (overlayVideoType == 'spotify') {

                if (result.spotifyTabID) {

                    chrome.tabs.query({}, function (tabs) {

                        let exists = tabs.some(tab => tab.id === result.spotifyTabID);
                        if (exists) {

                            chrome.tabs.sendMessage(result.spotifyTabID, { action: "pause_spotify" });

                        }

                    });

                }

            } else if (overlayVideoType == 'other-tabs') {

                //mute all unmuted tabs that aren't the main video one
                chrome.tabs.query({ muted: false }, (tabs) => {
                    tabs.forEach((tab) => {
                        if (tab.id !== sender.tab.id) {
                            chrome.tabs.update(tab.id, { muted: true });
                        }
                    });

                });

                //TODO: Decide if I want to mute/unmute the main tab - something to consider: when somebody sets the volume to go lower instead of completey muted
                //chrome.tabs.update(sender.tab.id, { muted: false });

            }

        });

    } else if (message.action === "execute_music_commercial_state") {

        //grab user set values
        chrome.storage.sync.get(['overlayVideoType', 'spotifyTabID', 'shouldClickNextOnPlaySpotify'], (result) => {

            let overlayVideoType = result.overlayVideoType ?? 'yt-playlist';
            let shouldClickNextOnPlaySpotify = result.shouldClickNextOnPlaySpotify ?? true;

            if (overlayVideoType == 'spotify') {

                if (result.spotifyTabID) {

                    chrome.tabs.query({}, function (tabs) {

                        let exists = tabs.some(tab => tab.id === result.spotifyTabID);
                        if (exists) {

                            if (shouldClickNextOnPlaySpotify) {
                                chrome.tabs.sendMessage(result.spotifyTabID, { action: "next_spotify" });
                            } else {
                                chrome.tabs.sendMessage(result.spotifyTabID, { action: "play_spotify" });
                            }

                        }

                    });

                }

            } else if (overlayVideoType == 'other-tabs') {

                //unmute all mutted tabs that aren't the main video one
                chrome.tabs.query({ muted: true }, (tabs) => {
                    tabs.forEach((tab) => {
                        if (tab.id !== sender.tab.id) {
                            chrome.tabs.update(tab.id, { muted: false });
                        }
                    });

                });

                //TODO: Decide if I want to mute/unmute the main tab - something else to consider: need some sort of unmute all tabs for beforeunload
                //chrome.tabs.update(sender.tab.id, { muted: true });

            }

        });

    } else if (message.action === "open_overlay_video_audio_tab") {

        //grab user set values
        chrome.storage.sync.get(['overlayHostName'], (result) => {

            let overlayHostName = result.overlayHostName ?? 'www.youtube.com';

            //since in auto-audio detection mode, open tab using the same domain as the overlay video so I can funnel audio from the overlay video through this tab as to not trigger audio detection
            //TODO: can I iframe this in offscreen.html instead? As an additional tab would not be needed and audio playing in offscreen doesn't seem to count towards the tab audio
            chrome.tabs.create({
                pinned: true,
                active: false,
                url: 'https://' + overlayHostName,
            },
                (tab) => {

                    setTimeout(() => {

                        chrome.storage.sync.set({ overlayVideoAudioTabID: tab.id });

                        chrome.scripting.executeScript({
                            target: { tabId: tab.id, allFrames: false },
                            func: rtcPlayAudio
                        });

                    }, 500);

                }
            );

        });

    } else if (message.action === "close_overlay_video_audio_tab") {

        chrome.storage.sync.get(['overlayVideoAudioTabID'], (result) => {

            if (result.overlayVideoAudioTabID) {

                chrome.tabs.query({}, function (tabs) {

                    let exists = tabs.some(tab => tab.id === result.overlayVideoAudioTabID);
                    if (exists) {
                        chrome.tabs.remove(result.overlayVideoAudioTabID);
                    }

                });

            }

        });

    }
});


function initialCommercialState(shouldHideYTBackground, overlayHostName, isOtherSiteTroubleshootMode, isOverlayVideoZoomMode, commercialDetectionMode) {

    //making sure if requested overlay video isn't a yt video and has same domain as main/background video that script wasn't loaded into that main video frame
    if (overlayHostName != 'www.youtube.com') {
        if (typeof mainVideoCollection !== 'undefined') {
            //TODO: is this second check necessary if we already know mainVideoCollection is defined? would the frames share this variable?
            if (mainVideoCollection == document.getElementsByTagName('video')) {
                return;
            }
        }
    }

    //TODO: add second (maybe call it B) isOverlayVideoZoomMode that can zoom the video tag (user could use both)
    if (isOverlayVideoZoomMode && window.location.hostname == overlayHostName && overlayHostName != 'www.youtube.com') {

        setTimeout(() => {

            if (document.getElementsByTagName('iframe')[0]) {

                //making the assumed iframe with the video fit the full page
                let videoIFrame = document.getElementsByTagName('iframe')[0];
                videoIFrame.style.setProperty("visibility", "visible", "important");
                videoIFrame.style.setProperty("position", "fixed", "important");
                videoIFrame.style.setProperty("top", "0", "important");
                videoIFrame.style.setProperty("left", "0", "important");
                videoIFrame.style.setProperty("min-width", "0", "important");
                videoIFrame.style.setProperty("min-height", "0", "important");
                videoIFrame.style.setProperty("width", "100%", "important");
                videoIFrame.style.setProperty("height", "100%", "important");
                videoIFrame.style.setProperty("padding", "0", "important");
                videoIFrame.style.setProperty("border-width", "0", "important");
                videoIFrame.style.setProperty("z-index", "2147483647", "important");

            }

        }, 1000);

    }

    //making sure frame has the requested hostname of the overlay video so this doesn't accidentaly impact the main/background video
    if (window.location.hostname == overlayHostName || (isOtherSiteTroubleshootMode && overlayHostName != 'www.youtube.com')) {

        //initial click or play on the overlay video
        if (overlayHostName == 'www.youtube.com' && document.getElementsByClassName('video-stream html5-main-video')[0]) {
            document.getElementsByClassName('video-stream html5-main-video')[0].click();
        } else if (overlayHostName != 'tv.youtube.com') {
            document.getElementsByTagName('video')[0].play();
        } //else do nothing because yttv plays automatically

        //set marker on overlay video so the Live Thread Ticker browser extension knows not to apply
        if (document.getElementsByTagName('body')[0]) {
            let lttBlocker = document.createElement("span");
            lttBlocker.id = 'YTOC-LTT-Blocker';
            document.getElementsByTagName('body')[0].appendChild(lttBlocker);
        }

        if (shouldHideYTBackground) {

            setTimeout(() => {

                if (document.getElementsByTagName('html')[0]) {
                    document.getElementsByTagName('html')[0].style.backgroundColor = "transparent";
                }
                if (document.getElementsByTagName('body')[0]) {
                    document.getElementsByTagName('body')[0].style.backgroundColor = "transparent";
                }
                //special for yt
                if (document.getElementsByClassName('html5-video-player')[0]) {
                    document.getElementsByClassName('html5-video-player')[0].style.backgroundColor = "transparent";
                }
                //special for yttv
                if (overlayHostName == 'tv.youtube.com') {
                    if (document.getElementsByTagName('ytu-player-controller')[0]) {
                        document.getElementsByTagName('ytu-player-controller')[0].style.backgroundColor = "transparent";
                    }
                    let hideYTTVBlackBackgroundStyle = document.createElement("style");
                    hideYTTVBlackBackgroundStyle.textContent = `
                        ytu-player-layout.ytu-player-controller {
                            --ypl-player-video-backdrop-color: transparent !important;
                        }
                    `;
                    let insertLocation = document.getElementsByTagName('body')[0];
                    insertLocation.appendChild(hideYTTVBlackBackgroundStyle);
                }

            }, 1000); //wait a little because when a video plays initially it disapears for a sec and it looks janky for it to look like it flickers

        }

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

            //unmute if started out muted for yt
            if (overlayHostName == 'www.youtube.com') {

                if (document.getElementsByClassName('ytp-mute-button')[0] && document.querySelector('[title="Unmute (m)"]')) {
                    document.getElementsByClassName('ytp-mute-button')[0].click();
                }

                if (document.getElementsByClassName('ytp-pause-overlay-container')[0]) {
                    document.getElementsByClassName('ytp-pause-overlay-container')[0].remove();
                }

            }

            //TODO: add button on top of overlay video  if in live mode that asks if user would like video to play PiP while main video is not commercial, disapear if not clicked after x time

            //checking if video is paused even though it is just about about ready to play, indicating something is preventing it from doing so
            if (myYTOCVideo.paused && myYTOCVideo.readyState > 2) {

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
            if (commercialDetectionMode === 'auto-audio') {

                //waiting another second to give new tab a chance to load
                setTimeout(() => {

                    var stream;
                    try {
                        if (myYTOCVideo.captureStream) {
                            stream = myYTOCVideo.captureStream();
                        } else if (myYTOCVideo.mozCaptureStream) {
                            stream = myYTOCVideo.mozCaptureStream();
                        } else {
                            alert(`Message from YTOC Extension: Videos from ${overlayHostName} not eligible for overlay while in Audio Detection mode. Please try to use a different video source, a different Overlay Type, or a different Mode of Detection.`);
                            return;
                        }
                    } catch (error) {
                        console.error("YTOC: An error occurred while trying to captureStream:", error.message);
                        alert(`Message from YTOC Extension: Videos from ${overlayHostName} not eligible for overlay while in Audio Detection mode. Please try to use a different video source, a different Overlay Type, or a different Mode of Detection.`);
                        return;
                    }

                    let peer = new RTCPeerConnection();
                    let channel = new BroadcastChannel("video_stream");

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
                        .then(() => channel.postMessage({ offer: peer.localDescription.toJSON() }))
                        .catch(error => console.error("Sender: Error creating offer", error));

                    channel.onmessage = event => {
                        if (event.data.answer) {
                            peer.setRemoteDescription(new RTCSessionDescription(event.data.answer))
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

                }, 1000);

            }
            

        }, 2500);

    } //else do nothing, most likely script was injected into wrong frame

}

//plays or unmutes overlay video
function startCommercialState(overlayVideoType, overlayHostName, isOtherSiteTroubleshootMode) {

    //making sure if requested overlay video isn't a yt video and has same domain as main/background video that script wasn't loaded into that main video frame
    if (overlayHostName != 'www.youtube.com') {
        if (typeof mainVideoCollection !== 'undefined') {
            if (mainVideoCollection == document.getElementsByTagName('video')) {
                return;
            }
        }
    }

    if (window.location.hostname == overlayHostName || (isOtherSiteTroubleshootMode && overlayHostName != 'www.youtube.com')) {

        if (overlayHostName == 'www.youtube.com') {

            if (overlayVideoType == 'yt-live' && document.getElementsByClassName('ytp-mute-button')[0] && document.querySelector('[title="Unmute (m)"]')) {

                document.getElementsByClassName('ytp-mute-button')[0].click();

            } else if (overlayVideoType != 'yt-live' && document.getElementsByTagName('video')[0].paused) {

                document.getElementsByTagName('video')[0].play();

            }

        } else {

            if (overlayVideoType == 'other-live') {

                if (overlayHostName == 'tv.youtube.com' && document.querySelector('[aria-label="Unmute (m)"]')) {

                    document.querySelector('[aria-label="Unmute (m)"]').click();

                } else if (overlayHostName != 'tv.youtube.com') {

                    document.getElementsByTagName('video')[0].muted = false;

                }

            } else if (overlayHostName == 'tv.youtube.com' && document.querySelector('[aria-label="Play (k)"]')) {

                document.querySelector('[aria-label="Play (k)"]').click();

            } else if (document.getElementsByTagName('video')[0].paused) {

                document.getElementsByTagName('video')[0].play();

            }

        }

    } //else do nothing

}

//pauses or mutes overlay video
function stopCommercialState(overlayVideoType, overlayHostName, isOtherSiteTroubleshootMode) {

    //making sure if requested overlay video isn't a yt video and has same domain as main/background video that script wasn't loaded into that main video frame
    if (overlayHostName != 'www.youtube.com') {
        if (typeof mainVideoCollection !== 'undefined') {
            if (mainVideoCollection == document.getElementsByTagName('video')) {
                return;
            }
        }
    }

    if (window.location.hostname == overlayHostName || (isOtherSiteTroubleshootMode && overlayHostName != 'www.youtube.com')) {

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

                    document.getElementsByTagName('video')[0].muted = true;

                }

            } else if (overlayHostName == 'tv.youtube.com' && document.querySelector('[aria-label="Pause (k)"]')) {

                document.querySelector('[aria-label="Pause (k)"]').click();
                
            } else if (!document.getElementsByTagName('video')[0].paused) {

                document.getElementsByTagName('video')[0].pause();

            }

        }

    } //else do nothing

}


chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === "chrome-view-tab-video") {

        chromeViewTab(message, sender);

    } else if (message.action === "chrome-view-tab-audio") {

        chromeListenToTab(message, sender);

    }
});


async function chromeViewTab(message, sender) {

    await chrome.offscreen.createDocument({
        url: 'offscreen.html',
        reasons: ['USER_MEDIA'],
        justification: 'Recording tab in order to extract user selected pixel color'
    });

    const streamId = await chrome.tabCapture.getMediaStreamId({
        targetTabId: sender.tab.id
    });

    const constraints = {
        video: {
            mandatory: {
                chromeMediaSource: 'tab',
                chromeMediaSourceId: streamId,
                maxFrameRate: 4,
                minFrameRate: 4,
                maxWidth: message.windowDimensions.x,
                maxHeight: message.windowDimensions.y,
                minWidth: message.windowDimensions.x,
                minHeight: message.windowDimensions.y
            }
        }
    }

    chrome.runtime.sendMessage({
        target: 'offscreen',
        action: 'start-viewing',
        constraints: constraints
    });

}


async function chromeListenToTab(message, sender) {

    await chrome.offscreen.createDocument({
        url: 'offscreen.html',
        reasons: ['USER_MEDIA', 'AUDIO_PLAYBACK'],
        justification: 'Recording tab in order to extract audio'
    });

    const streamId = await chrome.tabCapture.getMediaStreamId({
        targetTabId: sender.tab.id
    });

    const constraints = {
        audio: {
            mandatory: {
                chromeMediaSource: 'tab',
                chromeMediaSourceId: streamId
            }
        },
        video: false
    }

    chrome.runtime.sendMessage({
        target: 'offscreen',
        action: 'start-listening',
        constraints: constraints
    });

}


chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === "capture_main_video_tab_id") {

        //saving tab id to chrome storage to avoid global variables clearing out in service worker //TODO: figure out if better way for this
        chrome.storage.sync.set({ mainVideoTabID: sender.tab.id });

    } else if (message.action === "background_update_preferences") {

        chrome.storage.sync.get(['mainVideoTabID'], (result) => {

            if (result.mainVideoTabID) {

                chrome.tabs.query({}, function (tabs) {

                    let exists = tabs.some(tab => tab.id === result.mainVideoTabID);
                    if (exists) {

                        chrome.tabs.sendMessage(result.mainVideoTabID, { action: "content_update_preferences" });

                    }

                });

            }

        });

    }
});


chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === "glimpse_spotify") {

        chrome.tabs.update(sender.tab.id, { active: true });

    } else if (message.action === "background_update_logo_text") {

        chrome.storage.sync.get(['mainVideoTabID'], (result) => {

            if (result.mainVideoTabID) {

                chrome.tabs.query({}, function (tabs) {

                    let exists = tabs.some(tab => tab.id === result.mainVideoTabID);
                    if (exists) {

                        chrome.tabs.sendMessage(result.mainVideoTabID, {
                            action: "content_update_logo_text",
                            text: message.text
                        });

                    }

                });

            }

        });

    } else if (message.action === "glimpse_main_tab") {

        chrome.storage.sync.get(['mainVideoTabID'], (result) => {

            if (result.mainVideoTabID) {

                chrome.tabs.query({}, function (tabs) {

                    let exists = tabs.some(tab => tab.id === result.mainVideoTabID);
                    if (exists) {

                        chrome.tabs.update(result.mainVideoTabID, { active: true });
                        chrome.tabs.sendMessage(result.mainVideoTabID, { action: "show_resume_fullscreen_message" });

                    }

                });

            }

        });

    }
});


chrome.runtime.onMessage.addListener(function (request, sender, sendResponse) {

    if (request.action === 'firefox-capture-screenshot') {

        //TODO: can I make this only capture the video so it doesn't matter if it is full screen (would need to work out the coordinates too) - I don't think this is possible?
        chrome.tabs.captureVisibleTab(

            sender.tab.windowId, //debug - replace with just null if this doesn't work
            {
                format: 'png'
                , rect: request.rect
            },
            function (dataUrl) {
                sendResponse({ imgSrc: dataUrl });
            }

        );

    }

    //return true to indicate that the response will be sent asynchronously
    return true;
    
    }
);


function rtcPlayAudio() {

    clearPage();
    addBannerMessage('Tab opened by YTOC extension to funnel overlay video audio through. Do not close until you are done using YTOC extension.');

    let peer = new RTCPeerConnection();
    let channel = new BroadcastChannel("video_stream");

    var receivedVideo;
    var isInitialDifferenceSet = false;
    var initialDifference;

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

}