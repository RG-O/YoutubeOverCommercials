
//establish variables
var isCommercialState = false;
var firstClick = true;
var mainVideo;
var isFirstRun = true;
var fullScreenAlertSet = false;
var overlayScreen;
var overlayVideo;
var selectedPixel = null;
var isAutoModeFirstCommercial = true;
var mismatchCount = 0;
var matchCount = 0;

//TODO: Set as user prefs
var isDebugMode = true;
var mismatchCountThreshold = 4; //22 to account for replays?
var matchCountThreshold = 2;
var commercialDetectionMode = 'auto';

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
    'shouldHideYTBackground'
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
    mainVideoFade = result.mainVideoFade ?? 30;
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

});

//function that is responsible for loading the video iframe over top of the main/background video
function setOverlayVideo() {

    mainVideo = document.getElementsByTagName('video')[0]; //TODO: grab all videos on page and loop and interaction with all of them

    //TODO: add check to make sure user is still in full screen and if not to break and resut isFirstRun
    let insertLocation = document.fullscreenElement;
    if (insertLocation.nodeName == 'HTML') {
        insertLocation = document.getElementsByTagName('body')[0];
    }

    let firstChild = insertLocation.firstChild;
    overlayVideo = document.createElement('div');
    overlayVideo.className = "ytoc-overlay-video";
    //TODO: replace firstChild with null since the last items is actually most likely to show on top?
    insertLocation.insertBefore(overlayVideo, firstChild);
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

    //adding an overlay to darken the main/background video during commercials if user has chosen to do so
    if (mainVideoFade > 0 && commercialDetectionMode != 'auto') {

        overlayScreen = document.createElement('div');
        overlayScreen.className = "ytoc-overlay-screen";
        overlayScreen.style.backgroundColor = "rgba(0, 0, 0, ." + mainVideoFade + ")";
        insertLocation.insertBefore(overlayScreen, firstChild);

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

    //remove all full screen alerts if previously set
    removeElementsByClass('not-full-screen-alert');
    
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

    if (mainVideoFade > 0 && commercialDetectionMode != 'auto') {
        overlayScreen.style.backgroundColor = "transparent";
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

    isCommercialState = true;

    if (commercialDetectionMode == 'auto' && isAutoModeFirstCommercial) {

        isAutoModeFirstCommercial = false;

        initialRun();

    } else {

        chrome.runtime.sendMessage({ action: "execute_overlay_video_commercial_state" });

        if (mainVideoFade > 0 && commercialDetectionMode != 'auto') {
            overlayScreen.style.backgroundColor = "rgba(0, 0, 0, ." + mainVideoFade + ")";
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


//TODO: seperate these different paths into their own functions
//background.js is listening for user to enter in keyboard shortcut then sending a message to intiate this
chrome.runtime.onMessage.addListener(function (message) {

    if (message.action === "execute_manual_switch_function") {

        //special actions for the very first time this is initiated on a page
        if (isFirstRun) {

            //extension can only be initiated for the first time if user is in full screen mode, this is needed to find out where to place the overlay video
            if (document.fullscreenElement) {

                //TODO: look into why this would ever return iframe and why I'm stopping because of it
                if (document.fullscreenElement.nodeName != 'IFRAME') {

                    //setting up for pixel selection for auto mode or continuing run for manual
                    if (commercialDetectionMode == 'auto') {

                        setBlockersAndPixelSelectionInstructions();
                        //TODO: figure out if this makes sense to set isFirstRun here to avoid possible issues
                        isFirstRun = false;
                        document.addEventListener('click', pixelSelection);

                    } else {

                        initialRun();

                    }

                } //else do nothing for when nodeName is IFRAME

            } else if (overlayHostName == 'www.youtube.com') { //TODO: find a better way to not show this warning on overlay video when using non-yt videos and maybe not even let it get to this point
                //since user was not in full screen, instruct them that they need to be

                if (!fullScreenAlertSet && document.getElementsByTagName('video')[0]) {

                    //TODO: move into own function
                    let potentialVideos = document.getElementsByTagName('video');

                    for (let i = 0; i < potentialVideos.length; i++) {

                        let elm = document.createElement('div');
                        elm.className = "not-full-screen-alert";
                        elm.textContent = 'Must be full screen first'

                        let insertLocation = potentialVideos[i].parentNode;
                        insertLocation = insertLocation.parentNode;
                        let firstChild = insertLocation.firstChild;
                        insertLocation.insertBefore(elm, firstChild);

                    }

                    fullScreenAlertSet = true;

                }

            }
            
        } else {

            //TODO: set the mismatch and match counts to some negative number in here
            if (isCommercialState) {

                endCommercialMode();

            } else {

                startCommercialMode();

            }

        }

    }

});

//sets blockers so users cursor movement doesn't trigger any of the main/background video's UI to display and keeps click from pausing video
//also displays instructions to user for selecting pixel
function setBlockersAndPixelSelectionInstructions() {

    let clickBlocker1 = document.createElement('div');
    clickBlocker1.className = "ytoc-click-blocker";

    let insertLocation = document.getElementsByTagName('body')[0];
    insertLocation.insertBefore(clickBlocker1, null);

    let insertLocationFullscreenElm = document.fullscreenElement;

    //TODO: figure out better way to suppress UI from showing if there is a mousemove event on the top level full screen element like for vimeo
    //insertLocationFullscreenElm.classList.add("ytoc-click-blocker-addition");

    if (insertLocationFullscreenElm.nodeName == 'HTML') {
        insertLocationFullscreenElm = document.getElementsByTagName('body')[0];
    }

    let clickBlocker2 = document.createElement('div');
    clickBlocker2.className = "ytoc-click-blocker";

    insertLocationFullscreenElm.insertBefore(clickBlocker2, null);

    let overlayInstructions = document.createElement('div');
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

    //TODO: fix issue where if user places video at bottom of some sites like peacock, it adds scrollbar to whole page
    let iFrame = document.createElement('iframe');
    iFrame.src = chrome.extension.getURL("pixel-select-instructions.html");
    iFrame.width = "100%";
    iFrame.height = "100%";
    iFrame.allow = "autoplay; encrypted-media";
    iFrame.frameBorder = "0";
    iFrame.style.setProperty("border", "3px red solid", "important");

    overlayInstructions.appendChild(iFrame);

}


function pixelSelection(event) {

    //TODO: figure out if this check is really necessary
    if (!selectedPixel) {


        removeElementsByClass('not-full-screen-alert');
        removeElementsByClass('ytoc-overlay-instructions');
        //wait a sec to remove the click blocker so UI doesn't pop up right away
        setTimeout(() => {
            removeElementsByClass('ytoc-click-blocker');
        }, 3000);

        document.removeEventListener('click', pixelSelection);


        selectedPixel = { x: event.clientX, y: event.clientY };
        console.log(`Selected pixel location: (${selectedPixel.x}, ${selectedPixel.y})`); //debug

        //TODO: break this out to take captureOriginalPixelColor() or something like that and then like pixelColorMonitor()
        takeScreenshot(selectedPixel)
            .then(function (pixelColor) {

                //establish original pixel color
                const [orgR, orgG, orgB, orgA] = pixelColor;
                //const [orgH, orgS, orgL] = rgbToHsl(orgR, orgG, orgB);

                setInterval(() => {
                    //TODO: set some sort of pause on this interval if user leaves full screen

                    takeScreenshot(selectedPixel)
                        .then(function (pixelColor) {

                            //current color of pixel
                            let [r, g, b, a] = pixelColor; //debug - I switched this from const to let
                            //const [h, s, l] = rgbToHsl(r, g, b);

                            console.log('%cOriginal pixel color = rgba(' + orgR + ', ' + orgG + ', ' + orgB + ', ' + orgA + ')', 'background: rgba(' + orgR + ', ' + orgG + ', ' + orgB + ', ' + orgA + ')'); //debug
                            console.log('%cCurrent pixel color = rgba(' + r + ', ' + g + ', ' + b + ', ' + a + ')', 'background: rgba(' + r + ', ' + g + ', ' + b + ', ' + a + ')'); //debug

                            //console.log('%cOriginal pixel color = hsl(' + orgH + ', ' + orgS + ', ' + orgL); //debug
                            //console.log('%cCurrent pixel color = hsl(' + h + ', ' + s + ', ' + l + ')'); //debug

                            let redDifference = Math.abs(orgR - r);
                            let greenDifference = Math.abs(orgG - g);
                            let blueDifference = Math.abs(orgB - b);
                            let alphaDifference = Math.abs(orgA - a); //TODO: should I even check this?

                            console.log('%cPixel color difference = rgba(' + redDifference + ', ' + greenDifference + ', ' + blueDifference + ', ' + alphaDifference); //debug

                            //TODO: create user preference for going by rgb or hsl, actually, maybe have it be two separate buttons?
                            //TODO: add a current state check so I only call to update when state changes
                            //TODO: set to be a consecutive number of times before it changes?
                            //TODO: update to user set values
                            if (
                                redDifference > 10 ||
                                greenDifference > 10 ||
                                blueDifference > 10
                            ) {

                                mismatchCount++;
                                matchCount = 0;

                                if (mismatchCount >= mismatchCountThreshold) {

                                    if (!isCommercialState) {

                                        startCommercialMode();
                                        
                                        console.log('Pixel color changed'); //debug

                                        //TODO: add these as a debug option for the the users
                                        //videoTextOverlay.style.backgroundColor = 'rgba(' + orgR + ', ' + orgG + ', ' + orgB + ', ' + orgA + ')';
                                        //videoTextOverlay.style.color = 'rgba(' + r + ', ' + g + ', ' + b + ', ' + a + ')';
                                        //videoTextOverlay.textContent = "COMMERCIAL DETECTED";

                                    }

                                    //TODO: find out if this is better inside the if above or here, especially as it relates to manual switching during auto mode
                                    mismatchCount = 0;

                                }

                            } else {

                                matchCount++;
                                mismatchCount = 0;

                                if (matchCount >= matchCountThreshold) {

                                    if (isCommercialState) {

                                        endCommercialMode();

                                        //TODO: add this as a debug option
                                        //videoTextOverlay.textContent = "";

                                    }

                                    //TODO: find out if this is better inside the if above or here, especially as it relates to manual switching during auto mode
                                    matchCount = 0;

                                }
                            }

                        })
                        .catch(function (error) {
                            console.error(error);
                        });

                }, 1000);

            })
            .catch(function (error) {
                console.error(error);
            });

    }

}


function rgbToHsl(r, g, b) {
    r /= 255, g /= 255, b /= 255;
    var max = Math.max(r, g, b), min = Math.min(r, g, b);
    var h, s, l = (max + min) / 2;

    if (max == min) {
        h = s = 0; // achromatic
    } else {
        var d = max - min;
        s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
        switch (max) {
            case r: h = (g - b) / d + (g < b ? 6 : 0); break;
            case g: h = (b - r) / d + 2; break;
            case b: h = (r - g) / d + 4; break;
        }
        h /= 6;
    }

    return [Math.floor(h * 360), Math.floor(s * 100), Math.floor(l * 100)];
}

//TODO: swtich vars and consts to lets
//TODO: rename to grabPixelColor() or something like that
function takeScreenshot(coordinates) {
    console.log('content.js running takeScreenshot'); //debug

    return new Promise(function (resolve, reject) {

        var rect = { x: coordinates.x, y: coordinates.y, width: 1, height: 1 };

        chrome.runtime.sendMessage({ action: "capture-screenshot", rect: rect }, function (response) {

            console.log(response.imgSrc); //debug

            var image = new Image();
            image.src = response.imgSrc;

            console.log('i am here'); //debug

            image.addEventListener('load', function () {

                console.log('i am here2'); //debug

                var canvas = document.createElement('canvas');
                var context = canvas.getContext('2d');

                //var viewPortWidth = window.innerWidth; //debug
                //var viewPortHeight = window.innerHeight;
                //console.log('current viewport:' + viewPortWidth + "x" + viewPortHeight);
                //console.log('current pixel ratio:' + window.devicePixelRatio);

                canvas.width = image.width; //TODO: figure out is this necessary with setting it in draw image?
                canvas.height = image.height;
                context.drawImage(image, 0, 0);

                //var x = (coordinates.x * window.devicePixelRatio); //debug
                //var y = (coordinates.y * window.devicePixelRatio);
                //console.log(`Screen density relative pixel location: (${x}, ${y})`);
                //var pixelColor = context.getImageData(x, y, 1, 1).data;

                var pixelColor = context.getImageData(0, 0, 1, 1).data;
                const [r, g, b, a] = pixelColor;
                console.log(`rgba(${r}, ${g}, ${b}, ${a})`);

                resolve(pixelColor); // Resolve the promise with myString value

            });

        });

    });

}