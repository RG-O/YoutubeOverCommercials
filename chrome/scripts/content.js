
var isFirefox = false; //********************

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
//TODO: Add user preference for spotify to have audio come in gradually


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
    } else if (overlayVideoType == 'yt-video' || overlayVideoType == 'yt-live') {
        url = "https://www.youtube.com/embed/";
        if (overlayVideoType == 'yt-video') {
            url = url.concat(ytVideoID);
        } else {
            url = url.concat(ytLiveID);
        }
    } else if (overlayVideoType == 'other-video') {
        url = otherVideoURL;
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

        if (commercialDetectionMode != 'auto') {

            overlayScreen.className = "ytoc-overlay-screen";
            overlayScreen.style.backgroundColor = "rgba(0, 0, 0, ." + mainVideoFade + ")";
            insertLocation.insertBefore(overlayScreen, null);

        } else if (selectedPixel) {

            overlayScreen.className = "ytoc-overlay-screen-with-hole";
            //setting location of hole for the pixel color detector to look through, subtracting by 3 for radius of hole
            overlayScreen.style.left = (selectedPixel.x - 3) + 'px';
            overlayScreen.style.top = (selectedPixel.y - 3) + 'px';
            overlayScreen.style.boxShadow = "0 0 0 99999px rgba(0, 0, 0, ." + mainVideoFade + ")";
            insertLocation.insertBefore(overlayScreen, null);

        } else {
            //setting mainVideoFade to 0 to effectively shut it off since it is auto detection mode but I don't know where to put the hole
            mainVideoFade = 0;
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

    if (commercialDetectionMode != 'auto') {

        if (overlayVideoType == 'spotify') {
            //Note: this happens in captureOriginalPixelColor() in auto mode
            chrome.runtime.sendMessage({ action: "open_spotify" });
            window.addEventListener('beforeunload', closeSpotify);
        }

        //TODO: should this be moved above opening spotify?
        //Note: this happens in pixelSelection() in auto mode
        document.addEventListener('fullscreenchange', fullscreenChanged);

    }

    mainVideoCollection = document.getElementsByTagName('video'); //TODO: grab all videos on page and loop and interaction with all of them

    muteMainVideo();

    if (isAudioOnlyOverlay) {

        chrome.runtime.sendMessage({ action: "execute_music_commercial_state" });

        if (overlayVideoType == 'other-tabs') {
            window.addEventListener('beforeunload', stopMutingOtherTabs);
        }

    } else {

        //wait a little bit for the video to load //TODO: get indicator of when completely loaded
        setTimeout(() => {
            chrome.runtime.sendMessage({ action: "initial_execute_overlay_video_interaction" });
        }, 2000);
    }

}


function muteMainVideo() {

    //muting main/background video
    if (mainVideoVolumeDuringCommercials == 0) {

        //using the actual controls to mute YTTV because for whatever reason, it will unmute itself
        if (window.location.hostname == 'tv.youtube.com') {

            if (document.querySelector('[aria-label="Mute (m)"]')) {

                document.querySelector('[aria-label="Mute (m)"]').click();

            }

        } else {

            for (let i = 0; i < mainVideoCollection.length; i++) {
                mainVideoCollection[i].muted = true; // Mute each video
            }

        }

    } else if (mainVideoVolumeDuringCommercials < 1) {

        for (let i = 0; i < mainVideoCollection.length; i++) {
            mainVideoCollection[i].volume = mainVideoVolumeDuringCommercials;
        }

    } //else do nothing for 100

}


function unmuteMainVideo() {

    if (mainVideoVolumeDuringCommercials == 0) {

        if (window.location.hostname == 'tv.youtube.com') {

            if (document.querySelector('[aria-label="Unmute (m)"]')) {

                document.querySelector('[aria-label="Unmute (m)"]').click();

            }

        } else {

            for (let i = 0; i < mainVideoCollection.length; i++) {
                mainVideoCollection[i].muted = false; // Mute each video
            }

        }

    } else if (mainVideoVolumeDuringCommercials < 1) {

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

        if (mainVideoFade > 0) {
            if (commercialDetectionMode != 'auto') {
                overlayScreen.style.backgroundColor = "transparent";
            } else {
                overlayScreen.style.boxShadow = "0 0 0";
            }
        }

    }

    unmuteMainVideo();

}


//switches to commercial state which means showing the overlay video and muting the main/background video
function startCommercialMode() {

    if (commercialDetectionMode == 'auto' && isAutoModeFirstCommercial) {

        //check again if in full screen in case user exited
        if (document.fullscreenElement) {

            isCommercialState = true;

            isAutoModeFirstCommercial = false;
            //setting cooldown time so video has a chance to play for the first time
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

            if (mainVideoFade > 0) {
                if (commercialDetectionMode != 'auto') {
                    overlayScreen.style.backgroundColor = "rgba(0, 0, 0, ." + mainVideoFade + ")";
                } else {
                    overlayScreen.style.boxShadow = "0 0 0 99999px rgba(0, 0, 0, ." + mainVideoFade + ")";
                }
            }

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
        if (isFirstRun) {

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
                            'pipWidth'
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
                            if (!isAudioOnlyOverlay) {
                                overlayVideoLocationHorizontal = result.overlayVideoLocationHorizontal ?? 'middle';
                                overlayVideoLocationVertical = result.overlayVideoLocationVertical ?? 'middle';
                                videoOverlayWidth = result.videoOverlayWidth ?? 75;
                                videoOverlayHeight = result.videoOverlayHeight ?? 75;
                            } else {
                                overlayVideoLocationHorizontal = 'middle';
                                overlayVideoLocationVertical = 'middle';
                                videoOverlayWidth = 50;
                                videoOverlayHeight = 50;
                            }
                            mainVideoVolumeDuringCommercials = result.mainVideoVolumeDuringCommercials ?? 0; //TODO: get this to work for .01-.99 values for yttv
                            mainVideoVolumeDuringNonCommercials = result.mainVideoVolumeDuringNonCommercials ?? 100; //TODO: get this to work for .01-.99 values for yttv
                            if (mainVideoVolumeDuringCommercials > 0) {
                                mainVideoVolumeDuringCommercials = mainVideoVolumeDuringCommercials / 100;
                            }
                            if (mainVideoVolumeDuringNonCommercials > 0) {
                                mainVideoVolumeDuringNonCommercials = mainVideoVolumeDuringNonCommercials / 100;
                            }
                            commercialDetectionMode = result.commercialDetectionMode ?? 'auto';
                            mismatchCountThreshold = result.mismatchCountThreshold ?? 8;
                            matchCountThreshold = result.matchCountThreshold ?? 2;
                            colorDifferenceMatchingThreshold = result.colorDifferenceMatchingThreshold ?? 12;
                            manualOverrideCooldown = result.manualOverrideCooldown ?? 30;
                            isDebugMode = result.isDebugMode ?? false;
                            isPiPMode = result.isPiPMode ?? true;
                            pipLocationHorizontal = result.pipLocationHorizontal ?? 'top';
                            pipLocationVertical = result.pipLocationVertical ?? 'left';
                            pipHeight = result.pipHeight ?? 20;
                            pipWidth = result.pipWidth ?? 20;

                            chrome.runtime.sendMessage({ action: "capture_main_video_tab_id" });

                            //setting up for pixel selection for auto mode or continuing run for manual
                            if (commercialDetectionMode == 'auto') {

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

                                } //else do nothing //TODO: add else here that removes instructions and event listener and sets isAutoModeInitiated to false so if user initiated too early previously, they can try again later

                            } else {

                                initialRun();

                            }

                        });

                    } //else do nothing for when nodeName is IFRAME

                } else if (overlayHostName == 'www.youtube.com') { //TODO: find a better way to not show this warning on overlay video when using non-yt videos and maybe not even let it get to this point
                    //since user was not in full screen, instruct them that they need to be

                    setNotFullscreenAlerts();

                }

            });

        } else {

            //TODO: set the mismatch and match counts to some negative number in here
            if (isCommercialState) {

                endCommercialMode();

            } else {

                startCommercialMode();

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

        addMessageAlertToMainVideo('Video must be full screen for YTOC extension to work.');
        fullScreenAlertSet = true;

    }

}


//remove all full screen alerts if previously set
//TODO: rename this?
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
        pipBlocker.style.backgroundColor = "black";
        
        insertLocationFullscreenElm.insertBefore(pipBlocker, null);
        pipBlockerText = document.createElement('div');
        pipBlockerText.style.color = "white";
        pipBlockerText.style.fontSize = "16px";
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

    //hide verticle scrollbar if video placed on bottom
    if (overlayVideoLocationVertical == 'bottom') {
        let hideScollStyle = document.createElement("style");
        hideScollStyle.textContent = `
            ::-webkit-scrollbar {
                display: none;
            }
        `;
        insertLocation.appendChild(hideScollStyle);
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

    let iFrame = document.createElement('iframe');
    iFrame.src = chrome.runtime.getURL('pixel-select-instructions.html');
    iFrame.width = "100%";
    iFrame.height = "100%";
    iFrame.allow = "autoplay; encrypted-media";
    iFrame.frameBorder = "0";
    //iFrame.style.setProperty("border", "3px red solid", "important");

    overlayInstructions.appendChild(iFrame);

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

        //wait a sec to remove pixel selected message and replace with logo to let the user read message
        setTimeout(() => {
            if (!isAudioOnlyOverlay || isDebugMode) {
                logoBoxText = 'YTOC';
            } else if (overlayVideoType == 'spotify') {
                logoBoxText = 'Playing Spotify'; //TODO: Maybe also set this to YTOC
            } else if (overlayVideoType == 'other-tabs') {
                logoBoxText = "\uD83D\uDD0A"; //speaker with three sound waves symbol
            }
            logoBox.textContent = logoBoxText;
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
        //TODO: set some sort of pause on this interval if user leaves full screen

        getPixelColor(selectedPixel).then(function (pixelColor) {

            let redDifference = Math.abs(originalPixelColor.r - pixelColor.r);
            let greenDifference = Math.abs(originalPixelColor.g - pixelColor.g);
            let blueDifference = Math.abs(originalPixelColor.b - pixelColor.b);

            //TODO: Create HSL option
            if (
                redDifference > colorDifferenceMatchingThreshold ||
                greenDifference > colorDifferenceMatchingThreshold ||
                blueDifference > colorDifferenceMatchingThreshold
            ) {
                //color mismatch

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
                        logoBox.style.color = "rgba(" + pixelColor.r + ", " + pixelColor.g + ", " + pixelColor.b + ", 1)";
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
                //color match

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
                                logoBoxText = 'YTOC';
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

            logoBox.style.color = "rgba(" + pixelColor.r + ", " + pixelColor.g + ", " + pixelColor.b + ", 1)";

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

        chrome.runtime.sendMessage({ action: "chrome-view-tab", windowDimensions: windowDimensions });
        window.addEventListener('beforeunload', stopViewingTab);

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

        if (commercialDetectionMode == 'auto') {
            logoBox.style.display = 'none';
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

        if (commercialDetectionMode == 'auto') {
            resumeAutoMode();
            if (isDebugMode) { logoBox.style.display = 'block'; }
        }

        if ((overlayVideoType == 'spotify' && !isCommercialState) || overlayVideoType == 'other-tabs') {
            chrome.runtime.sendMessage({ action: "execute_music_non_commercial_state" });
        }

    }

}


function pauseAutoMode() {

    clearInterval(monitorIntervalID);
    stopViewingTab();
    addMessageAlertToMainVideo('YTOC extension paused until back to fullscreen. Set video to fullscreen or refresh tab to remove message.');

}


function resumeAutoMode() {

    pixelColorMatchMonitor(originalPixelColor, selectedPixel);
    startViewingTab(windowDimensions);
    cooldownCountRemaining = 8; //give a chance for video UI to go away

}


function abortPixelSelection() {
    if (!document.fullscreenElement) {

        isAutoModeInitiated = false;

        removeBlockersListenersAndPixelSelectionInstructions();

        //close offscreen.js
        chrome.runtime.sendMessage({
            target: "offscreen",
            action: "close"
        });

        window.removeEventListener('beforeunload', stopViewingTab);
        document.removeEventListener('fullscreenchange', abortPixelSelection);

        //give a split second for the other stuff to occur before temporarly freezing everything with this alert
        setTimeout(() => {
            alert('Pixel selection aborted! Go back to full screen and hit keyboard shortcut to start again.');
        }, 500);

    }
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
    //setting location of hole for the pixel color detector to look through, subtracting by 3 for radius of hole
    selectedPixelRing.style.left = (selectedPixel.x - 3) + 'px';
    selectedPixelRing.style.top = (selectedPixel.y - 3) + 'px';

    insertLocation.insertBefore(selectedPixelRing, null);

}


function closeSpotify() {
    chrome.runtime.sendMessage({ action: "close_spotify" });
}


chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
    if (message.action == 'content_update_logo_text') {

        if (commercialDetectionMode == 'auto') {

            logoBoxText = message.text;

            //strangley, an unnecessary delay feels smoother here
            setTimeout(() => {
                if (!countdownOngoing) {
                    logoBox.textContent = logoBoxText;
                }
            }, 2000);

            if (isCommercialState) {

                logoBox.style.display = 'block';
                if (!isDebugMode) {
                    setTimeout(() => {
                        logoBoxText = "\uD83D\uDD0A"; //speaker with three sound waves symbol
                        logoBox.textContent = logoBoxText;
                    }, 10000);
                }

            }

        } //else no need to update logo if not in auto mode

    } else if (message.action == 'show_resume_fullscreen_message') {

        //TODO: add removeElementsByClass('ytoc-main-video-message-alert') into addMessageAlertToMainVideo() function
        removeElementsByClass('ytoc-main-video-message-alert');
        addMessageAlertToMainVideo('Success! You may now resume fullscreen and enjoy :)');

    } else if (message.action == 'content_update_preferences') {

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
                'pipWidth'
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

    overlay.style.setProperty("width", widthPercentage + "%", "important");
    overlay.style.setProperty("height", heightPercentage + "%", "important");

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