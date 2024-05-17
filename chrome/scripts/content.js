//TODO: Add instrutions for manual mode

//establish variables
var isCommercialState = false;
var firstClick = true;
var mainVideo;
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

//grab all user set values
//note: this is an async function
chrome.storage.sync.get([
    'overlayVideoType',
    'ytPlaylistID',
    'ytVideoID',
    'ytLiveID',
    'otherVideoURL',
    'otherLiveURL',
    'overlayHostName',
    'mainVideoFade',
    'videoOverlayWidth',
    'videoOverlayHeight',
    'overlayVideoLocationHorizontal',
    'overlayVideoLocationVertical',
    'mainVideoVolumeDuringCommercials',
    'mainVideoVolumeDuringNonCommercials',
    'shouldHideYTBackground',
    'commercialDetectionMode',
    'mismatchCountThreshold',
    'matchCountThreshold',
    'colorDifferenceMatchingThreshold',
    'manualOverrideCooldown',
    'isDebugMode'
], (result) => {

    //set them to default if not set by user yet
    overlayVideoType = result.overlayVideoType ?? 'yt-playlist';
    ytPlaylistID = result.ytPlaylistID ?? 'PLt982az5t-dVn-HDI4D7fnvMXt8T9_OGB';
    ytVideoID = result.ytVideoID ?? '5AMQbxBZohY';
    ytLiveID = result.ytLiveID ?? 'QhJcIlE0NAQ';
    otherVideoURL = result.otherVideoURL ?? 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/TearsOfSteel.mp4';
    otherLiveURL = result.otherLiveURL ?? 'https://tv.youtube.com/watch/_2ONrjDR7S8';
    overlayHostName = result.overlayHostName ?? 'www.youtube.com';
    overlayVideoLocationHorizontal = result.overlayVideoLocationHorizontal ?? 'middle';
    overlayVideoLocationVertical = result.overlayVideoLocationVertical ?? 'middle';
    mainVideoFade = result.mainVideoFade ?? 55;
    videoOverlayWidth = result.videoOverlayWidth ?? 75;
    videoOverlayHeight = result.videoOverlayHeight ?? 75;
    mainVideoVolumeDuringCommercials = result.mainVideoVolumeDuringCommercials ?? 0; //TODO: get this to work for .01-.99 values for yttv
    mainVideoVolumeDuringNonCommercials = result.mainVideoVolumeDuringNonCommercials ?? 100; //TODO: get this to work for .01-.99 values for yttv
    if (mainVideoVolumeDuringCommercials > 0) {
        mainVideoVolumeDuringCommercials = mainVideoVolumeDuringCommercials / 100;
    }
    if (mainVideoVolumeDuringNonCommercials > 0) {
        mainVideoVolumeDuringNonCommercials = mainVideoVolumeDuringNonCommercials / 100;
    }
    shouldHideYTBackground = result.shouldHideYTBackground ?? true;
    commercialDetectionMode = result.commercialDetectionMode ?? 'auto';
    mismatchCountThreshold = result.mismatchCountThreshold ?? 8;
    matchCountThreshold = result.matchCountThreshold ?? 2;
    colorDifferenceMatchingThreshold = result.colorDifferenceMatchingThreshold ?? 12;
    manualOverrideCooldown = result.manualOverrideCooldown ?? 30;
    isDebugMode = result.isDebugMode ?? false;

});

//function that is responsible for loading the video iframe over top of the main/background video
function setOverlayVideo() {

    mainVideo = document.getElementsByTagName('video')[0]; //TODO: grab all videos on page and loop and interaction with all of them

    //TODO: add check to make sure user is still in full screen and if not to break and resut isFirstRun
    let insertLocation = document.fullscreenElement;
    if (insertLocation.nodeName == 'HTML') {
        insertLocation = document.getElementsByTagName('body')[0];
    }

    addOverlayFade(insertLocation);

    overlayVideo = document.createElement('div');
    overlayVideo.className = "ytoc-overlay-video";
    //TODO: replace firstChild with null since the last items is actually most likely to show on top?
    insertLocation.insertBefore(overlayVideo, null);
    overlayVideo.style.visibility = "visible";
    overlayVideo.style.setProperty("width", videoOverlayWidth + "%", "important");
    overlayVideo.style.setProperty("height", videoOverlayHeight + "%", "important");

    //setting overlay video in user set location
    if (overlayVideoLocationHorizontal == 'left' || overlayVideoLocationHorizontal == 'middle') {
        overlayVideo.style.setProperty("left", "0", "important");
    }
    if (overlayVideoLocationHorizontal == 'right' || overlayVideoLocationHorizontal == 'middle') {
        overlayVideo.style.setProperty("right", "0", "important");
    }
    if (overlayVideoLocationVertical == 'top' || overlayVideoLocationVertical == 'middle') {
        overlayVideo.style.setProperty("top", "0", "important");
    }
    if (overlayVideoLocationVertical == 'bottom' || overlayVideoLocationVertical == 'middle') {
        overlayVideo.style.setProperty("bottom", "0", "important");
    }


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

    setOverlayVideo();

    //muting main/background video
    if (mainVideoVolumeDuringCommercials == 0) {

        //using the actually controls to mute YTTV because for whatever reason, it will unmute itself
        if (window.location.hostname == 'tv.youtube.com' && document.querySelector('[aria-label="Mute (m)"]')) {
            document.querySelector('[aria-label="Mute (m)"]').click();
        }

        mainVideo.muted = true;

    } else if (mainVideoVolumeDuringCommercials < 1) {

        mainVideo.volume = mainVideoVolumeDuringCommercials;

    } //else do nothing for 100

    //wait a little bit for the video to load //TODO: get indicator of when completely loaded
    setTimeout(() => {
        chrome.runtime.sendMessage({ action: "initial_execute_overlay_video_interaction" });
    }, 2000);

}


//switches to non-commercial state which means hiding the overlay video and unmuting the main video
function endCommercialMode() {

    isCommercialState = false;

    chrome.runtime.sendMessage({ action: "execute_overlay_video_non_commercial_state" });
    overlayVideo.style.visibility = "hidden";

    if (mainVideoFade > 0) {
        if (commercialDetectionMode != 'auto') {
            overlayScreen.style.backgroundColor = "transparent";
        } else {
            overlayScreen.style.boxShadow = "0 0 0";
        }
    }

    if (mainVideoVolumeDuringCommercials == 0) {
        if (window.location.hostname == 'tv.youtube.com' && document.querySelector('[aria-label="Unmute (m)"]')) {
            document.querySelector('[aria-label="Unmute (m)"]').click();
        }
        mainVideo.muted = false;
    } else if (mainVideoVolumeDuringCommercials < 1) {
        mainVideo.volume = mainVideoVolumeDuringNonCommercials;
    } //else do nothing for 100

}


//switches to commercial state which means showing the overlay video and muting the main/background video
function startCommercialMode() {

    if (commercialDetectionMode == 'auto' && isAutoModeFirstCommercial) {

        //check again if in full screen in case user exited
        if (document.fullscreenElement) {

            isCommercialState = true;

            isAutoModeFirstCommercial = false;
            //setting cooldown time so video has a chance to play for the first time
            cooldownCountRemaining = 6;
            initialRun();

        } else {
            setNotFullscreenAlerts();
        }
        

    } else {

        isCommercialState = true;

        chrome.runtime.sendMessage({ action: "execute_overlay_video_commercial_state" });

        if (mainVideoFade > 0) {
            if (commercialDetectionMode != 'auto') {
                overlayScreen.style.backgroundColor = "rgba(0, 0, 0, ." + mainVideoFade + ")";
            } else {
                overlayScreen.style.boxShadow = "0 0 0 99999px rgba(0, 0, 0, ." + mainVideoFade + ")";
            }
        }

        if (mainVideoVolumeDuringCommercials == 0) {
            if (window.location.hostname == 'tv.youtube.com' && document.querySelector('[aria-label="Mute (m)"]')) {
                document.querySelector('[aria-label="Mute (m)"]').click();
            }
            mainVideo.muted = true;
        } else if (mainVideoVolumeDuringCommercials < 1) {
            mainVideo.volume = mainVideoVolumeDuringCommercials;
        } //else do nothing for 100

        overlayVideo.style.visibility = "visible";

    }

}


//TODO: made it so the manual override works before the video ever comes up on its own
//background.js is listening for user to enter in keyboard shortcut then sending a message to intiate this
chrome.runtime.onMessage.addListener(function (message) {

    if (message.action === "execute_manual_switch_function") {

        //special actions for the very first time this is initiated on a page
        if (isFirstRun) {

            //extension can only be initiated for the first time if user is in full screen mode, this is needed to find out where to place the overlay video
            if (document.fullscreenElement) {

                //TODO: look into why this would ever return iframe and why I'm stopping because of it - I think it is because if the iframe is fullscreened then that means something inside of it would also count as fullscreened, see espn.com/watch for example
                if (document.fullscreenElement.nodeName != 'IFRAME') {

                    //TODO: grab user set variables here

                    //setting up for pixel selection for auto mode or continuing run for manual
                    if (commercialDetectionMode == 'auto') {

                        if (!isAutoModeInitiated) {

                            isAutoModeInitiated = true;

                            startViewingTab();

                            document.addEventListener('fullscreenchange', abortPixelSelection);

                            //give a sec for recording to start before asking user to pick a pixel
                            setTimeout(() => {
                                setBlockersAndPixelSelectionInstructions();
                                document.addEventListener('click', pixelSelection);
                            }, 1000);

                        } //else do nothing //TODO: add else here that removes instructions and event listener and sets isAutoModeInitiated to false so if user initiated too early previously, they can try again later

                    } else {

                        initialRun();

                    }

                } //else do nothing for when nodeName is IFRAME

            } else if (overlayHostName == 'www.youtube.com') { //TODO: find a better way to not show this warning on overlay video when using non-yt videos and maybe not even let it get to this point
                //since user was not in full screen, instruct them that they need to be

                setNotFullscreenAlerts();

            }
            
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


//sets text over top of every video on the page letting the user know that they need to be fullscreen for the extension to work
function setNotFullscreenAlerts() {

    if (!fullScreenAlertSet && document.getElementsByTagName('video')[0]) {

        let potentialVideos = document.getElementsByTagName('video');

        for (let i = 0; i < potentialVideos.length; i++) {

            let elm = document.createElement('div');
            elm.className = "not-full-screen-alert";
            elm.textContent = 'Video must be full screen for YTOC extension to work.'

            let insertLocation = potentialVideos[i].parentNode;
            insertLocation = insertLocation.parentNode;
            insertLocation.insertBefore(elm, null);

        }

        fullScreenAlertSet = true;

    }

}


//remove all full screen alerts if previously set
function removeNotFullscreenAlerts() {

    removeElementsByClass('not-full-screen-alert');
    fullScreenAlertSet = false;

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

    overlayInstructions = document.createElement('div');
    overlayInstructions.className = "ytoc-overlay-instructions";
    insertLocationFullscreenElm.insertBefore(overlayInstructions, null);

    overlayInstructions.style.visibility = "visible";
    overlayInstructions.style.setProperty("width", videoOverlayWidth + "%", "important");
    overlayInstructions.style.setProperty("height", videoOverlayHeight + "%", "important");
    //overlayInstructions.style.setProperty("border", "3px red solid", "important");

    //setting overlay video in user set location
    if (overlayVideoLocationHorizontal == 'left' || overlayVideoLocationHorizontal == 'middle') {
        overlayInstructions.style.setProperty("left", "0", "important");
    }
    if (overlayVideoLocationHorizontal == 'right' || overlayVideoLocationHorizontal == 'middle') {
        overlayInstructions.style.setProperty("right", "0", "important");
    }
    if (overlayVideoLocationVertical == 'top' || overlayVideoLocationVertical == 'middle') {
        overlayInstructions.style.setProperty("top", "0", "important");
    }
    if (overlayVideoLocationVertical == 'bottom' || overlayVideoLocationVertical == 'middle') {
        overlayInstructions.style.setProperty("bottom", "0", "important");
    }

    //hide verticle scrollbar if video placed on bottom
    if (overlayVideoLocationVertical == 'bottom') {
        let hideScollStyle = document.createElement("style");
        hideScollStyle.textContent = `
        ::-webkit-scrollbar {
            display: none;
        }`
        insertLocation.appendChild(hideScollStyle);
    }

    //TODO: fix issue where if user places video at bottom of some sites like peacock, it adds scrollbar to whole page
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

        //subtracting by 1 so it doesn't accidentally capture the cursor if it still happens to be showing
        selectedPixel = { x: (event.clientX - 1), y: (event.clientY - 2) };

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
        const originalPixelColor = pixelColor;

        logoBox.style.backgroundColor = "rgba(" + originalPixelColor.r + ", " + originalPixelColor.g + ", " + originalPixelColor.b + ", 1)";
        //deciding whether to set text as white or black based on background color
        if ((originalPixelColor.r * 0.299 + originalPixelColor.g * 0.587 + originalPixelColor.b * 0.114) > 150) {
            logoBox.style.color = "rgba(0, 0, 0, 1)";
        } else {
            logoBox.style.color = "rgba(255, 255, 255, 1)";
        }

        //wait a sec to remove pixel selected message and replace with logo to let the user read message
        setTimeout(() => {
            logoBox.textContent = 'YTOC';
            if (!isDebugMode) { logoBox.style.display = 'none'; }
            removeElementsByClass('ytoc-selection-indicator');
        }, 2000);

        pixelColorMatchMonitor(originalPixelColor, selectedPixel);

    })
    .catch(function (error) {
        console.error(error);
    });

}


//checks the color of the user set pixel and compares it to the original color in intervals and initiates commercial or non-commercial mode accordingly
function pixelColorMatchMonitor(originalPixelColor, selectedPixel) {

    setInterval(() => {
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

                mismatchCount++;
                matchCount = 0;
                logoCountdownMismatchesRemaining = (mismatchCountThreshold - mismatchCount);

                //show countdown if 3 seconds until commercial mode or it would be 3 seconds until commercial mode and cooldown is blocking
                if (logoCountdownMismatchesRemaining <= 3 && !isCommercialState) {

                    if (cooldownCountRemaining >= 1) {

                        logoBox.textContent = cooldownCountRemaining;
                        logoBox.style.display = 'block';

                    } else if (logoCountdownMismatchesRemaining >= 1) {

                        logoBox.textContent = logoCountdownMismatchesRemaining;
                        logoBox.style.display = 'block';

                    }

                }

                if (mismatchCount >= mismatchCountThreshold && cooldownCountRemaining <= 0) {

                    if (!isCommercialState) {

                        if (isDebugMode) { console.log('commercial detected'); }

                        startCommercialMode();

                        logoBox.textContent = "YTOC"
                        logoBox.style.color = "rgba(" + pixelColor.r + ", " + pixelColor.g + ", " + pixelColor.b + ", 1)";
                        logoBox.style.display = 'block';
                        if (!isDebugMode) {
                            setTimeout(() => {
                                logoBox.style.display = 'none';
                            }, 5000);
                        }

                    }

                    //TODO: find out if this is better inside the if above or here, especially as it relates to manual switching during auto mode
                    mismatchCount = 0;

                }

            } else {

                matchCount++;
                mismatchCount = 0;

                if (!isDebugMode) { logoBox.style.display = 'none'; }
                logoBox.textContent = "YTOC"

                if (matchCount >= matchCountThreshold && cooldownCountRemaining <= 0) {

                    if (isCommercialState) {

                        if (isDebugMode) { console.log('commercial undetected'); }

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
    logoBox.textContent = 'PIXEL SELECTED!';
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
function startViewingTab() {

    let windowDimensions = { x: window.innerWidth, y: window.innerHeight };

    chrome.runtime.sendMessage({ action: "view-tab", windowDimensions: windowDimensions });

    window.addEventListener('beforeunload', stopViewingTab);

}


//TODO: maybe have this close the offscreen doc instead and get rid of the fancy offscreen management
function stopViewingTab() {

    //close offscreen.js
    chrome.runtime.sendMessage({
        target: "offscreen",
        action: "close"
    });

    window.removeEventListener('beforeunload', stopViewingTab);

}



function fullscreenChanged() {
    if (!document.fullscreenElement) {
        //TODO: Make this temporarily pause extension and not show overlay video until user is back in full screen and without offscreen.js self destructing
        document.removeEventListener('fullscreenchange', fullscreenChanged);

        alert('Note: To enter full screen again, attempt to do so like normal, but then hit F11 on keyboard.');
        
    }
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