
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
var isAmazonPrimeVideo;
var pixelSelectionEventType = 'click';
var commercialTimerStartTime;
var commercialTimerEndTime;

var overlayVideoType;
var ytPlaylistID;
var ytVideoID;
var ytLiveID;
var otherVideoURL;
var otherLiveURL;
var overlayHostName;
var isOtherSiteTroubleshootMode;
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
var windowWidth;
var windowHeight;
//TODO: Add user preference for spotify to have audio come in gradually

//Advanced Logo Analysis Variables
var advancedLogoSelectionTopLeftLocation;
var advancedLogoSelectionBottomRightLocation;
var advancedLogoSelectionDimensions;
var advancedLogoSelectionBox;
var requiredAdvancedLogoMaskCollectionSamples = 8;
var advancedLogoMaskCollectionSamples = 0;
var advancedLogoMatchThreshold = 0.63; //note: will be lowered slightly if color logo detected
var advancedLogoMismatchThreshold = 0.33; //note: will be lowered slightly if color logo detected
var advancedLogoInfoContainer;
var advancedLogoEdgeImage;
var advancedLogoFinalMaskImage;
//var advancedLogoInsideLogoColorImageDebug; //debug-high
var hasMaskCompleteMessageBeenDismissed = false;
var consecutiveAdvancedLogoAnalysisCallFailures = 0;
var isAdvancedLogoMonitorPaused = false;
var isColorLogo = false;

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
    iFrame.allow = "autoplay; encrypted-media; local-network-access;"; //after Chrome version 142 update, need local-network-access so permissions prompt occurs for stremio and maybe others
    iFrame.frameBorder = "0";

    overlayVideo.appendChild(iFrame);

}


function removeOverlayVideo() {
    overlayVideo.remove();
    overlayScreen.remove();
}


//adding an overlay to darken the main/background video during commercials if user has chosen to do so
function addOverlayFade(insertLocation) {

    if (mainVideoFade > 0) {

        overlayScreen = document.createElement('div');

        if (commercialDetectionMode.indexOf('auto-pixel') < 0) {

            overlayScreen.className = "ytoc-overlay-screen";
            overlayScreen.style.backgroundColor = "rgba(0, 0, 0, ." + mainVideoFade + ")";
            insertLocation.insertBefore(overlayScreen, null);

        } else if (commercialDetectionMode === 'auto-pixel-advanced-logo') {

            overlayScreen.className = "ytoc-overlay-screen-with-hole";
            overlayScreen.style.setProperty("width", `${advancedLogoSelectionDimensions.width}px`, "important");
            overlayScreen.style.setProperty("height", `${advancedLogoSelectionDimensions.height}px`, "important");
            //setting location of hole for the advanced logo detector to look through
            overlayScreen.style.setProperty("left", `${advancedLogoSelectionTopLeftLocation.x}px`, "important");
            overlayScreen.style.setProperty("top", `${advancedLogoSelectionTopLeftLocation.y}px`, "important");
            overlayScreen.style.boxShadow = "0 0 0 99999px rgba(0, 0, 0, ." + mainVideoFade + ")";
            insertLocation.insertBefore(overlayScreen, null);

        } else if (selectedPixel) {

            overlayScreen.className = "ytoc-overlay-screen-with-hole";
            overlayScreen.style.setProperty("border-radius", "50%", "important");
            if (isFirefox) {
                //firefox does not need as large of a hole
                overlayScreen.style.setProperty("width", "6px", "important");
                overlayScreen.style.setProperty("height", "6px", "important");
            } else {
                overlayScreen.style.setProperty("width", "10px", "important");
                overlayScreen.style.setProperty("height", "10px", "important");
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

        let overlayInjectionTimeout;
        if (isOtherSiteTroubleshootMode) {
            //wait longer to inject overlay.js for potentially iframes loading inside iframes
            overlayInjectionTimeout = 5000;
        } else {
            overlayInjectionTimeout = 1000;
        }
        //wait a little bit for the video to load //TODO: get indicator of when completely loaded
        setTimeout(() => {
            chrome.runtime.sendMessage({ action: "initial_execute_overlay_video_interaction" });
        }, overlayInjectionTimeout);

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
    stopCommercialTimer();

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

    startCommercialTimer();

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
                            'isOtherSiteTroubleshootMode',
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
                            isOtherSiteTroubleshootMode = result.isOtherSiteTroubleshootMode ?? false;
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
                            colorDifferenceMatchingThreshold = result.colorDifferenceMatchingThreshold ?? 16;
                            manualOverrideCooldown = result.manualOverrideCooldown ?? 45;
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

                                    windowWidth = window.innerWidth;
                                    windowHeight = window.innerHeight;
                                    windowDimensions = { x: windowWidth, y: windowHeight };
                                    startViewingTab(windowDimensions);

                                    document.addEventListener('fullscreenchange', abortPixelSelection);

                                    //give a split sec for recording to start before asking user to pick a pixel
                                    setTimeout(() => {
                                        //TODO: should what I'm doing for amazon be done everywhere?
                                        if (window.location.hostname === 'www.amazon.com') {
                                            isAmazonPrimeVideo = true;
                                            pixelSelectionEventType = 'mouseup';
                                        } else {
                                            isAmazonPrimeVideo = false;
                                            pixelSelectionEventType = 'click';
                                        }

                                        setBlockersAndPixelSelectionInstructions();
                                        if (commercialDetectionMode === 'auto-pixel-advanced-logo') {
                                            document.addEventListener('mousedown', fullLogoSelectionInitiation);
                                        } else {
                                            document.addEventListener(pixelSelectionEventType, pixelSelection);
                                        }
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
                        if (commercialDetectionMode !== 'auto-pixel-advanced-logo') {
                            logoBox.style.display = 'none';
                        } else {
                            advancedLogoInfoContainer.style.display = 'none';
                        }
                    } else if (commercialDetectionMode === 'auto-audio') {
                        audioLevelIndicatorContainer.style.display = 'none';
                    } //else don't need to hide for manual mode
                }

            } else {

                startCommercialMode();

                //hide logo for non audio overlays and not debug mode
                if (isAudioOnlyOverlay) {
                    if (commercialDetectionMode.indexOf('auto-pixel') >= 0) {
                        if (commercialDetectionMode !== 'auto-pixel-advanced-logo') {
                            logoBox.style.display = 'block';
                        } else {
                            advancedLogoInfoContainer.style.display = 'flex';
                        }
                    } else if (commercialDetectionMode === 'auto-audio') {
                        audioLevelIndicatorContainer.style.display = 'flex';
                    }
                } else if (!isDebugMode) {
                    if (commercialDetectionMode.indexOf('auto-pixel') >= 0) {
                        if (commercialDetectionMode !== 'auto-pixel-advanced-logo') {
                            logoBox.style.display = 'none';
                        } else {
                            advancedLogoInfoContainer.style.display = 'none';
                        }
                    } else if (commercialDetectionMode === 'auto-audio') {
                        audioLevelIndicatorContainer.style.display = 'none';
                    }
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

    htmlElement = document.getElementsByTagName('html')[0];

    //adding extra level of click blocking and mouse interference when inside iframe
    if (inIFrame() && htmlElement) {
        nativeInlinePointerEvents = htmlElement.style.pointerEvents;
        htmlElement.style.pointerEvents = 'none';
    }

    //add additional click blocker to html element if on amazon prime to prevent UI from coming up. TODO: should I do this for all sites and not just amazon?
    if (isAmazonPrimeVideo && htmlElement) {
        htmlElement.addEventListener('click', blockHandler, true);
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
    } else if (commercialDetectionMode === 'auto-pixel-advanced-logo') {
        iFrameSource = iFrameSource + '?purpose=advanced-logo-mode-instructions';
    }
    iFrame.src = iFrameSource;
    iFrame.width = "100%";
    iFrame.height = "100%";
    iFrame.allow = "autoplay; encrypted-media;";
    iFrame.frameBorder = "0";
    //iFrame.style.setProperty("border", "3px red solid", "important");

    overlayInstructions.appendChild(iFrame);

    //TODO: do this everywhere and not just for amazon?
    if (isAmazonPrimeVideo) {
        for (const video of mainVideoCollection) {
            video.style.zIndex = '2147483645';
        }
    }
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
    if (commercialDetectionMode === 'auto-pixel-advanced-logo') {
        document.removeEventListener('mousedown', fullLogoSelectionInitiation);
    } else {
        document.removeEventListener(pixelSelectionEventType, pixelSelection);
    }

    if (isAmazonPrimeVideo) {
        //TODO: set this to only run once so I don't have to remove?
        htmlElement.removeEventListener('click', blockHandler, true);
    }

    let removeBlockersDelay = 0;
    if (document.fullscreenElement) {
        removeBlockersDelay = 5000;
        if (commercialDetectionMode === 'auto-pixel-advanced-logo') {
            //wait until logo mask is complete to remove click and UI blockers
            removeBlockersDelay = (requiredAdvancedLogoMaskCollectionSamples * 1000) + 2000;
        }
    }
    //wait a sec to remove the click blocker so UI doesn't pop up right away. not waiting if not fullscreen, meaning montoring has paused or ended.
    setTimeout(() => {
        removeClickAndUIBlockers();
    }, removeBlockersDelay);

}


function removeClickAndUIBlockers() {
    removeElementsByClass('ytoc-click-blocker');

    if (inIFrame()) {
        htmlElement.style.pointerEvents = nativeInlinePointerEvents;
    }

    if (isAmazonPrimeVideo) {
        for (const video of mainVideoCollection) {
            video.style.removeProperty('z-index');
        }
    }
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

        let selectedPixelGridLocation = getSelectedPixelGridLocation(selectedPixel);

        //TODO: create user option to turn off logo completely
        setCommercialDetectedIndicator(selectedPixel, selectedPixelGridLocation);

        if (shouldOverlayVideoSizeAndLocationAutoSet) {
            autoUpdateOverlayVideoSizeAndLocationValues(selectedPixel, selectedPixelGridLocation);
        }

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

                        if (overlayVideoType == 'spotify') {
                            logoBoxText = 'PLAYING SPOTIFY'
                        }
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


function fullLogoSelectionInitiation(event) {
    //TODO: figure out if this check is really necessary
    if (!selectedPixel) {
        let startX = event.clientX;
        let startY = event.clientY;

        advancedLogoSelectionBox = document.createElement("div");
        advancedLogoSelectionBox.className = 'ytoc-advanced-logo-selection-box';
        advancedLogoSelectionBox.style.left = `${startX}px`;
        advancedLogoSelectionBox.style.top = `${startY}px`;

        //TODO: add check to make sure user is still in full screen and if not to break and resut isFirstRun
        let insertLocation = document.fullscreenElement;
        if (insertLocation.nodeName == 'HTML') {
            insertLocation = document.getElementsByTagName('body')[0];
        }
        insertLocation.insertBefore(advancedLogoSelectionBox, null);

        //note: mousedown listener for fullLogoSelectionInitiation removed later in removeBlockersListenersAndPixelSelectionInstructions()

        document.addEventListener('mousemove', function (event) {
            fullLogoSelectionBoxResize(event, startX, startY);
        });
        //note: this is set to only run once so it does not need removed later
        document.addEventListener('mouseup', function (event) {
            fullLogoSelectionCompletion(event, startX, startY);
        }, { once: true });
    }
}


function fullLogoSelectionBoxResize(event, startX, startY) {
    const x = Math.min(event.clientX, startX);
    const y = Math.min(event.clientY, startY);
    const width = Math.abs(event.clientX - startX);
    const height = Math.abs(event.clientY - startY);

    advancedLogoSelectionBox.style.left = `${x}px`;
    advancedLogoSelectionBox.style.top = `${y}px`;
    advancedLogoSelectionBox.style.width = `${width}px`;
    advancedLogoSelectionBox.style.height = `${height}px`;
}


function fullLogoSelectionCompletion(event, startX, startY) {
    document.removeEventListener('mousemove', fullLogoSelectionBoxResize);
    advancedLogoSelectionBox.remove();
    
    const endX = event.clientX;
    const endY = event.clientY;

    let topLeftX = Math.min(startX, endX);
    let topLeftY = Math.min(startY, endY);
    if (!isFirefox) {
        //adjusting as chrome always seems a pixel off
        topLeftX += 2;
        topLeftY += 2;
    }
    const bottomRightX = Math.max(startX, endX);
    const bottomRightY = Math.max(startY, endY);
    const width = bottomRightX - topLeftX;
    const height = bottomRightY - topLeftY;
    if (width < 4 || height < 4) {
        abortPixelSelection();
        alert('Must select larger area. Remember to click and drag to select area.');
        return;
    }
    advancedLogoSelectionTopLeftLocation = { x: topLeftX, y: topLeftY };
    advancedLogoSelectionBottomRightLocation = { x: bottomRightX, y: bottomRightY };
    advancedLogoSelectionDimensions = { width, height };

    removeBlockersListenersAndPixelSelectionInstructions();
    //note: don't need to remove mouseup listener because it is set to run only once
    document.addEventListener('fullscreenchange', fullscreenChanged);

    selectedPixel = { ...advancedLogoSelectionTopLeftLocation };
    let selectedPixelGridLocation = getSelectedPixelGridLocation(selectedPixel);
    //TODO: I have a lot of different top/bottom and right/left screen checks all over the place, perhaps I should combine them.
    if (shouldOverlayVideoSizeAndLocationAutoSet) {
        let locationToBaseAutoOverlaySizeAndLocation;
        if (selectedPixelGridLocation.isTop) {
            locationToBaseAutoOverlaySizeAndLocation = { ...advancedLogoSelectionBottomRightLocation };
        } else {
            locationToBaseAutoOverlaySizeAndLocation = { ...advancedLogoSelectionTopLeftLocation };
        }
        autoUpdateOverlayVideoSizeAndLocationValues(locationToBaseAutoOverlaySizeAndLocation, selectedPixelGridLocation);
    }

    if (overlayVideoType == 'other-tabs') {
        //if user has extension set to other-tabs, mute the other tabs now
        chrome.runtime.sendMessage({ action: "execute_music_non_commercial_state" });
    }

    setAdvancedLogoDetectionImagePreviews(advancedLogoSelectionTopLeftLocation, advancedLogoSelectionDimensions, selectedPixelGridLocation);

    //wait split second to give chance for the selection box border and hopefully the user cursor to disappear before building the mask
    setTimeout(() => {
        buildLogoMask(advancedLogoSelectionTopLeftLocation, advancedLogoSelectionDimensions);
    }, 250);
}


function buildLogoMask(advancedLogoSelectionTopLeftLocation, advancedLogoSelectionDimensions) {
    const startTime = Date.now();

    if (!document.fullscreenElement) {
        //TODO: somehow work to not trigger the othe exit fullscreen trigger during mask building
        removeElementsByClass('ytoc-main-video-message-alert');
        shutdownAdvancedLogoAnalysis('Logo analysis canceled prior to completion due to exiting fullscreen. Please resume full screen and try again. This message will soon disappear.');
        return;
    }

    let buildMaskRequestType;
    if (advancedLogoMaskCollectionSamples === 0) {
        buildMaskRequestType = "build-mask-first";
    } else if (advancedLogoMaskCollectionSamples > 0 && advancedLogoMaskCollectionSamples < requiredAdvancedLogoMaskCollectionSamples) {
        buildMaskRequestType = "build-mask";
    } else if (advancedLogoMaskCollectionSamples >= requiredAdvancedLogoMaskCollectionSamples) {
        buildMaskRequestType = "build-mask-last";
    }

    getAdvancedLogoAnalysis(advancedLogoSelectionTopLeftLocation, advancedLogoSelectionDimensions, buildMaskRequestType).then(function (logoAnalysisResponse) {
        if (!logoAnalysisResponse) {
            shutdownAdvancedLogoAnalysis('Error calling Advanced Logo Analyzer Companion App. Please make sure app is running and try again. This message will soon disappear.');
            return;
        } else if (logoAnalysisResponse.error) {
            let errorMessage = 'An unnexpected error occured, please try again later. This message will soon disappear.';
            if (logoAnalysisResponse.error === "no logo detected") {
                //note: this error occurs when there is no edge in the finished mask that is above the threshold
                errorMessage = 'Logo weak or missing. Please try again. This message will soon disappear.';
            }
            shutdownAdvancedLogoAnalysis(errorMessage);
            return;
        }

        ++advancedLogoMaskCollectionSamples;

        advancedLogoEdgeImage.src = logoAnalysisResponse.maskBuildPreviewImage;

        const elapsed = Date.now() - startTime;
        const delay = Math.max(0, 1000 - elapsed);

        if (buildMaskRequestType === "build-mask-last") {
            prepForAdvancedLogoMonitor(logoAnalysisResponse, delay, advancedLogoSelectionTopLeftLocation, advancedLogoSelectionDimensions);
        } else {
            setTimeout(() => {
                buildLogoMask(advancedLogoSelectionTopLeftLocation, advancedLogoSelectionDimensions);
            }, delay);
        }
    })
}


function prepForAdvancedLogoMonitor(logoAnalysisResponse, delay, advancedLogoSelectionTopLeftLocation, advancedLogoSelectionDimensions) {
    if (logoAnalysisResponse.edgeSum < 10) {
        shutdownAdvancedLogoAnalysis('Logo weak or missing. Please try again. This message will soon disappear.');
        return;
    }

    if (isDebugMode) {
        logoBox.style.color = "rgb(" + logoAnalysisResponse.averageColorInsideLogoBGR[2] + ", " + logoAnalysisResponse.averageColorInsideLogoBGR[1] + ", " + logoAnalysisResponse.averageColorInsideLogoBGR[0] + ")";
    }

    //advancedLogoInsideLogoColorImageDebug.src = logoAnalysisResponse.averageColorInsideLogoCaptureRegionImage; //debug-high
    if (isDebugMode) advancedLogoFinalMaskImage.src = logoAnalysisResponse.finalMaskImage;

    let insideVersusOutsideHueDifference = Math.abs(logoAnalysisResponse.averageColorOutsideLogo.hsv[0] - logoAnalysisResponse.averageColorInsideLogoHSV[0]);
    let insideVersusOutsideBrightnessDifference = Math.abs(logoAnalysisResponse.averageColorOutsideLogo.hsv[2] - logoAnalysisResponse.averageColorInsideLogoHSV[2]);
    //TODO: have it be like some percentage of pixels that are bright instead of averaging the colors which often ends up being a shade of brown for color logos. or average the s and v's of each pixel?
    //check average color of inside of logo part of mask to see if it is a white / transparent white logo or a colored logo
    //note: logoAnalysisResponse.averageColorInsideLogoHSV[2] = 255 can be full color or full white, depending on the saturation
    if (
        (logoAnalysisResponse.averageColorInsideLogoHSV[1] < 50 && logoAnalysisResponse.averageColorInsideLogoHSV[2] > 50) || //low saturation //TODO: Switch to HSL in the python so I can actually use the L value instead? or maybe it is fine mostly relying on the S in HSV
        (logoAnalysisResponse.averageColorInsideLogoHSV[1] < 140 && logoAnalysisResponse.averageColorInsideLogoHSV[2] > 40 && insideVersusOutsideHueDifference < 27 && insideVersusOutsideBrightnessDifference > 15) //lower saturation threashold if hue outside the logo is similar to inside the logo, implying that the logo may be transparent
    ) {
        isColorLogo = false;
        logoBoxText = 'BASELINE LOGO MASK COMPLETE. BRIGHT OR TRANSPARENT LOGO DETECTED. IF ISSUE, REFRESH PAGE AND TRY AGAIN. MONITORING STARTING NOW.';
    } else {
        isColorLogo = true;
        logoBoxText = 'BASELINE LOGO MASK COMPLETE. LOGO WITH COLOR OR BLACK DETECTED. IF ISSUE, REFRESH PAGE AND TRY AGAIN. MONITORING STARTING NOW.';
        //lower threasholds just a bit since it is harder to compare edges on complicated color logos
        advancedLogoMatchThreshold = 0.6;
        advancedLogoMismatchThreshold = 0.31;
    }
    logoBox.textContent = logoBoxText;

    setTimeout(() => {
        if (!isDebugMode) {
            advancedLogoInfoContainer.style.display = 'none';
        } else {
            advancedLogoFinalMaskImage.remove();
            //advancedLogoInsideLogoColorImageDebug.remove(); //debug-high
        }

        hasMaskCompleteMessageBeenDismissed = true;

        initialLogoBoxTextUpdate();
    }, delay + 8000);

    setTimeout(() => {
        //TODO: Best to set this here in case user is retrying after errors?
        isAdvancedLogoMonitorPaused = false;
        advancedLogoMonitor(advancedLogoSelectionTopLeftLocation, advancedLogoSelectionDimensions);
    }, delay);

    if (overlayVideoType == 'spotify') {
        //if user has extension set to spotify, open spotify now and prompt the user to choose music to play
        setTimeout(() => {
            chrome.runtime.sendMessage({ action: "open_spotify" });
            window.addEventListener('beforeunload', closeSpotify);
        }, delay + 2000);
    }
}


//checks the color of the user set pixel and compares it to the original color in intervals and initiates commercial or non-commercial mode accordingly
function advancedLogoMonitor(advancedLogoSelectionTopLeftLocation, advancedLogoSelectionDimensions) {
    if (!isAdvancedLogoMonitorPaused) {
        const startTime = Date.now();

        getAdvancedLogoAnalysis(advancedLogoSelectionTopLeftLocation, advancedLogoSelectionDimensions, "compare-to-mask").then(function (logoAnalysisResponse) {
            //if error calling python script
            if (!logoAnalysisResponse) {
                ++consecutiveAdvancedLogoAnalysisCallFailures;

                logoBox.textContent = 'ADVANCED LOGO ANALYSIS ERROR. CONSECUTIVE ERRORS = ' + consecutiveAdvancedLogoAnalysisCallFailures;
                advancedLogoInfoContainer.style.display = 'flex';
                if (!isDebugMode && (!isAudioOnlyOverlay || !isCommercialState)) {
                    setTimeout(() => {
                        advancedLogoInfoContainer.style.display = 'none';
                    }, 5000);
                }

                if (consecutiveAdvancedLogoAnalysisCallFailures > 3) {
                    shutdownAdvancedLogoAnalysis('Error calling Advanced Logo Analyzer Companion App. Please make sure app is running and try again. This message will soon disappear.');
                } else {
                    const elapsed = Date.now() - startTime;
                    const delay = Math.max(0, 1000 - elapsed);
                    //call no faster than once per second
                    setTimeout(() => {
                        advancedLogoMonitor(advancedLogoSelectionTopLeftLocation, advancedLogoSelectionDimensions);
                    }, delay);
                }

                return;
            }
            consecutiveAdvancedLogoAnalysisCallFailures = 0;

            if (hasMaskCompleteMessageBeenDismissed) {
                //TODO: only update this while it is showing. Otherwise it is a waste?
                advancedLogoEdgeImage.src = logoAnalysisResponse.edgeMatchVisualImage;
            }

            const formattedEdgeMatchPercentage = ((logoAnalysisResponse.edgeMatchConfidence * 100).toFixed(0)).padStart(2, "0") + "%";
            if (isDebugMode) {
                if (hasMaskCompleteMessageBeenDismissed) {
                    logoBox.textContent = formattedEdgeMatchPercentage;
                    //logoBox.textContent = ((logoAnalysisResponse.edgeMatchConfidence * 100).toFixed(0)).padStart(2, "0") + "%";
                }
            }

            const isBrightAroundLogo = (logoAnalysisResponse.averageColorOutsideLogo.hsv[1] < 19 && logoAnalysisResponse.averageColorOutsideLogo.hsv[2] > 229);

            //default to matching logo if not in commercial break and not matching logo if in commercial break
            let match = !isCommercialState;
            if (
                !isCommercialState &&
                logoAnalysisResponse.edgeMatchConfidence < advancedLogoMismatchThreshold &&
                (isColorLogo || !isBrightAroundLogo)
            ) {
                match = false;
            } else if (
                isCommercialState &&
                logoAnalysisResponse.edgeMatchConfidence > advancedLogoMatchThreshold
            ) {
                match = true;
            }
            if (!match) {
                //indicating potential commercial break

                mismatchCount++;
                matchCount = 0;
                logoCountdownMismatchesRemaining = (mismatchCountThreshold - mismatchCount);

                //show countdown if 3 seconds until commercial mode or it would be 3 seconds until commercial mode and cooldown is blocking
                if (logoCountdownMismatchesRemaining <= 3 && !isCommercialState) {
                    if ((cooldownCountRemaining >= 1) && (cooldownCountRemaining > logoCountdownMismatchesRemaining)) {
                        //logoBox.textContent = cooldownCountRemaining;
                        logoBox.textContent = formattedEdgeMatchPercentage; //TODO: is this useful?
                        advancedLogoInfoContainer.style.display = 'flex';

                        countdownOngoing = true;
                    } else if (logoCountdownMismatchesRemaining >= 1) {
                        //logoBox.textContent = logoCountdownMismatchesRemaining; 
                        logoBox.textContent = formattedEdgeMatchPercentage; //TODO: is this useful?
                        advancedLogoInfoContainer.style.display = 'flex';

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

                        if (overlayVideoType === 'spotify') {
                            logoBoxText = 'PLAYING SPOTIFY'
                        }
                        logoBox.textContent = logoBoxText;

                        advancedLogoInfoContainer.style.display = 'flex';
                        if (!isDebugMode && !isAudioOnlyOverlay) {
                            setTimeout(() => {
                                advancedLogoInfoContainer.style.display = 'none';
                            }, 5000);
                        }
                    }

                    //TODO: find out if this is better inside the if above or here, especially as it relates to manual switching during auto mode. or is it needed at all?
                    mismatchCount = 0;
                }
            } else {
                //match indicating logo potentially back or white background when the logo is white

                //do not want bright around white logo protection clearing out mismatch count while potentially going to commercial with white background
                //TODO: need more testing and analysis on this
                if (isColorLogo || isCommercialState || !isBrightAroundLogo || logoAnalysisResponse.edgeMatchConfidence > advancedLogoMismatchThreshold) {
                    matchCount++;
                    mismatchCount = 0;
                }

                //TODO: is this the best way to do this considering audio and video options?
                if (!isDebugMode && !isCommercialState && hasMaskCompleteMessageBeenDismissed) {
                    advancedLogoInfoContainer.style.display = 'none';
                }

                countdownOngoing = false;
                if (!isDebugMode) {
                    logoBox.textContent = logoBoxText;
                }

                if (matchCount >= matchCountThreshold && cooldownCountRemaining <= 0) {
                    if (isCommercialState) {
                        if (isDebugMode) { console.log('commercial undetected'); }

                        if (isAudioOnlyOverlay) {
                            if (isDebugMode) {
                                logoBoxText = 'LIVE COMMERCIAL BLOCKER';
                                logoBox.textContent = logoBoxText;
                            } else {
                                advancedLogoInfoContainer.style.display = 'none';
                            }
                        }

                        endCommercialMode();
                    }
                    //TODO: find out if this is better inside the if above or here, especially as it relates to manual switching during auto mode. or does it need done at all?
                    matchCount = 0;
                }
            }

            if (isDebugMode) {
                if (!isCommercialState && !isColorLogo && isBrightAroundLogo) {
                    logoBox.style.backgroundColor = "red";
                } else {
                    logoBox.style.backgroundColor = "rgb(" + logoAnalysisResponse.averageColorOutsideLogo.rgb + ")";
                }
            }

            cooldownCountRemaining--;

            const elapsed = Date.now() - startTime;
            const delay = Math.max(0, 1000 - elapsed);
            //call no faster than once per second
            setTimeout(() => {
                advancedLogoMonitor(advancedLogoSelectionTopLeftLocation, advancedLogoSelectionDimensions)
            }, delay);

        })
            .catch(function (error) {
                console.error(error);
            });
    }
}


//will build edge mask of logo and then will return how much that egde mask matches the current edges amoung other things
function getAdvancedLogoAnalysis(coordinates, dimensions, request) {
    return new Promise(function (resolve, reject) {
        if (isFirefox) {
            let rect = { x: coordinates.x, y: coordinates.y, width: dimensions.width, height: dimensions.height };

            chrome.runtime.sendMessage({
                action: "firefox-advanced-logo-analysis",
                rect: rect,
                request: request,
                isCommercialState: isCommercialState
            }, function (response) {
                if (response.wasSuccessfulCall) {
                    resolve(response.logoAnalysisResponse);
                } else {
                    resolve(false);
                }
            });
        } else {
            chrome.runtime.sendMessage({
                target: "offscreen",
                action: "capture-logo-advanced",
                request: request,
                coordinates: coordinates,
                dimensions: dimensions,
                isCommercialState: isCommercialState
            }, function (response) {
                if (response.wasSuccessfulCall) {
                    resolve(response.logoAnalysisResponse);
                } else {
                    resolve(false);
                }
            });
        }
    });
}


//TODO: Somehow use a variation of this for all auto-pixel modes to let users reselect pixel without refreshing tab
function shutdownAdvancedLogoAnalysis(message) {
    addMessageAlertToMainVideo(message);
    setTimeout(() => {
        removeElementsByClass('ytoc-main-video-message-alert');
    }, 9000);

    pauseAutoMode(false);

    document.removeEventListener('fullscreenchange', fullscreenChanged);
    if (logoBox) {
        logoBox.remove(); //TODO: does this even need removed if I'm removing the container it is in right after this?
    }
    if (advancedLogoInfoContainer) {
        advancedLogoInfoContainer.remove();
    }

    //remove these right away instead of waiting for the timeout to do so from removeBlockersListenersAndPixelSelectionInstructions
    removeClickAndUIBlockers();

    //complete reset
    cooldownCountRemaining = 8;
    advancedLogoMaskCollectionSamples = 0;
    selectedPixel = false;
    isAutoModeInitiated = false;
}


function setAdvancedLogoDetectionImagePreviews(advancedLogoSelectionTopLeftLocation, advancedLogoSelectionDimensions, selectedPixelGridLocation) {
    //TODO: add check to make sure user is still in fullscreen mode
    let insertLocation = document.fullscreenElement;
    if (insertLocation.nodeName == 'HTML') {
        insertLocation = document.getElementsByTagName('body')[0];
    }

    advancedLogoInfoContainer = document.createElement('div');
    advancedLogoInfoContainer.className = "ytoc-advanced-logo-container";
    advancedLogoInfoContainer.style.display = 'flex';

    insertLocation.insertBefore(advancedLogoInfoContainer, null);

    advancedLogoEdgeImage = document.createElement('img');
    if (isDebugMode) advancedLogoFinalMaskImage = document.createElement('img');
    //advancedLogoInsideLogoColorImageDebug = document.createElement('img'); //debug-high

    logoBox = document.createElement('div');
    logoBox.className = "ytoc-logo-advanced";
    logoBoxText = 'ANALYZING LOGO...';
    logoBox.textContent = logoBoxText;

    if (selectedPixelGridLocation.isTop) {
        advancedLogoInfoContainer.style.top = advancedLogoSelectionTopLeftLocation.y + 'px';
        advancedLogoInfoContainer.style.bottom = 'auto';
    } else {
        advancedLogoInfoContainer.style.top = 'auto';
        advancedLogoInfoContainer.style.bottom = ((windowHeight - advancedLogoSelectionTopLeftLocation.y) - advancedLogoSelectionDimensions.height) + 'px';
    }

    if (selectedPixelGridLocation.isLeft) {
        advancedLogoInfoContainer.style.left = (advancedLogoSelectionTopLeftLocation.x + advancedLogoSelectionDimensions.width) + 'px';
        advancedLogoInfoContainer.style.right = 'auto';

        advancedLogoInfoContainer.insertBefore(advancedLogoEdgeImage, null);
        if (isDebugMode) advancedLogoInfoContainer.insertBefore(advancedLogoFinalMaskImage, null);
        //advancedLogoInfoContainer.insertBefore(advancedLogoInsideLogoColorImageDebug, null); //debug-high

        //insert after images to show on the left
        advancedLogoInfoContainer.insertBefore(logoBox, null);
    } else {
        advancedLogoInfoContainer.style.left = 'auto';
        advancedLogoInfoContainer.style.right = (windowWidth - advancedLogoSelectionTopLeftLocation.x) + 'px';

        //insert before images to show on the right
        advancedLogoInfoContainer.insertBefore(logoBox, null);

        //advancedLogoInfoContainer.insertBefore(advancedLogoInsideLogoColorImageDebug, null); //debug-high
        if (isDebugMode) advancedLogoInfoContainer.insertBefore(advancedLogoFinalMaskImage, null);
        advancedLogoInfoContainer.insertBefore(advancedLogoEdgeImage, null);
    }
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
function setCommercialDetectedIndicator(selectedPixel, selectedPixelGridLocation) {

    //TODO: add check to make sure user is still in fullscreen mode
    let insertLocation = document.fullscreenElement;
    if (insertLocation.nodeName == 'HTML') {
        insertLocation = document.getElementsByTagName('body')[0];
    }

    logoBox = document.createElement('div');
    logoBox.className = "ytoc-logo";
    if (commercialDetectionMode === 'auto-pixel-advanced-logo') {
        logoBoxText = 'ANALYZING LOGO...';
    } else {
        logoBoxText = 'PIXEL SELECTED!';
    }
    logoBox.textContent = logoBoxText;
    logoBox.style.display = 'block';

    if (selectedPixelGridLocation.isLeft) {
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
        logoBoxText = 'PLAYING SPOTIFY';
    } else if (overlayVideoType == 'other-tabs') {
        logoBoxText = "PLAYING OTHER TAB AUDIO"; //speaker with three sound waves symbol
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

        //TODO: is this even necessary anymore?
        if (commercialDetectionMode.indexOf('auto-pixel') >= 0) {
            if (commercialDetectionMode !== 'auto-pixel-advanced-logo') {
                logoBox.style.display = 'block';
            }
        } else {
            audioLevelIndicatorContainer.style.display = 'flex';
        }

        //TODO: add user preference for this?
        //if (!isDebugMode && commercialDetectionMode !== 'auto-audio') {
        //    setTimeout(() => {
        //        logoBoxText = "\uD83D\uDD0A"; //speaker with three sound waves symbol
        //        logoBox.textContent = logoBoxText;
        //    }, 10000);
        //}

    }

}


//returns the quadrant that the selected pixel is in
function getSelectedPixelGridLocation(selectedPixel) {
    let selectedPixelGridLocation = { isTop: false, isLeft: false };

    if (selectedPixel.x < windowWidth / 2) {
        selectedPixelGridLocation.isLeft = true;
    }
    if (selectedPixel.y < windowHeight / 2) {
        selectedPixelGridLocation.isTop = true;
    }

    return selectedPixelGridLocation;
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
            if (commercialDetectionMode !== 'auto-pixel-advanced-logo') {
                logoBox.style.display = 'none';
            } else {
                advancedLogoInfoContainer.style.display = 'none';
            }
            pauseAutoMode(true);
        } else if (commercialDetectionMode == 'auto-audio') {
            audioLevelIndicatorContainer.style.display = 'none';
            pauseAutoMode(true);
        }

        if (isCommercialState) {
            if (!isAudioOnlyOverlay) {
                endCommercialMode();
            } else {
                //don't want to count while not actively checking when the commercials end 
                stopCommercialTimer();
            }
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
            if (isDebugMode || (isAudioOnlyOverlay && isCommercialState)) {
                if (commercialDetectionMode !== 'auto-pixel-advanced-logo') {
                    logoBox.style.display = 'block';
                } else {
                    advancedLogoInfoContainer.style.display = 'flex';
                }
            }
        } else if (commercialDetectionMode == 'auto-audio') {
            resumeAutoMode();
            if (isDebugMode) { audioLevelIndicatorContainer.style.display = 'flex'; }
        } //else do not run resumeAutoMode

        if ((overlayVideoType == 'spotify' && !isCommercialState) || overlayVideoType == 'other-tabs') {
            chrome.runtime.sendMessage({ action: "execute_music_non_commercial_state" });
        }

    }

}


function pauseAutoMode(shouldDisplayMessage) {
    if (commercialDetectionMode === 'auto-pixel-advanced-logo') {
        isAdvancedLogoMonitorPaused = true;
    } else {
        clearInterval(monitorIntervalID);
    }

    stopViewingTab();

    if (shouldDisplayMessage) {
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
}


function resumeAutoMode() {

    if (commercialDetectionMode.indexOf('auto-pixel') >= 0) {
        startViewingTab(windowDimensions);
        //give a sec for tab viewing to start
        setTimeout(() => {
            cooldownCountRemaining = 8; //give a chance for video UI to go away
            if (commercialDetectionMode === 'auto-pixel-advanced-logo') {
                isAdvancedLogoMonitorPaused = false;
                advancedLogoMonitor(advancedLogoSelectionTopLeftLocation, advancedLogoSelectionDimensions);
            } else {
                pixelColorMatchMonitor(originalPixelColor, selectedPixel);
            }
        }, 1000);
    } else if (commercialDetectionMode === 'auto-audio') {
        startListeningToTab();
        audioThresholdMonitor();
    }
    
}


function abortPixelSelection() {
    isAutoModeInitiated = false;

    removeBlockersListenersAndPixelSelectionInstructions();
    stopViewingTab();
    document.removeEventListener('fullscreenchange', abortPixelSelection);

    let abortMessage;
    if (!document.fullscreenElement) {
        abortMessage = 'Selection aborted! Go back to full screen and hit keyboard shortcut to start again. This message will disappear shortly.';
    } else {
        abortMessage = 'Selection aborted! Hit keyboard shortcut to start again. This message will disappear shortly.';
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
                'overlayVideoType',
                'ytPlaylistID',
                'ytVideoID',
                'ytLiveID',
                'otherVideoURL',
                'otherLiveURL',
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

                //verify user is not switching from or to audio only overlays //TODO: get that to work
                if (!isAudioOnlyOverlay && result.overlayVideoType !== 'spotify' && result.overlayVideoType !== 'other-tabs') {

                    //if user changes video source, update for next commercial
                    if (
                        overlayVideoType !== result.overlayVideoType ||
                        ytPlaylistID !== result.ytPlaylistID ||
                        ytVideoID !== result.ytVideoID ||
                        ytLiveID !== result.ytLiveID ||
                        otherVideoURL !== result.otherVideoURL ||
                        otherLiveURL !== result.otherLiveURL
                    ) {

                        //TODO: get to work for both auto and manual modes
                        if (commercialDetectionMode.indexOf('auto') >= 0) {

                            if (!isAutoModeFirstCommercial) {
                                removeOverlayVideo();
                                isAutoModeFirstCommercial = true;
                            }

                            overlayVideoType = result.overlayVideoType;
                            if (overlayVideoType == 'yt-live' || overlayVideoType == 'other-live') {
                                isLiveOverlayVideo = true;
                            } else {
                                isLiveOverlayVideo = false;
                            }
                            ytPlaylistID = result.ytPlaylistID;
                            ytVideoID = result.ytVideoID;
                            ytLiveID = result.ytLiveID;
                            otherVideoURL = result.otherVideoURL;
                            otherLiveURL = result.otherLiveURL;

                        }

                    }

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


function autoUpdateOverlayVideoSizeAndLocationValues(selectedPixel, selectedPixelGridLocation) {

    videoOverlayWidth = 100;
    overlayVideoLocationHorizontal = 'middle';

    let belowSelectedPixelBuffer = 8;
    let aboveSelectedPixelBuffer = 4;
    if (isFirefox || commercialDetectionMode === 'auto-pixel-advanced-logo') {
        belowSelectedPixelBuffer = 4;
    }

    if (selectedPixelGridLocation.isTop) {
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


//prevent all javascript from occuring for an event
function blockHandler(e) {
    e.stopImmediatePropagation();
    e.preventDefault();
}


//start recording how much time this extension is blocking commercials for fun stats
function startCommercialTimer() {
    commercialTimerStartTime = Date.now();
}


//stop recording commercial blocking time and add value to historic count
function stopCommercialTimer() {
    if (!commercialTimerStartTime) return;

    commercialTimerEndTime = Date.now();
    const today = new Date().toDateString();

    const sessionCommercialsBlockedSeconds = (commercialTimerEndTime - commercialTimerStartTime) / 1000;
    //clear timer
    commercialTimerStartTime = null; //TODO: set to false instead of null?

    chrome.storage.sync.get([
        'totalCommercialsBlockedSeconds',
        'todayCommercialsBlockedSeconds',
        'firstCommercialTimerDate',
        'lastCommercialTimerDate'
    ], (result) => {
        let totalCommercialsBlockedSeconds = result.totalCommercialsBlockedSeconds || 0;
        let todayCommercialsBlockedSeconds = result.todayCommercialsBlockedSeconds || 0;
        let firstCommercialTimerDate = result.firstCommercialTimerDate || today;
        let lastCommercialTimerDate = result.lastCommercialTimerDate || today;

        if (lastCommercialTimerDate !== today) {
            todayCommercialsBlockedSeconds = 0;
        }

        totalCommercialsBlockedSeconds += sessionCommercialsBlockedSeconds;
        todayCommercialsBlockedSeconds += sessionCommercialsBlockedSeconds;

        chrome.storage.sync.set({
            totalCommercialsBlockedSeconds: totalCommercialsBlockedSeconds,
            todayCommercialsBlockedSeconds: todayCommercialsBlockedSeconds,
            firstCommercialTimerDate: firstCommercialTimerDate,
            lastCommercialTimerDate: today,
        });
    });
}