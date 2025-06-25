
var isFirefox = false; //******************** remember to also update in background.js and overlay.js

var isCommercialState = false;
var firstClick = true;
var mainVideoCollection;
var isFirstRun = true;
var fullScreenAlertSet = false;
var overlayScreen;
var overlayVideo;
var isAutoModeInitiated = false;
var selectedPixel = null;
var isAutoModeFirstCommercial = true;
var mismatchCount = 0;
var matchCount = 0;
var cooldownCountRemaining = 8; //set to 8 for an initial cooldown so video won't display right away
var monitorIntervalID;
var originalPixelColor;
var windowDimensions;
var logoBoxText;
var countdownOngoing = false;
var pipBlocker;
var pipBlockerText;
var hasFontBeenInjected = false;

var overlayVideoType;
var ytPlaylistID;
var ytVideoID;
var ytLiveID;
var otherVideoURL;
var otherLiveURL;
var overlayHostName;
var mainVideoFade;
var videoOverlayWidth;
var videoOverlayHeight;
var overlayVideoLocationHorizontal;
var overlayVideoLocationVertical;
var mainVideoVolumeDuringCommercials;
var mainVideoVolumeDuringNonCommercials;
var clickBlocker1;
var clickBlocker2;
var nativeInlinePointerEvents;
var htmlElement;
var overlayInstructions;
var logoBox;
var commercialDetectionMode;
var mismatchCountThreshold;
var matchCountThreshold;
var colorDifferenceMatchingThreshold;
var manualOverrideCooldown;
var isDebugMode;
var haveLogoCountdown;
var logoCountdownMismatchesRemaining;
var isAudioOnlyOverlay;
var isLiveOverlayVideo;
var isPiPMode;
var pipLocationHorizontal;
var pipLocationVertical;
var pipHeight;
var pipWidth;
var audioLevelThreshold;
var audioLevelIndicatorContainer;
var audioLevelBar;
var audioLevelThresholdLine;
var shouldOverlayVideoSizeAndLocationAutoSet;
var shouldShuffleYTPlaylist;
//TODO: Add user preference for spotify to have audio come in gradually

//variables for Firefox auto audio commercial detection mode:
var stream;
var audioContext;
var audioSource;
var audioAnalyzer;
var audioDataArray;
var isAudioConnected = false;


//function that is responsible for loading the video iframe over top of the main/background video
function setOverlayVideo() {

    //TODO: add check to make sure user is still in full screen and if not to break and resut isFirstRun
    let insertLocation = document.fullscreenElement;
    if (insertLocation.nodeName == 'HTML') {
        insertLocation = document.getElementsByTagName('body')[0];
    }

    addOverlayFade(insertLocation);

    overlayVideo = document.createElement('div');
    overlayVideo.className = "ytoc-overlay-video";
    insertLocation.insertBefore(overlayVideo, null);
    overlayVideo.style.visibility = "visible";

    //TODO: Add option to auto set overlay video location and size based on selected pixel location for auto-pixel mode
    setOverlaySizeAndLocation(overlayVideo, videoOverlayWidth, videoOverlayHeight, overlayVideoLocationHorizontal, overlayVideoLocationVertical, "0");

    let url;
    if (overlayVideoType == 'yt-playlist') {
        url = "https://www.youtube.com/embed/?listType=playlist&amp;list=";
        url = url.concat(ytPlaylistID);
        if (shouldShuffleYTPlaylist) {
            let randomStart = Math.floor(Math.random() * 10) + 1;
            url += '&index=' + randomStart;
        }
    } else if (overlayVideoType == 'yt-video' || overlayVideoType == 'yt-live') {
        url = "https://www.youtube.com/embed/";
        if (overlayVideoType == 'yt-video') {
            url = url.concat(ytVideoID);
        } else {
            url = url.concat(ytLiveID);
        }
    } else if (overlayVideoType == 'other-video') {
        if (isFirefox) {
            if (overlayHostName === chrome.i18n.getMessage("@@extension_id")) {
                url = chrome.runtime.getURL('pixel-select-instructions.html') + '?purpose=overlay-video-container&video-url=' + otherVideoURL;
            } else {
                url = otherVideoURL;
            }
        } else {
            if (overlayHostName === chrome.runtime.id) {
                url = chrome.runtime.getURL('pixel-select-instructions.html') + '?purpose=overlay-video-container&video-url=' + otherVideoURL;
            } else {
                url = otherVideoURL;
            }
        }
    } else if (overlayVideoType == 'other-live') {
        url = otherLiveURL;
    }

    let iFrame = document.createElement('iframe');
    iFrame.src = url;
    iFrame.width = "100%";
    iFrame.height = "100%";
    iFrame.allow = "autoplay; encrypted-media";
    iFrame.frameBorder = "0";

    overlayVideo.appendChild(iFrame);

}


//adding an overlay to darken the main/background video during commercials if user has chosen to do so
function addOverlayFade(insertLocation) {

    if (mainVideoFade > 0) {

        overlayScreen = document.createElement('div');

        if (commercialDetectionMode.indexOf('auto-pixel') < 0) {

            overlayScreen.className = "ytoc-overlay-screen";
            overlayScreen.style.backgroundColor = "rgba(0, 0, 0, ." + mainVideoFade + ")";
            insertLocation.insertBefore(overlayScreen, null);

        } else if (selectedPixel) {

            overlayScreen.className = "ytoc-overlay-screen-with-hole";
            if (isFirefox) {
                //firefox does not need as large of a hole
                overlayScreen.style.setProperty("width", "6px", "important");
                overlayScreen.style.setProperty("height", "6px", "important");
            }
            //setting location of hole for the pixel color detector to look through, subtracting by 3 for radius of hole
            overlayScreen.style.left = (selectedPixel.x - 3) + 'px';
            overlayScreen.style.top = (selectedPixel.y - 3) + 'px';
            overlayScreen.style.boxShadow = "0 0 0 99999px rgba(0, 0, 0, ." + mainVideoFade + ")";
            insertLocation.insertBefore(overlayScreen, null);

        } else {
            //setting mainVideoFade to 0 to effectively shut it off since it is auto-pixel detection mode but I don't know where to put the hole
            mainVideoFade = 0;
        }

    }

}


function showOverlayFade() {

    if (mainVideoFade > 0) {
        if (commercialDetectionMode.indexOf('auto-pixel') < 0) {
            overlayScreen.style.backgroundColor = "rgba(0, 0, 0, ." + mainVideoFade + ")";
        } else {
            overlayScreen.style.boxShadow = "0 0 0 99999px rgba(0, 0, 0, ." + mainVideoFade + ")";
        }
    }

}


function hideOverlayFade() {

    if (mainVideoFade > 0) {
        if (commercialDetectionMode.indexOf('auto-pixel') < 0) {
            overlayScreen.style.backgroundColor = "transparent";
        } else {
            overlayScreen.style.boxShadow = "0 0 0";
        }
    }

}


//removes all elements on the page with a specific class name
function removeElementsByClass(className) {

    if (document.getElementsByClassName(className)[0]) {

        let elements = document.getElementsByClassName(className);
        let element;

        //doing this weird since getElementsByClassName returns a live collection
        while (element = elements[0]) {
            element.parentNode.removeChild(element);
        }

    }

}


function initialRun() {

    isCommercialState = true;
    isFirstRun = false;

    removeNotFullscreenAlerts();

    if (!isAudioOnlyOverlay) {
        setOverlayVideo();
    }

    if (commercialDetectionMode.indexOf('auto') < 0) {

        if (overlayVideoType == 'spotify') {
            //Note: this happens elsewhere in auto modes
            chrome.runtime.sendMessage({ action: "open_spotify" });
            window.addEventListener('beforeunload', closeSpotify);
        }

        //TODO: should this be moved above opening spotify?
        //Note: this happens in pixelSelection() in auto mode
        document.addEventListener('fullscreenchange', fullscreenChanged);

    }

    muteMainVideo();

    if (isAudioOnlyOverlay) {

        chrome.runtime.sendMessage({ action: "execute_music_commercial_state" });

        if (overlayVideoType == 'other-tabs') {
            window.addEventListener('beforeunload', stopMutingOtherTabs);
        }

    } else {

        if (commercialDetectionMode === 'auto-audio' && !isFirefox) {
            chrome.runtime.sendMessage({ action: "chrome_open_overlay_video_audio_tab" });
            window.addEventListener('beforeunload', closeOverlayVideoAudioTab);
        }

        //wait a little bit for the video to load //TODO: get indicator of when completely loaded
        setTimeout(() => {
            chrome.runtime.sendMessage({ action: "initial_execute_overlay_video_interaction" });
        }, 2000);

    }

}


function muteMainVideo() {

    //muting main/background video
    if (mainVideoVolumeDuringCommercials == 0) {

        if (commercialDetectionMode === 'auto-audio') {

            if (isFirefox) {

                if (isAudioConnected) {
                    audioSource.disconnect(audioContext.destination);
                    isAudioConnected = false;
                }

            } else {

                chrome.runtime.sendMessage({
                    target: "offscreen",
                    action: "disconnect-tab-audio"
                });

            }
            

        } else if (window.location.hostname == 'tv.youtube.com') {

            //using the actual controls to mute YTTV because for whatever reason, it will unmute itself
            if (document.querySelector('[aria-label="Mute (m)"]')) {

                document.querySelector('[aria-label="Mute (m)"]').click();

            }

        } else {

            for (let i = 0; i < mainVideoCollection.length; i++) {
                mainVideoCollection[i].muted = true; // Mute each video
            }

        }

    } else if (mainVideoVolumeDuringCommercials < 1 && commercialDetectionMode !== 'auto-audio') { //note: mainVideoVolumeDuringCommercials is a percentage and can't adjust exact main video audio level in auto-audio mode as the levels are being read

        for (let i = 0; i < mainVideoCollection.length; i++) {
            mainVideoCollection[i].volume = mainVideoVolumeDuringCommercials;
        }

    } //else do nothing for 100

}


function unmuteMainVideo() {

    if (mainVideoVolumeDuringCommercials == 0) {

        if (commercialDetectionMode === 'auto-audio') {

            if (isFirefox) {

                if (!isAudioConnected) {
                    audioSource.connect(audioContext.destination);
                    isAudioConnected = true;
                }

            } else {

                chrome.runtime.sendMessage({
                    target: "offscreen",
                    action: "connect-tab-audio"
                });

            }

        } else if (window.location.hostname == 'tv.youtube.com') {

            if (document.querySelector('[aria-label="Unmute (m)"]')) {

                document.querySelector('[aria-label="Unmute (m)"]').click();

            }

        } else {

            for (let i = 0; i < mainVideoCollection.length; i++) {
                mainVideoCollection[i].muted = false; // Mute each video
            }

        }

    } else if (mainVideoVolumeDuringCommercials < 1 && commercialDetectionMode !== 'auto-audio') { //note: mainVideoVolumeDuringCommercials is a percentage and can't adjust exact main video audio level in auto-audio mode as the levels are being read

        for (let i = 0; i < mainVideoCollection.length; i++) {
            mainVideoCollection[i].volume = mainVideoVolumeDuringNonCommercials;
        }

    } //else do nothing for 100

}


//switches to non-commercial state which means hiding the overlay video and unmuting the main video
function endCommercialMode() {

    isCommercialState = false;

    if (isAudioOnlyOverlay) {

        chrome.runtime.sendMessage({ action: "execute_music_non_commercial_state" });

    } else {

        chrome.runtime.sendMessage({ action: "execute_overlay_video_non_commercial_state" });

        if (isPiPMode && isLiveOverlayVideo && document.fullscreenElement) {
            enterPiPMode();
        } else {
            overlayVideo.style.visibility = "hidden";
        }

        hideOverlayFade();

    }

    unmuteMainVideo();

}


//switches to commercial state which means showing the overlay video and muting the main/background video
function startCommercialMode() {

    if (commercialDetectionMode.indexOf('auto') >= 0 && isAutoModeFirstCommercial) {

        //check again if in full screen in case user exited
        if (document.fullscreenElement) {

            isCommercialState = true;

            isAutoModeFirstCommercial = false;
            //setting cooldown time so video has a chance to play for the first time, also needed for overlay video audio to shift to other tab in auto-audio mode
            cooldownCountRemaining = 8;
            initialRun();

        } else {
            setNotFullscreenAlerts();
        }

    } else {

        isCommercialState = true;

        if (overlayVideoType == 'spotify' || overlayVideoType == 'other-tabs') {

            chrome.runtime.sendMessage({ action: "execute_music_commercial_state" });

        } else {

            chrome.runtime.sendMessage({ action: "execute_overlay_video_commercial_state" });

            showOverlayFade();

            if (isPiPMode && isLiveOverlayVideo) {
                exitPiPMode();
            }

            overlayVideo.style.visibility = "visible";

        }

        muteMainVideo();

    }

}


//TODO: make it so the manual override works before the video ever comes up on its own
//background.js is listening for user to enter in keyboard shortcut then sending a message to intiate this
chrome.runtime.onMessage.addListener(function (message) {

    if (message.action === "execute_manual_switch_function") {

        //special actions for the very first time this is initiated on a page
        if (isFirstRun && !isAutoModeInitiated) {

            if (!hasFontBeenInjected) {
                injectFontOntoPage();
            }

            //get overlayHostName
            //note: getting all other user set values later
            chrome.storage.sync.get(['overlayHostName'], (result) => {

                overlayHostName = result.overlayHostName ?? 'www.youtube.com';

                //extension can only be initiated for the first time if user is in full screen mode, this is needed to find out where to place the overlay video
                if (document.fullscreenElement) {

                    //TODO: look into why this would ever return iframe and why I'm stopping because of it - I think it is because if the iframe is fullscreened then that means something inside of it would also count as fullscreened, see espn.com/watch for example
                    if (document.fullscreenElement.nodeName != 'IFRAME') {

                        //grab all user set values
                        chrome.storage.sync.get([
                            'overlayVideoType',
                            'ytPlaylistID',
                            'ytVideoID',
                            'ytLiveID',
                            'otherVideoURL',
                            'otherLiveURL',
                            'mainVideoFade',
                            'videoOverlayWidth',
                            'videoOverlayHeight',
                            'overlayVideoLocationHorizontal',
                            'overlayVideoLocationVertical',
                            'mainVideoVolumeDuringCommercials',
                            'mainVideoVolumeDuringNonCommercials',
                            'commercialDetectionMode',
                            'mismatchCountThreshold',
                            'matchCountThreshold',
                            'colorDifferenceMatchingThreshold',
                            'manualOverrideCooldown',
                            'isDebugMode',
                            'isPiPMode',
                            'pipLocationHorizontal',
                            'pipLocationVertical',
                            'pipHeight',
                            'pipWidth',
                            'audioLevelThreshold',
                            'shouldOverlayVideoSizeAndLocationAutoSet',
                            'shouldShuffleYTPlaylist'
                        ], (result) => {

                            //set them to default if not set by user yet
                            overlayVideoType = result.overlayVideoType ?? 'yt-playlist';
                            if (overlayVideoType == 'spotify' || overlayVideoType == 'other-tabs') {
                                isAudioOnlyOverlay = true;
                                isLiveOverlayVideo = false;
                            } else if (overlayVideoType == 'yt-live' || overlayVideoType == 'other-live') {
                                isAudioOnlyOverlay = false;
                                isLiveOverlayVideo = true;
                            } else {
                                isAudioOnlyOverlay = false;
                                isLiveOverlayVideo = false;
                            }
                            ytPlaylistID = result.ytPlaylistID ?? 'PLt982az5t-dVn-HDI4D7fnvMXt8T9_OGB';
                            ytVideoID = result.ytVideoID ?? '5AMQbxBZohY';
                            ytLiveID = result.ytLiveID ?? 'QhJcIlE0NAQ';
                            otherVideoURL = result.otherVideoURL ?? 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/TearsOfSteel.mp4';
                            otherLiveURL = result.otherLiveURL ?? 'https://tv.youtube.com/watch/_2ONrjDR7S8';
                            mainVideoFade = result.mainVideoFade ?? 65;
                            mainVideoVolumeDuringCommercials = result.mainVideoVolumeDuringCommercials ?? 0; //TODO: get this to work for .01-.99 values for yttv
                            mainVideoVolumeDuringNonCommercials = result.mainVideoVolumeDuringNonCommercials ?? 100; //TODO: get this to work for .01-.99 values for yttv
                            if (mainVideoVolumeDuringCommercials > 0) {
                                mainVideoVolumeDuringCommercials = mainVideoVolumeDuringCommercials / 100;
                            }
                            if (mainVideoVolumeDuringNonCommercials > 0) {
                                mainVideoVolumeDuringNonCommercials = mainVideoVolumeDuringNonCommercials / 100;
                            }
                            commercialDetectionMode = result.commercialDetectionMode ?? 'auto-pixel-normal';
                            //adjusting to updated settings for people that have already downloaded the extension (people set to opposite pixel mode will need to reselect in updated settings)
                            if (commercialDetectionMode === 'auto') {
                                commercialDetectionMode = 'auto-pixel-normal';
                            }
                            shouldOverlayVideoSizeAndLocationAutoSet = result.shouldOverlayVideoSizeAndLocationAutoSet ?? false;
                            if (commercialDetectionMode.indexOf('auto-pixel') < 0) {
                                shouldOverlayVideoSizeAndLocationAutoSet = false;
                            }
                            //explaination for below: sometimes the instructions don't need to take up the whole page because there is no video overlay or the video overlay is auto set
                            //note: no instructions and overlay video are needed for auto-audio mode with isAudioOnlyOverlay, but we don't want to replace the user set settings since we indirectly read them to place the audio indicator
                            if ((isAudioOnlyOverlay && commercialDetectionMode !== 'auto-audio') || shouldOverlayVideoSizeAndLocationAutoSet) {
                                overlayVideoLocationHorizontal = 'middle';
                                overlayVideoLocationVertical = 'middle';
                                videoOverlayWidth = 50;
                                videoOverlayHeight = 50;
                            } else {
                                overlayVideoLocationHorizontal = result.overlayVideoLocationHorizontal ?? 'middle';
                                overlayVideoLocationVertical = result.overlayVideoLocationVertical ?? 'middle';
                                videoOverlayWidth = result.videoOverlayWidth ?? 75;
                                videoOverlayHeight = result.videoOverlayHeight ?? 75;
                            }
                            mismatchCountThreshold = result.mismatchCountThreshold ?? 8;
                            matchCountThreshold = result.matchCountThreshold ?? 2;
                            colorDifferenceMatchingThreshold = result.colorDifferenceMatchingThreshold ?? 14;
                            manualOverrideCooldown = result.manualOverrideCooldown ?? 120;
                            isDebugMode = result.isDebugMode ?? false;
                            isPiPMode = result.isPiPMode ?? true;
                            pipLocationHorizontal = result.pipLocationHorizontal ?? 'top';
                            pipLocationVertical = result.pipLocationVertical ?? 'left';
                            pipHeight = result.pipHeight ?? 20;
                            pipWidth = result.pipWidth ?? 20;
                            audioLevelThreshold = result.audioLevelThreshold ?? 5;
                            shouldShuffleYTPlaylist = result.shouldShuffleYTPlaylist ?? false;

                            chrome.runtime.sendMessage({ action: "capture_main_video_tab_id" });
                            mainVideoCollection = document.getElementsByTagName('video');

                            if (overlayVideoLocationVertical == 'bottom' || shouldOverlayVideoSizeAndLocationAutoSet) {
                                hideVerticleScrollbar();
                            }

                            //setting up for pixel selection for auto mode or continuing run for manual
                            if (commercialDetectionMode.indexOf('auto-pixel') >= 0) {

                                if (!isAutoModeInitiated) {

                                    isAutoModeInitiated = true;

                                    windowDimensions = { x: window.innerWidth, y: window.innerHeight };
                                    startViewingTab(windowDimensions);

                                    document.addEventListener('fullscreenchange', abortPixelSelection);

                                    //give a split sec for recording to start before asking user to pick a pixel
                                    setTimeout(() => {
                                        setBlockersAndPixelSelectionInstructions();
                                        document.addEventListener('click', pixelSelection);
                                    }, 500);

                                }

                            } else if (commercialDetectionMode == 'auto-audio') {

                                if (!isAutoModeInitiated) {

                                    isAutoModeInitiated = true;

                                    startListeningToTab();

                                    //give a split sec for recording to start before asking user to pick a pixel
                                    setTimeout(() => {
                                        prepForAudioMonitor();
                                    }, 500);

                                }

                            } else {

                                initialRun();

                            }

                        });

                    } //else do nothing for when nodeName is IFRAME

                } else if (overlayHostName == 'www.youtube.com') { //TODO: find a better way to not show this warning on overlay video when using non-yt videos and maybe not even let it get to this point. 
                    //TODO: Also displays some sort of alert / warning when user tries to use over top of actual www.youtube.com
                    //since user was not in full screen, instruct them that they need to be

                    setNotFullscreenAlerts();

                }

            });

        } else if (commercialDetectionMode.indexOf('auto-pixel') >= 0 && !selectedPixel) {
            abortPixelSelection();
        } else {

            if (isCommercialState) {

                endCommercialMode();

                if (!isDebugMode) {
                    if (commercialDetectionMode.indexOf('auto-pixel') >= 0) {
                        logoBox.style.display = 'none';
                    } else if (commercialDetectionMode === 'auto-audio') {
                        audioLevelIndicatorContainer.style.display = 'none';
                    } //else don't need to hide for auto mode
                }

            } else {

                startCommercialMode();

                if (isAudioOnlyOverlay) {
                    if (commercialDetectionMode.indexOf('auto-pixel') >= 0) {
                        logoBox.style.display = 'block';
                    } else if (commercialDetectionMode === 'auto-audio') {
                        audioLevelIndicatorContainer.style.display = 'flex';
                    } //else don't show for auto mode
                }

            }

            //set cooldown period so auto doesn't switch mode for user defined amount of time
            cooldownCountRemaining = manualOverrideCooldown;

        }

    }

});


//lets the user know that they need to be fullscreen for the extension to work
//TODO: does this need modified or removed now that everything pauses?
function setNotFullscreenAlerts() {

    if (!fullScreenAlertSet) {

        addMessageAlertToMainVideo('Video must be full screen for Live Commercial Blocker extension to work.');
        fullScreenAlertSet = true;

    }

}


//remove all full screen alerts if previously set
//TODO: rename this and set fullScreenAlertSet elsewhere?
function removeNotFullscreenAlerts() {

    removeElementsByClass('ytoc-main-video-message-alert');
    fullScreenAlertSet = false;

}


//sets specific message over top of every video on the page
function addMessageAlertToMainVideo(message) {

    if (document.getElementsByTagName('video')[0]) {

        let potentialVideos = document.getElementsByTagName('video');

        for (let i = 0; i < potentialVideos.length; i++) {

            let elm = document.createElement('div');
            elm.className = "ytoc-main-video-message-alert";
            elm.textContent = message;

            let insertLocation = potentialVideos[i].parentNode;
            insertLocation = insertLocation.parentNode;
            insertLocation.insertBefore(elm, null);

        }

    }

}


//sets blockers so users cursor movement doesn't trigger any of the main/background video's UI to display and keeps click from pausing video
//also displays instructions to user for selecting pixel
function setBlockersAndPixelSelectionInstructions() {

    clickBlocker1 = document.createElement('div');
    clickBlocker1.className = "ytoc-click-blocker";

    let insertLocation = document.getElementsByTagName('body')[0];
    insertLocation.insertBefore(clickBlocker1, null);

    let insertLocationFullscreenElm = document.fullscreenElement;

    //TODO: figure out better way to suppress UI from showing if there is a mousemove event on the top level full screen element like for vimeo
    //insertLocationFullscreenElm.classList.add("ytoc-click-blocker-addition");

    if (insertLocationFullscreenElm.nodeName == 'HTML') {
        insertLocationFullscreenElm = document.getElementsByTagName('body')[0];
    }

    clickBlocker2 = document.createElement('div');
    clickBlocker2.className = "ytoc-click-blocker";

    insertLocationFullscreenElm.insertBefore(clickBlocker2, null);

    //adding extra level of click blocking and mouse interference when inside iframe
    if (inIFrame()) {

        htmlElement = document.getElementsByTagName('html')[0];
        nativeInlinePointerEvents = htmlElement.style.pointerEvents;
        htmlElement.style.pointerEvents = 'none';

    }

    if (isPiPMode && isLiveOverlayVideo) {

        pipBlocker = document.createElement('div');
        pipBlocker.className = "ytoc-overlay-instructions";
        pipBlocker.style.backgroundColor = "rgb(240, 238, 236)";
        
        insertLocationFullscreenElm.insertBefore(pipBlocker, null);
        pipBlockerText = document.createElement('div');
        pipBlockerText.style.color = "black";
        pipBlockerText.style.fontSize = "16px";
        pipBlockerText.style.fontFamily = '"Montserrat", sans-serif';
        pipBlockerText.style.textShadow = "none";
        pipBlockerText.style.padding = "5px";
        if (pipLocationVertical == 'bottom') {
            pipBlockerText.style.position = "absolute";
            pipBlockerText.style.bottom = "0";
        }
        pipBlockerText.textContent = "PiP Location - Disable PiP or change PiP location/size in extension settings (advanced) if covering desired logo/graphic.";
        pipBlocker.appendChild(pipBlockerText);
        setOverlaySizeAndLocation(pipBlocker, pipWidth, pipHeight, pipLocationHorizontal, pipLocationVertical, "5px");

    }

    overlayInstructions = document.createElement('div');
    overlayInstructions.className = "ytoc-overlay-instructions";
    insertLocationFullscreenElm.insertBefore(overlayInstructions, null);
    overlayInstructions.style.visibility = "visible";
    //overlayInstructions.style.setProperty("border", "3px red solid", "important");
    setOverlaySizeAndLocation(overlayInstructions, videoOverlayWidth, videoOverlayHeight, overlayVideoLocationHorizontal, overlayVideoLocationVertical, "0");

    let iFrame = document.createElement('iframe');
    let iFrameSource = chrome.runtime.getURL('pixel-select-instructions.html');
    if (commercialDetectionMode === 'auto-pixel-opposite') {
        iFrameSource = iFrameSource + '?purpose=opposite-mode-instructions';
    }
    iFrame.src = iFrameSource;
    iFrame.width = "100%";
    iFrame.height = "100%";
    iFrame.allow = "autoplay; encrypted-media";
    iFrame.frameBorder = "0";
    //iFrame.style.setProperty("border", "3px red solid", "important");

    overlayInstructions.appendChild(iFrame);

}


//hides verticle scrollbar because on some websites if the overlay video is placed on the bottom, it adds a scrollbar
function hideVerticleScrollbar() {

    let body = document.getElementsByTagName('body')[0];

    let hideScollStyle = document.createElement("style");
    hideScollStyle.textContent = `
        ::-webkit-scrollbar {
            display: none;
        }
    `;
    body.appendChild(hideScollStyle);

    if (isFirefox) {
        if (document.getElementsByTagName('html')[0]) {
            //TODO: I believe scrollbar-width is experimental and not supported with all firefox versions, I should try to find something else
            document.getElementsByTagName('html')[0].style.scrollbarWidth = "none";
        }
        if (document.getElementsByTagName('body')[0]) {
            document.getElementsByTagName('body')[0].style.scrollbarWidth = "none";
        }
    }

}


function removeBlockersListenersAndPixelSelectionInstructions() {

    removeNotFullscreenAlerts();

    removeElementsByClass('ytoc-overlay-instructions');

    //remove help cursor right away
    clickBlocker1.style.setProperty("cursor", "none", "important");
    clickBlocker2.style.setProperty("cursor", "none", "important");

    document.removeEventListener('fullscreenchange', abortPixelSelection);
    document.removeEventListener('click', pixelSelection);

    //wait a sec to remove the click blocker so UI doesn't pop up right away
    setTimeout(() => {
        removeElementsByClass('ytoc-click-blocker');
        if (inIFrame()) {
            htmlElement.style.pointerEvents = nativeInlinePointerEvents;
        }
    }, 5000);

}


function pixelSelection(event) {

    //TODO: figure out if this check is really necessary
    if (!selectedPixel) {

        if (isFirefox) {
            selectedPixel = { x: event.clientX, y: event.clientY };
        } else {
            //subtracting by a couple so it doesn't accidentally capture the cursor in chromium
            selectedPixel = { x: (event.clientX - 1), y: (event.clientY - 2) };
        }

        removeBlockersListenersAndPixelSelectionInstructions();

        indicateSelectedPixel(selectedPixel);

        document.addEventListener('fullscreenchange', fullscreenChanged);

        //TODO: create user option to turn off logo completely
        setCommercialDetectedIndicator(selectedPixel);

        captureOriginalPixelColor(selectedPixel);

    }

}


//grabs the color of the of the user set pixel at time of selection so it can use it to compare in subsequent checks
function captureOriginalPixelColor(selectedPixel) {

    getPixelColor(selectedPixel).then(function (pixelColor) {

        //establish original pixel color
        originalPixelColor = pixelColor;

        logoBox.style.backgroundColor = "rgba(" + originalPixelColor.r + ", " + originalPixelColor.g + ", " + originalPixelColor.b + ", 1)";
        //deciding whether to set text as white or black based on background color
        if ((originalPixelColor.r * 0.299 + originalPixelColor.g * 0.587 + originalPixelColor.b * 0.114) > 150) {
            logoBox.style.color = "rgba(0, 0, 0, 1)";
        } else {
            logoBox.style.color = "rgba(255, 255, 255, 1)";
        }

        if (shouldOverlayVideoSizeAndLocationAutoSet) {
            autoUpdateOverlayVideoSizeAndLocationValues(selectedPixel);
        }

        //wait a sec to remove pixel selected message and replace with logo to let the user read message
        setTimeout(() => {
            initialLogoBoxTextUpdate();
            if (!isDebugMode) { logoBox.style.display = 'none'; }
            removeElementsByClass('ytoc-selection-indicator');
        }, 2000);

        if (overlayVideoType == 'spotify') {
            //if user has extension set to spotify, open spotify now and prompt the user to choose music to play
            setTimeout(() => {
                chrome.runtime.sendMessage({ action: "open_spotify" });
                window.addEventListener('beforeunload', closeSpotify);
            }, 2000);
        } else if (overlayVideoType == 'other-tabs') {
            //if user has extension set to other-tabs, mute the other tabs now
            chrome.runtime.sendMessage({ action: "execute_music_non_commercial_state" });
        }

        pixelColorMatchMonitor(originalPixelColor, selectedPixel);

    })
        .catch(function (error) {
            console.error(error);
        });

}


//checks the color of the user set pixel and compares it to the original color in intervals and initiates commercial or non-commercial mode accordingly
function pixelColorMatchMonitor(originalPixelColor, selectedPixel) {

    monitorIntervalID = setInterval(() => {

        getPixelColor(selectedPixel).then(function (pixelColor) {

            let redDifference = Math.abs(originalPixelColor.r - pixelColor.r);
            let greenDifference = Math.abs(originalPixelColor.g - pixelColor.g);
            let blueDifference = Math.abs(originalPixelColor.b - pixelColor.b);

            //TODO: Create HSL option
            let match;
            if (
                redDifference > colorDifferenceMatchingThreshold ||
                greenDifference > colorDifferenceMatchingThreshold ||
                blueDifference > colorDifferenceMatchingThreshold
            ) {
                match = false;
            } else {
                match = true;
            }

            if ((commercialDetectionMode === 'auto-pixel-normal' && !match) || (commercialDetectionMode === 'auto-pixel-opposite' && match)) {
                //color indicating potential commercial break

                mismatchCount++;
                matchCount = 0;
                logoCountdownMismatchesRemaining = (mismatchCountThreshold - mismatchCount);

                //show countdown if 3 seconds until commercial mode or it would be 3 seconds until commercial mode and cooldown is blocking
                if (logoCountdownMismatchesRemaining <= 3 && !isCommercialState) {

                    if ((cooldownCountRemaining >= 1) && (cooldownCountRemaining > logoCountdownMismatchesRemaining)) {

                        logoBox.textContent = cooldownCountRemaining;
                        logoBox.style.display = 'block';
                        countdownOngoing = true;

                    } else if (logoCountdownMismatchesRemaining >= 1) {

                        logoBox.textContent = logoCountdownMismatchesRemaining;
                        logoBox.style.display = 'block';
                        countdownOngoing = true;

                    } else {
                        countdownOngoing = false;
                    }

                } else {
                    countdownOngoing = false;
                }

                if (mismatchCount >= mismatchCountThreshold && cooldownCountRemaining <= 0) {

                    if (!isCommercialState) {

                        if (isDebugMode) { console.log('commercial detected'); }

                        startCommercialMode();

                        logoBox.textContent = logoBoxText;
                        if (commercialDetectionMode === 'auto-pixel-normal') {
                            logoBox.style.color = "rgba(" + pixelColor.r + ", " + pixelColor.g + ", " + pixelColor.b + ", 1)";
                        }
                        logoBox.style.display = 'block';
                        if (!isDebugMode && !isAudioOnlyOverlay) {

                            setTimeout(() => {

                                logoBox.style.display = 'none';

                            }, 5000);

                        }

                    }

                    //TODO: find out if this is better inside the if above or here, especially as it relates to manual switching during auto mode
                    mismatchCount = 0;

                }

            } else {
                //color indicating potentially out of commercial break

                matchCount++;
                mismatchCount = 0;

                //TODO: is this the best way to do this considering audio and video options?
                if (!isDebugMode && !isCommercialState) {
                    logoBox.style.display = 'none';
                }

                countdownOngoing = false;
                logoBox.textContent = logoBoxText;

                if (matchCount >= matchCountThreshold && cooldownCountRemaining <= 0) {

                    if (isCommercialState) {

                        if (isDebugMode) { console.log('commercial undetected'); }

                        if (isAudioOnlyOverlay) {
                            if (isDebugMode) {
                                logoBoxText = 'LIVE COMMERCIAL BLOCKER';
                                logoBox.textContent = logoBoxText;
                            } else {
                                logoBox.style.display = 'none';
                            }
                        }

                        endCommercialMode();

                    }

                    //TODO: find out if this is better inside the if above or here, especially as it relates to manual switching during auto mode
                    matchCount = 0;

                }

            }

            if (commercialDetectionMode === 'auto-pixel-normal') {
                logoBox.style.color = "rgba(" + pixelColor.r + ", " + pixelColor.g + ", " + pixelColor.b + ", 1)";
            }

            cooldownCountRemaining--;

        })
            .catch(function (error) {
                console.error(error);
            });

    }, 1000);

}


//grabs color of plugged in pixel by asking background.js to take a screenshot of said pixel
function getPixelColor(coordinates) {

    return new Promise(function (resolve, reject) {

        if (isFirefox) {

            let rect = { x: coordinates.x, y: coordinates.y, width: 1, height: 1 };

            chrome.runtime.sendMessage({ action: "firefox-capture-screenshot", rect: rect }, function (response) {

                let image = new Image();
                image.src = response.imgSrc;

                image.addEventListener('load', function () {

                    let canvas = document.createElement('canvas');
                    let context = canvas.getContext('2d');

                    canvas.width = image.width; //TODO: figure out is this necessary with setting it in draw image?
                    canvas.height = image.height;
                    context.drawImage(image, 0, 0);

                    let pixelColor = context.getImageData(0, 0, 1, 1).data;
                    pixelColor = { r: pixelColor[0], g: pixelColor[1], b: pixelColor[2] };

                    resolve(pixelColor); // Resolve the promise with pixelColor value

                });

            });

        } else {

            chrome.runtime.sendMessage({
                target: "offscreen",
                action: "capture-screenshot",
                coordinates: coordinates
            }, function (response) {

                //console.log(response.myCoordinates); //debug-high
                //console.log(response.pixelColor); //debug-high
                //console.log(response.image); //debug-high

                resolve(response.pixelColor);

            });

        }

    });

}


function prepForAudioMonitor() {

    setAudioLevelIndicator();

    //wait a sec to remove initiated message to let the user read message before replacing with logo
    setTimeout(() => {
        initialLogoBoxTextUpdate();
        if (!isDebugMode) { audioLevelIndicatorContainer.style.display = 'none'; }
    }, 2000);

    document.addEventListener('fullscreenchange', fullscreenChanged);

    if (overlayVideoType == 'spotify') {
        //if user has extension set to spotify, open spotify now and prompt the user to choose music to play
        setTimeout(() => {
            chrome.runtime.sendMessage({ action: "open_spotify" });
            window.addEventListener('beforeunload', closeSpotify);
        }, 2000);
    } else if (overlayVideoType == 'other-tabs') {
        //if user has extension set to other-tabs, mute the other tabs now
        chrome.runtime.sendMessage({ action: "execute_music_non_commercial_state" });
    }

    audioThresholdMonitor();

}


function setAudioLevelIndicator() {

    //TODO: add check to make sure user is still in fullscreen mode
    let insertLocation = document.fullscreenElement;
    if (insertLocation.nodeName == 'HTML') {
        insertLocation = document.getElementsByTagName('body')[0];
    }

    audioLevelIndicatorContainer = document.createElement('div');
    audioLevelIndicatorContainer.className = "ytoc-audio-level-indicator-container";
    audioLevelIndicatorContainer.style.display = 'flex';

    //TODO: let user specifically chose location or at least give them option to disable completely
    let audioLevelIndicatorContainerLocationHorizontal;
    if (overlayVideoLocationHorizontal === 'middle' || overlayVideoLocationHorizontal === 'right') {
        audioLevelIndicatorContainerLocationHorizontal = 'left';
    } else {
        audioLevelIndicatorContainerLocationHorizontal = 'right';
    }

    let audioLevelIndicatorContainerLocationVertical;
    if (overlayVideoLocationVertical === 'middle' || overlayVideoLocationVertical === 'bottom') {
        audioLevelIndicatorContainerLocationVertical = 'top';
    } else {
        audioLevelIndicatorContainerLocationVertical = 'bottom';
    }

    setOverlaySizeAndLocation(audioLevelIndicatorContainer, false, false, audioLevelIndicatorContainerLocationHorizontal, audioLevelIndicatorContainerLocationVertical, "0")

    let audioLevelIndicator = document.createElement('div');
    audioLevelIndicator.className = "ytoc-audio-level-indicator";
    audioLevelIndicatorContainer.appendChild(audioLevelIndicator);

    audioLevelBar = document.createElement('div');
    audioLevelBar.className = "ytoc-audio-level-indicator-bar";
    audioLevelIndicator.appendChild(audioLevelBar);

    audioLevelThresholdLine = document.createElement('div');
    audioLevelThresholdLine.className = "ytoc-audio-level-indicator-threshold";
    audioLevelThresholdLine.style.bottom = audioLevelThreshold + '%';
    audioLevelIndicator.appendChild(audioLevelThresholdLine);

    logoBox = document.createElement('div');
    logoBox.className = "ytoc-audio-level-indicator-countdown";
    logoBoxText = 'Live Commercial Blocker Initiated';
    logoBox.textContent = logoBoxText;
    if (audioLevelIndicatorContainerLocationHorizontal === 'right') {
        audioLevelIndicatorContainer.insertBefore(logoBox, audioLevelIndicator);
    } else {
        audioLevelIndicatorContainer.appendChild(logoBox);
    }

    insertLocation.insertBefore(audioLevelIndicatorContainer, null);

}



//checks the audio level and compares it to the audio level threshold and initiates commercial or non-commercial mode accordingly
function audioThresholdMonitor() {

    monitorIntervalID = setInterval(() => {
        
        getAudioLevel().then(function (audioLevel) {

            setAudioLevelBar(audioLevel);

            if (audioLevel < audioLevelThreshold) {
                //low audio level indicating potential commercial break

                mismatchCount++;
                matchCount = 0;
                logoCountdownMismatchesRemaining = (mismatchCountThreshold - mismatchCount);

                //show countdown if 3 seconds until commercial mode or it would be 3 seconds until commercial mode and cooldown is blocking
                if (logoCountdownMismatchesRemaining <= 3 && !isCommercialState) {

                    if ((cooldownCountRemaining >= 1) && (cooldownCountRemaining > logoCountdownMismatchesRemaining)) {

                        logoBox.textContent = cooldownCountRemaining;
                        audioLevelIndicatorContainer.style.display = 'flex';
                        countdownOngoing = true;

                    } else if (logoCountdownMismatchesRemaining >= 1) {

                        logoBox.textContent = logoCountdownMismatchesRemaining;
                        audioLevelIndicatorContainer.style.display = 'flex';
                        countdownOngoing = true;

                    } else {
                        countdownOngoing = false;
                    }

                } else {
                    countdownOngoing = false;
                }

                if (mismatchCount >= mismatchCountThreshold && cooldownCountRemaining <= 0) {

                    if (!isCommercialState) {

                        if (isDebugMode) { console.log('commercial detected'); }

                        startCommercialMode();

                        logoBox.textContent = logoBoxText;
                        audioLevelIndicatorContainer.style.display = 'flex';
                        if (!isDebugMode && !isAudioOnlyOverlay) {

                            setTimeout(() => {
                                audioLevelIndicatorContainer.style.display = 'flex';
                            }, 5000);

                        }

                    }

                    //TODO: find out if this is better inside the if above or here, especially as it relates to manual switching during auto mode
                    mismatchCount = 0;

                }

            } else {
                //high audio level indicating potentially out of commercial break

                matchCount++;
                mismatchCount = 0;

                if (!isDebugMode && !isCommercialState) {
                    audioLevelIndicatorContainer.style.display = 'none';
                }

                countdownOngoing = false;
                logoBox.textContent = logoBoxText;

                if (matchCount >= matchCountThreshold && cooldownCountRemaining <= 0) {

                    if (isCommercialState) {

                        if (isDebugMode) { console.log('commercial undetected'); }

                        if (isAudioOnlyOverlay) {
                            if (isDebugMode) {
                                logoBoxText = 'LIVE COMMERCIAL BLOCKER';
                                logoBox.textContent = logoBoxText;
                            } else {
                                audioLevelIndicatorContainer.style.display = 'none';
                            }
                        }

                        endCommercialMode();

                    }

                    matchCount = 0;

                }

            }

            cooldownCountRemaining--;

        })
        .catch(function (error) {
            console.error(error);
        });

    }, 1000);

}


//gets current audio level of tab from offscreen
function getAudioLevel() {

    return new Promise(function (resolve, reject) {

        if (isFirefox) {

            audioAnalyzer.getByteFrequencyData(audioDataArray);
            let volumeSum = 0;
            for (const volume of audioDataArray) {
                volumeSum += volume;
            }
            let averageVolume = volumeSum / audioDataArray.length;
            let audioLevel = Math.round(averageVolume * 100 / 127);

            resolve(audioLevel);

        } else {

            chrome.runtime.sendMessage({
                target: "offscreen",
                action: "capture-audio-level"
            }, function (response) {
                resolve(response.audioLevel);
            });

        }

    });

}

function setAudioLevelBar(level) {
    audioLevelBar.style.height = level + '%';
    audioLevelBar.style.backgroundColor = level < audioLevelThreshold ? 'rgb(140, 179, 210, 0.9)' : 'red';
}


//sets element to show user color differences next to selected pixel when commercial is detected
function setCommercialDetectedIndicator(selectedPixel) {

    //TODO: add check to make sure user is still in fullscreen mode
    let insertLocation = document.fullscreenElement;
    if (insertLocation.nodeName == 'HTML') {
        insertLocation = document.getElementsByTagName('body')[0];
    }

    logoBox = document.createElement('div');
    logoBox.className = "ytoc-logo";
    logoBoxText = 'PIXEL SELECTED!';
    logoBox.textContent = logoBoxText;
    logoBox.style.display = 'block';

    let windowWidth = window.innerWidth;

    if (selectedPixel.x < windowWidth / 2) {
        //user clicked on the left side of the page
        logoBox.style.left = (selectedPixel.x + 10) + 'px';
        logoBox.style.right = 'auto';
    } else {
        //user clicked on the right side of the page
        logoBox.style.right = (windowWidth - selectedPixel.x + 10) + 'px';
        logoBox.style.left = 'auto';
    }

    logoBox.style.top = (selectedPixel.y - 15) + 'px';

    insertLocation.insertBefore(logoBox, null);

}


function initialLogoBoxTextUpdate() {

    if (!isAudioOnlyOverlay || isDebugMode) {
        logoBoxText = 'LIVE COMMERCIAL BLOCKER';
    } else if (overlayVideoType == 'spotify') {
        logoBoxText = 'Playing Spotify'; //TODO: Maybe also set this to Live Commercial Blocker
    } else if (overlayVideoType == 'other-tabs') {
        logoBoxText = "\uD83D\uDD0A"; //speaker with three sound waves symbol
    }
    logoBox.textContent = logoBoxText;

}

function spotifyLogoBoxUpdate(text) {

    logoBoxText = text;

    //strangley, an unnecessary delay feels smoother here
    setTimeout(() => {
        if (!countdownOngoing) {
            logoBox.textContent = logoBoxText;
        }
    }, 2000);

    if (isCommercialState) {

        if (commercialDetectionMode.indexOf('auto-pixel') >= 0) {
            logoBox.style.display = 'block';
        } else {
            audioLevelIndicatorContainer.style.display = 'flex';
        }

        //TODO: either add user preference to always show song title during commercial even when not in debug mode or just do it and have this timeout set logo to black or white
        if (!isDebugMode && commercialDetectionMode !== 'auto-audio') {
            setTimeout(() => {
                logoBoxText = "\uD83D\uDD0A"; //speaker with three sound waves symbol
                logoBox.textContent = logoBoxText;
            }, 10000);
        }

    }

}


//detects if content script is running inside an iframe, should work for cross domain and same domain iframes
function inIFrame() {
    try {
        return window.self !== window.top;
    } catch (e) {
        return true;
    }
}


//TODO: figure out peacock refresh
//calls background.js to create an offscreen document and grabs the getMediaStreamId of the tab to send to the offscreen document which then starts recording the tab
function startViewingTab(windowDimensions) {

    if (!isFirefox) {

        chrome.runtime.sendMessage({ action: "chrome-view-tab-video", windowDimensions: windowDimensions });
        window.addEventListener('beforeunload', stopViewingTab);

    }

}


function startListeningToTab() {

    if (!isFirefox) {

        chrome.runtime.sendMessage({ action: "chrome-view-tab-audio" });
        window.addEventListener('beforeunload', stopViewingTab);

    } else {

        try {

            //grab first video with an audio track
            for (const video of mainVideoCollection) {
                const audioTracks = video.srcObject?.getAudioTracks() || [];
                if (audioTracks.length === 0) {

                    try {
                        stream = video.mozCaptureStream();
                    } catch (e) {
                        stream = video.captureStream();
                    }

                    audioContext = new AudioContext();
                    audioSource = audioContext.createMediaStreamSource(stream);
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

                    return;
                    
                }
            }

        } catch (error) {
            console.error("Live Commercial Blocker: An error occurred while trying to captureStream:", error.message);
            clearInterval(monitorIntervalID);
            alert(`Message from Live Commercial Blocker Extension: Videos from ${window.location.hostname} not compatible with Audio Detection mode on Firefox. Please try a different Mode of Detection.`);
            return;
        }

    }

}


function stopViewingTab() {

    if (!isFirefox) {

        //close offscreen
        chrome.runtime.sendMessage({
            target: "offscreen",
            action: "close"
        });

        window.removeEventListener('beforeunload', stopViewingTab);

    }

}


//note: should use stopViewingTab() instead to close offscreen
function pauseViewingTab() {

    if (!isFirefox) {

        chrome.runtime.sendMessage({
            target: "offscreen",
            action: "stop-viewing"
        });

    }

}


//note: does not currently work, need to close and reopen offscreen in order to pause and resume viewing tab
function resumeViewingTab() {

    if (!isFirefox) {

        chrome.runtime.sendMessage({
            target: "offscreen",
            action: "resume-viewing"
        });

    }

}


function fullscreenChanged() {

    if (!document.fullscreenElement) {

        if (commercialDetectionMode.indexOf('auto-pixel') >= 0) {
            logoBox.style.display = 'none';
            pauseAutoMode();
        } else if (commercialDetectionMode == 'auto-audio') {
            audioLevelIndicatorContainer.style.display = 'none';
            pauseAutoMode();
        }

        if (isCommercialState && !isAudioOnlyOverlay) {
            endCommercialMode();
        }

        if (isPiPMode && isLiveOverlayVideo && !isCommercialState) {
            overlayVideo.style.visibility = "hidden";
        }

        //TODO: should I be doing it this way?
        if (overlayVideoType == 'other-tabs') {
            chrome.runtime.sendMessage({ action: "execute_music_commercial_state" });
        }

    } else if (document.fullscreenElement) {

        removeElementsByClass('ytoc-main-video-message-alert');

        if (commercialDetectionMode.indexOf('auto-pixel') >= 0) {
            resumeAutoMode();
            if (isDebugMode) { logoBox.style.display = 'block'; }
        } else if (commercialDetectionMode == 'auto-audio') {
            resumeAutoMode();
            if (isDebugMode) { audioLevelIndicatorContainer.style.display = 'flex'; }
        }

        if ((overlayVideoType == 'spotify' && !isCommercialState) || overlayVideoType == 'other-tabs') {
            chrome.runtime.sendMessage({ action: "execute_music_non_commercial_state" });
        }

    }

}


function pauseAutoMode() {
    clearInterval(monitorIntervalID);
    stopViewingTab();

    let pauseMessage = 'Live Commercial Blocker extension paused. Set video back to fullscreen to resume.';
    if (overlayVideoType === 'spotify') {
        pauseMessage += ' Or refresh page to exit extension and remove message.';
    } else {
        pauseMessage += ' This message will disappear shortly.';
    }
    addMessageAlertToMainVideo(pauseMessage);

    //TODO: add removal timeout directly to addMessageAlertToMainVideo to make all messages disappear?
    //TODO: get this working for the spotify mode without accidentally removing the success message after user chooses spotify playlist
    if (overlayVideoType !== 'spotify') {
        setTimeout(() => {
            removeElementsByClass('ytoc-main-video-message-alert');
        }, 9000);
    }
}


function resumeAutoMode() {

    if (commercialDetectionMode.indexOf('auto-pixel') >= 0) {
        pixelColorMatchMonitor(originalPixelColor, selectedPixel);
        startViewingTab(windowDimensions); //TODO: move this up one line?
        cooldownCountRemaining = 8; //give a chance for video UI to go away
    } else if (commercialDetectionMode === 'auto-audio') {
        startListeningToTab();
        audioThresholdMonitor();
    }
    
}


function abortPixelSelection() {

    isAutoModeInitiated = false;

    removeBlockersListenersAndPixelSelectionInstructions();
    
    //close offscreen.js
    chrome.runtime.sendMessage({
        target: "offscreen",
        action: "close"
    });

    window.removeEventListener('beforeunload', stopViewingTab);
    document.removeEventListener('fullscreenchange', abortPixelSelection);

    let abortMessage;
    if (!document.fullscreen) {
        abortMessage = 'Pixel selection aborted! Go back to full screen and hit keyboard shortcut to start again. This message will disappear shortly.';
    } else {
        abortMessage = 'Pixel selection aborted! Hit keyboard shortcut to start again. This message will disappear shortly.';
    }
    addMessageAlertToMainVideo(abortMessage);

    setTimeout(() => {
        removeElementsByClass('ytoc-main-video-message-alert');
    }, 7000);

}


//circles the selected pixel in a red ring
function indicateSelectedPixel(selectedPixel) {

    //TODO: add check to make sure user is still in full screen and if not to break and resut isFirstRun
    let insertLocation = document.fullscreenElement;
    if (insertLocation.nodeName == 'HTML') {
        insertLocation = document.getElementsByTagName('body')[0];
    }

    let selectedPixelRing = document.createElement('div');

    selectedPixelRing.className = "ytoc-selection-indicator";
    if (isFirefox) {
        //firefox does not need as large of a hole
        selectedPixelRing.style.setProperty("width", "6px", "important");
        selectedPixelRing.style.setProperty("height", "6px", "important");
    }
    //setting location of hole for the pixel color detector to look through, subtracting by 3 for radius of hole
    selectedPixelRing.style.left = (selectedPixel.x - 3) + 'px';
    selectedPixelRing.style.top = (selectedPixel.y - 3) + 'px';

    insertLocation.insertBefore(selectedPixelRing, null);

}


function closeOverlayVideoAudioTab() {
    chrome.runtime.sendMessage({ action: "close_overlay_video_audio_tab" });
}


function closeSpotify() {
    chrome.runtime.sendMessage({ action: "close_spotify" });
}


chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
    if (message.action == 'content_update_logo_text') {

        //ignore this message if not in necessary frame
        if (!mainVideoCollection) {
            return;
        }

        if (commercialDetectionMode.indexOf('auto') >= 0) {

            spotifyLogoBoxUpdate(message.text);

        } //else no need to update logo if not in auto mode

    } else if (message.action == 'show_resume_fullscreen_message') {

        //ignore this message if not in necessary frame
        if (!mainVideoCollection) {
            return;
        }

        //TODO: add removeElementsByClass('ytoc-main-video-message-alert') into addMessageAlertToMainVideo() function
        removeElementsByClass('ytoc-main-video-message-alert');
        addMessageAlertToMainVideo('Success! You may now resume fullscreen and enjoy :)');

    } else if (message.action == 'content_update_preferences') {

        //ignore this message if not in necessary frame
        if (!mainVideoCollection) {
            return;
        }

        if (!isFirstRun) {

            //grab all user set values
            //note: this is an async function
            //TODO: figure out how to update all the preferences that I'm not updating here after extension has already been initiated
            chrome.storage.sync.get([
                'mismatchCountThreshold',
                'matchCountThreshold',
                'colorDifferenceMatchingThreshold',
                'manualOverrideCooldown',
                'pipLocationHorizontal',
                'pipLocationVertical',
                'pipHeight',
                'pipWidth',
                'audioLevelThreshold'
            ], (result) => {

                //set them to default if not set by user yet
                mismatchCountThreshold = result.mismatchCountThreshold ?? 8;
                matchCountThreshold = result.matchCountThreshold ?? 2;
                colorDifferenceMatchingThreshold = result.colorDifferenceMatchingThreshold ?? 12;
                manualOverrideCooldown = result.manualOverrideCooldown ?? 30;
                pipLocationHorizontal = result.pipLocationHorizontal ?? 'left';
                pipLocationVertical = result.pipLocationVertical ?? 'top';
                pipHeight = result.pipHeight ?? 20;
                pipWidth = result.pipWidth ?? 20;
                audioLevelThreshold = result.audioLevelThreshold ?? 5;

                if (audioLevelThresholdLine) {
                    audioLevelThresholdLine.style.bottom = audioLevelThreshold + '%';
                }

                //removeElementsByClass('ytoc-main-video-message-alert');
                //addMessageAlertToMainVideo('Preferences Updated! You may now resume fullscreen and enjoy :)');

            });

        } //else do not update preferences because this gets updated on first run anyway

    }
});


function stopMutingOtherTabs() {

    chrome.runtime.sendMessage({ action: "execute_music_commercial_state" });

}


function setOverlaySizeAndLocation(overlay, widthPercentage, heightPercentage, xLocation, yLocation, spacerStyleValue) {

    if (widthPercentage) {
        overlay.style.setProperty("width", widthPercentage + "%", "important");
    }
    if (heightPercentage) {
        overlay.style.setProperty("height", heightPercentage + "%", "important");
    }

    if (xLocation == 'left' || xLocation == 'middle') {
        overlay.style.setProperty("left", spacerStyleValue, "important");
    }
    if (xLocation == 'right' || xLocation == 'middle') {
        overlay.style.setProperty("right", spacerStyleValue, "important");
    }
    if (yLocation == 'top' || yLocation == 'middle') {
        overlay.style.setProperty("top", spacerStyleValue, "important");
    }
    if (yLocation == 'bottom' || yLocation == 'middle') {
        overlay.style.setProperty("bottom", spacerStyleValue, "important");
    }

}


//tries to mimic browser PiP mode as firefox does not have a PiP API and chrome's only works when triggered by user action
function enterPiPMode() {

    overlayVideo.style.removeProperty("right");
    overlayVideo.style.removeProperty("left");
    overlayVideo.style.removeProperty("bottom");
    overlayVideo.style.removeProperty("top");

    //TODO: remove the 7px gap and and then update the scrollbar hiding to account for piplocationvertical, pipmode, and islivevideo -- or make the gap a user setting?
    setOverlaySizeAndLocation(overlayVideo, pipWidth, pipHeight, pipLocationHorizontal, pipLocationVertical, "7px");

}


function exitPiPMode() {

    overlayVideo.style.removeProperty("right");
    overlayVideo.style.removeProperty("left");
    overlayVideo.style.removeProperty("bottom");
    overlayVideo.style.removeProperty("top");

    setOverlaySizeAndLocation(overlayVideo, videoOverlayWidth, videoOverlayHeight, overlayVideoLocationHorizontal, overlayVideoLocationVertical, "0");

}


function autoUpdateOverlayVideoSizeAndLocationValues(selectedPixel) {

    videoOverlayWidth = 100;
    overlayVideoLocationHorizontal = 'middle';

    let windowHeight = window.innerHeight;

    let belowSelectedPixelBuffer = 8;
    let aboveSelectedPixelBuffer = 4;
    if (isFirefox) {
        belowSelectedPixelBuffer = 4;
    }

    if (selectedPixel.y < windowHeight / 2) {
        overlayVideoLocationVertical = 'bottom';
        videoOverlayHeight = 100 - (((selectedPixel.y + belowSelectedPixelBuffer) / windowHeight) * 100).toFixed(3); //keeping 8px of room to view pixel and don't want to go below 0 in case user selected from very top //TODO: set differently for firefox?
    } else {
        overlayVideoLocationVertical = 'top';
        videoOverlayHeight = (((selectedPixel.y - aboveSelectedPixelBuffer) / windowHeight) * 100).toFixed(3); //keeping 4px of room to view pixel and don't want to go below 0 in case user selected from very top
    }

}


function injectFontOntoPage() {
    let fontInjectionStyle = document.createElement("style");
    fontInjectionStyle.textContent = `@import url('https://fonts.googleapis.com/css2?family=Montserrat:ital,wght@0,700;1,700&display=swap');`;
    let insertLocation = document.getElementsByTagName('body')[0];
    insertLocation.appendChild(fontInjectionStyle);

    hasFontBeenInjected = true;
}