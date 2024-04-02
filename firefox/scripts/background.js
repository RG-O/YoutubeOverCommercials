
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
        chrome.storage.sync.get(['shouldHideYTBackground', 'overlayHostName'], (result) => {

            let shouldHideYTBackground = result.shouldHideYTBackground ?? true;
            let overlayHostName = result.overlayHostName ?? 'www.youtube.com';

            //TODO: inject an entire js file into the overlay video and then message functions in it, would that be better?
            //injecting initialCommercialState() into all frames on the active tab
            chrome.scripting.executeScript({
                target: { tabId: sender.tab.id, allFrames: true },
                func: initialCommercialState,
                args: [shouldHideYTBackground, overlayHostName]
            });

        });

    } else if (message.action === "execute_overlay_video_non_commercial_state") {

        //grab user set values
        chrome.storage.sync.get(['overlayVideoType', 'overlayHostName'], (result) => {

            let overlayVideoType = result.overlayVideoType ?? 'yt-playlist';
            let overlayHostName = result.overlayHostName ?? 'www.youtube.com';

            //injecting stopCommercialState() into all frames on the active tab
            chrome.scripting.executeScript({
                target: { tabId: sender.tab.id, allFrames: true },
                func: stopCommercialState,
                args: [overlayVideoType, overlayHostName]
            });

        });

        

    } else if (message.action === "execute_overlay_video_commercial_state") {

        //grab user set values
        chrome.storage.sync.get(['overlayVideoType', 'overlayHostName'], (result) => {

            let overlayVideoType = result.overlayVideoType ?? 'yt-playlist';
            let overlayHostName = result.overlayHostName ?? 'www.youtube.com';

            //injecting startCommercialState() into all frames on the active tab
            chrome.scripting.executeScript({
                target: { tabId: sender.tab.id, allFrames: true },
                func: startCommercialState,
                args: [overlayVideoType, overlayHostName]
            });

        });

    }
});


function initialCommercialState(shouldHideYTBackground, overlayHostName) {

    //making sure if requested overlay video isn't a yt video and has same domain as main/background video that script wasn't loaded into that main video frame
    if (overlayHostName != 'www.youtube.com') {
        if (typeof mainVideo !== 'undefined') {
            if (mainVideo == document.getElementsByTagName('video')[0]) {
                return;
            }
        }
    }

    //making sure frame has the requested hostname of the overlay video so this doesn't accidentaly impact the main/background video
    if (window.location.hostname == overlayHostName) {

        //initial click or play on the overlay video
        if (overlayHostName == 'www.youtube.com' && document.getElementsByClassName('video-stream html5-main-video')[0]) {
            document.getElementsByClassName('video-stream html5-main-video')[0].click();
        } else if (overlayHostName != 'tv.youtube.com') {
            document.getElementsByTagName('video')[0].play();
        } //else do nothing because yttv plays automatically
        

        if (shouldHideYTBackground) {

            setTimeout(() => {
                //TODO: do special background hiding for yttv
                if (document.getElementsByClassName('html5-video-player')[0]) {
                    document.getElementsByClassName('html5-video-player')[0].style.backgroundColor = "transparent";
                }
                if (document.getElementsByTagName('body')[0]) {
                    document.getElementsByTagName('body')[0].style.backgroundColor = "transparent";
                }
            }, 1000); //wait a little because when a video plays initially it disapears for a sec and it looks janky for it to look like it flickers

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
            
            
            //checking if video is paused even though it is just about about ready to play, indicating something is preventing it from doing so
            if (myYTOCVideo.paused && myYTOCVideo.readyState > 2) {

                let elm = document.createElement("div");
                elm.textContent = "Detected that video cannot auto start due to reasons. Please manually play video, pause video, and then play video again. Doing so will allow the extension to work properly from here on out. Sorry for the inconvenience! This message will soon disapear."
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
                        }`

                    elm.appendChild(fadeStyle);

                    setTimeout(() => {
                        elm.remove();
                    }, 15000);

                }, 15000);
                
            }

        }, 2500);
        
    } //else do nothing, most likely script was injected into wrong frame

}

//plays or unmutes overlay video
function startCommercialState(overlayVideoType, overlayHostName) {

    //making sure if requested overlay video isn't a yt video and has same domain as main/background video that script wasn't loaded into that main video frame
    if (overlayHostName != 'www.youtube.com') {
        if (typeof mainVideo !== 'undefined') {
            if (mainVideo == document.getElementsByTagName('video')[0]) {
                return;
            }
        }
    }

    if (window.location.hostname == overlayHostName) {

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

            } else {

                if (document.getElementsByTagName('video')[0].paused) {

                    document.getElementsByTagName('video')[0].play();

                }

            }

        }

    } //else do nothing

}

//pauses or mutes overlay video
function stopCommercialState(overlayVideoType, overlayHostName) {

    //making sure if requested overlay video isn't a yt video and has same domain as main/background video that script wasn't loaded into that main video frame
    if (overlayHostName != 'www.youtube.com') {
        if (typeof mainVideo !== 'undefined') {
            if (mainVideo == document.getElementsByTagName('video')[0]) {
                return;
            }
        }
    }

    if (window.location.hostname == overlayHostName) {

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

            } else {

                if (!document.getElementsByTagName('video')[0].paused) {

                    document.getElementsByTagName('video')[0].pause();

                }

            }

        }

    } //else do nothing

}
