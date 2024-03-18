
//Establish variables
var isCommercialState = false;
var firstClick = true;
var mainVideo;
var isFirstRun = true;
var fullScreenAlertSet = false;
var overlayScreen;
var overlayVideo;

var overlayVideoType;
var ytPlaylistID;
var ytVideoID;
var ytLiveID;
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
    ytVideoID = result.ytVideoID ?? 's86-Z-CbaHA';
    ytLiveID = result.ytLiveID ?? 'QhJcIlE0NAQ';
    overlayVideoLocationHorizontal = result.overlayVideoLocationHorizontal ?? 'middle';
    overlayVideoLocationVertical = result.overlayVideoLocationVertical ?? 'middle';
    mainVideoFade = result.mainVideoFade ?? 50;
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

    let insertLocation = document.fullscreenElement;
    if (insertLocation.nodeName == 'HTML') {
        insertLocation = document.getElementsByTagName('body')[0];
    }

    let firstChild = insertLocation.firstChild;
    overlayVideo = document.createElement('div');
    overlayVideo.className = "ytoc-overlay-video";
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
    }

    let iFrame = document.createElement('iframe');
    iFrame.src = url;
    iFrame.width = "100%";
    iFrame.height = "100%";
    iFrame.allow = "autoplay; encrypted-media";
    iFrame.frameBorder = "0";

    overlayVideo.appendChild(iFrame);

    //adding an overlay to darken the main/background video during commercials if user has chosen to do so
    if (mainVideoFade > 0) {

        overlayScreen = document.createElement('div');
        overlayScreen.className = "ytoc-overlay-screen";
        overlayScreen.style.backgroundColor = "rgba(0, 0, 0, ." + mainVideoFade + ")";
        insertLocation.insertBefore(overlayScreen, firstChild);

    }

    isFirstRun = false;

}

//background.js is listening for user to enter in keyboard shortcut then sending a message to intiate this
chrome.runtime.onMessage.addListener(function (message) {

    if (message.action === "execute_manual_switch_function") {

        //special actions for the very first time this is initiated on a page
        if (isFirstRun) {

            //extension can only be initiated for the first time if user is in full screen mode, this is needed to find out where to place the overlay video
            if (document.fullscreenElement) {

                //TODO: look into why this would ever return iframe and why I'm stopping because of it
                if (document.fullscreenElement.nodeName != 'IFRAME') {

                    //removing the not full screen alert if previously set
                    if (document.getElementsByClassName('not-full-screen-alert')[0]) {

                        let elements = document.getElementsByClassName('not-full-screen-alert');
                        let element;

                        //doing this weird since getElementsByClassName returns a live collection
                        while (element = elements[0]) {
                            element.parentNode.removeChild(element);
                        }

                    }

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

                    isCommercialState = true;
                    isFirstRun = false;

                } //else do nothing for when nodeName is IFRAME

            } else {
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

            if (isCommercialState) {
                //switching to non-commercial state which means hiding the overlay video and unmuting the main video

                isCommercialState = false;

                chrome.runtime.sendMessage({ action: "execute_overlay_video_non_commercial_state" });
                overlayVideo.style.visibility = "hidden";

                if (mainVideoFade > 0) {
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

            } else {
                //switching to commercial state which means showing the overlay video and muting the main/background video

                isCommercialState = true;

                chrome.runtime.sendMessage({ action: "execute_overlay_video_commercial_state" });

                if (mainVideoFade > 0) {
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

    }

});