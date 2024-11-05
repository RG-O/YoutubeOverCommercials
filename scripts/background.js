
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

    }
});


function initialCommercialState(shouldHideYTBackground, overlayHostName) {

    //making sure if requested overlay video isn't a yt video and has same domain as main/background video that script wasn't loaded into that main video frame
    if (overlayHostName != 'www.youtube.com') {
        if (typeof mainVideoCollection !== 'undefined') {
            //TODO: is this second check necessary if we already know mainVideoCollection is defined? would the frames share this variable?
            if (mainVideoCollection == document.getElementsByTagName('video')) {
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

        }, 2500);

    } //else do nothing, most likely script was injected into wrong frame

}

//plays or unmutes overlay video
function startCommercialState(overlayVideoType, overlayHostName) {

    //making sure if requested overlay video isn't a yt video and has same domain as main/background video that script wasn't loaded into that main video frame
    if (overlayHostName != 'www.youtube.com') {
        if (typeof mainVideoCollection !== 'undefined') {
            if (mainVideoCollection == document.getElementsByTagName('video')) {
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

            } else if (overlayHostName == 'tv.youtube.com' && document.querySelector('[aria-label="Play (k)"]')) {

                document.querySelector('[aria-label="Play (k)"]').click();

            } else if (document.getElementsByTagName('video')[0].paused) {

                document.getElementsByTagName('video')[0].play();

            }

        }

    } //else do nothing

}

//pauses or mutes overlay video
function stopCommercialState(overlayVideoType, overlayHostName) {

    //making sure if requested overlay video isn't a yt video and has same domain as main/background video that script wasn't loaded into that main video frame
    if (overlayHostName != 'www.youtube.com') {
        if (typeof mainVideoCollection !== 'undefined') {
            if (mainVideoCollection == document.getElementsByTagName('video')) {
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

            } else if (overlayHostName == 'tv.youtube.com' && document.querySelector('[aria-label="Pause (k)"]')) {

                document.querySelector('[aria-label="Pause (k)"]').click();
                
            } else if (!document.getElementsByTagName('video')[0].paused) {

                document.getElementsByTagName('video')[0].pause();

            }

        }

    } //else do nothing

}


chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === "chrome-view-tab") {

        chromeViewTab(message, sender);

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