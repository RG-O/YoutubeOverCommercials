
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

        chrome.scripting.executeScript({
            target: { tabId: sender.tab.id, allFrames: true },
            files: ["scripts/overlay.js"]
        });

    } else if (message.action === "execute_overlay_video_non_commercial_state") {

        chrome.tabs.sendMessage(sender.tab.id, { action: "overlay_non_commercial_state" });

    } else if (message.action === "execute_overlay_video_commercial_state") {

        chrome.tabs.sendMessage(sender.tab.id, { action: "overlay_commercial_state" });

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

    } else if (message.action === "chrome_open_overlay_video_audio_tab") {

        //grab user set values
        chrome.storage.sync.get(['overlayHostName'], (result) => {

            let overlayHostName = result.overlayHostName ?? 'www.youtube.com';
            let url;
            if (overlayHostName === chrome.runtime.id) {
                url = chrome.runtime.getURL('pixel-select-instructions.html') + '?purpose=rtc';
            } else {
                url = 'https://' + overlayHostName;
            }

            //since in auto-audio detection mode, open tab using the same domain as the overlay video so I can funnel audio from the overlay video through this tab as to not trigger audio detection
            //TODO: can I iframe this in offscreen.html instead? As an additional tab would not be needed and audio playing in offscreen doesn't seem to count towards the tab audio
            chrome.tabs.create({
                pinned: true,
                active: false,
                url: url,
            },
                (tab) => {

                    chrome.storage.sync.set({ overlayVideoAudioTabID: tab.id });

                    //note: if new tab is pixel-select-instructions.html, the rtc.js gets injected differently
                    if (overlayHostName !== chrome.runtime.id) {

                        setTimeout(() => {

                            chrome.scripting.executeScript({
                                target: { tabId: tab.id, allFrames: false },
                                files: ["scripts/rtc.js"]
                            });

                        }, 500);

                    }

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


chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === "chrome-view-tab-video") {

        let aiMode = false;
        chromeViewTab(message, sender, aiMode);

    } else if (message.action === "chrome-view-tab-video-ai-openai") {

        let aiMode = 'openai';
        chromeViewTab(message, sender, aiMode);

    } else if (message.action === "chrome-view-tab-audio") {

        chromeListenToTab(message, sender);

    }
});


async function chromeViewTab(message, sender, aiMode) {

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

    if (!aiMode) {
        chrome.runtime.sendMessage({
            target: 'offscreen',
            action: 'start-viewing',
            constraints: constraints
        });
    } else if (aiMode === 'openai') {
        chrome.storage.sync.get(['openAIAPIKey'], (result) => {
            let openAIAPIKey = result.openAIAPIKey ?? false;
            chrome.runtime.sendMessage({
                target: 'offscreen',
                action: 'start-viewing-ai-openai',
                api: openAIAPIKey,
                constraints: constraints
            });
        });
    }

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

            sender.tab.windowId,
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
