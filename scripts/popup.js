
var isFirefox = false; //********************


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
    'shouldHideYTBackground',
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
    'shouldClickNextOnPlaySpotify',
    'isOverlayVideoZoomMode',
    'isOtherSiteTroubleshootMode',
    'isOppositePixelDetectionMode'
], (result) => {

    //set them to default if not set by user yet
    optionsForm.overlayVideoType.value = result.overlayVideoType ?? 'yt-playlist';
    optionsForm.ytPlaylistID.value = result.ytPlaylistID ?? 'PLt982az5t-dVn-HDI4D7fnvMXt8T9_OGB';
    optionsForm.ytVideoID.value = result.ytVideoID ?? '5AMQbxBZohY';
    optionsForm.ytLiveID.value = result.ytLiveID ?? 'QhJcIlE0NAQ';
    optionsForm.otherVideoURL.value = result.otherVideoURL ?? 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/TearsOfSteel.mp4';
    optionsForm.otherLiveURL.value = result.otherLiveURL ?? 'https://tv.youtube.com/watch/_2ONrjDR7S8';
    optionsForm.overlayVideoLocationHorizontal.value = result.overlayVideoLocationHorizontal ?? 'middle';
    optionsForm.overlayVideoLocationVertical.value = result.overlayVideoLocationVertical ?? 'middle';
    optionsForm.mainVideoFade.value = result.mainVideoFade ?? 65;
    optionsForm.videoOverlayWidth.value = result.videoOverlayWidth ?? 75;
    optionsForm.videoOverlayHeight.value = result.videoOverlayHeight ?? 75;
    optionsForm.mainVideoVolumeDuringCommercials.value = result.mainVideoVolumeDuringCommercials ?? 0;
    optionsForm.mainVideoVolumeDuringNonCommercials.value = result.mainVideoVolumeDuringNonCommercials ?? 100;
    optionsForm.shouldHideYTBackground.checked = result.shouldHideYTBackground ?? true;
    optionsForm.commercialDetectionMode.value = result.commercialDetectionMode ?? 'auto';
    optionsForm.mismatchCountThreshold.value = result.mismatchCountThreshold ?? 8;
    optionsForm.matchCountThreshold.value = result.matchCountThreshold ?? 2;
    optionsForm.colorDifferenceMatchingThreshold.value = result.colorDifferenceMatchingThreshold ?? 12;
    optionsForm.manualOverrideCooldown.value = result.manualOverrideCooldown ?? 30;
    optionsForm.isDebugMode.checked = result.isDebugMode ?? false;
    optionsForm.isPiPMode.checked = result.isPiPMode ?? true;
    optionsForm.pipLocationHorizontal.value = result.pipLocationHorizontal ?? 'left';
    optionsForm.pipLocationVertical.value = result.pipLocationVertical ?? 'top';
    optionsForm.pipHeight.value = result.pipHeight ?? 20;
    optionsForm.pipWidth.value = result.pipWidth ?? 20;
    optionsForm.shouldClickNextOnPlaySpotify.checked = result.shouldClickNextOnPlaySpotify ?? true;
    optionsForm.isOverlayVideoZoomMode.checked = result.isOverlayVideoZoomMode ?? false;
    optionsForm.isOtherSiteTroubleshootMode.checked = result.isOtherSiteTroubleshootMode ?? false;
    optionsForm.isOppositePixelDetectionMode.checked = result.isOppositePixelDetectionMode ?? false;

    document.getElementById(optionsForm.commercialDetectionMode.value).style.display = 'block';
    const modeRadios = document.forms["optionsForm"].elements["commercialDetectionMode"];
    for (let i = 0, max = modeRadios.length; i < max; i++) {
        modeRadios[i].addEventListener('change', toggleModeInstructionsVisability);
    }

    document.getElementById(optionsForm.overlayVideoType.value).style.display = 'block';
    const videoTypeRadios = document.forms["optionsForm"].elements["overlayVideoType"];
    for (let i = 0, max = videoTypeRadios.length; i < max; i++) {
        videoTypeRadios[i].addEventListener('change', toggleIDFieldVisability);
    }

    setKeyboardShortcutText();
    togglePiPFieldsVisability();
    document.getElementById('isPiPMode').addEventListener('change', togglePiPFieldsVisability);

});


//if user clicks the save button, save all their values to their chrome profile
document.getElementById("save-button").onclick = function () {

    //check to see if they have inputed all the fields (except for checkboxes), alert them if they haven't
    if (
        optionsForm.overlayVideoType.value &&
        //TODO: add a special check to these so they are only needed if their type is selected
        optionsForm.ytPlaylistID.value &&
        optionsForm.ytVideoID.value &&
        optionsForm.ytLiveID.value &&
        optionsForm.otherVideoURL.value &&
        optionsForm.otherLiveURL.value &&
        optionsForm.overlayVideoLocationHorizontal.value &&
        optionsForm.overlayVideoLocationVertical.value &&
        optionsForm.mainVideoFade.value &&
        optionsForm.videoOverlayWidth.value &&
        optionsForm.videoOverlayHeight.value &&
        optionsForm.mainVideoVolumeDuringCommercials.value &&
        optionsForm.mainVideoVolumeDuringNonCommercials.value &&
        optionsForm.commercialDetectionMode.value &&
        optionsForm.mismatchCountThreshold.value &&
        optionsForm.matchCountThreshold.value &&
        optionsForm.colorDifferenceMatchingThreshold.value &&
        optionsForm.manualOverrideCooldown.value &&
        optionsForm.pipLocationHorizontal.value &&
        optionsForm.pipLocationVertical.value &&
        optionsForm.pipHeight.value &&
        optionsForm.pipWidth.value
    ) {

        let overlayHostName;
        if (optionsForm.overlayVideoType.value === "other-video") {
            overlayHostName = new URL(optionsForm.otherVideoURL.value).hostname;
        } else if (optionsForm.overlayVideoType.value === "other-live") {
            overlayHostName = new URL(optionsForm.otherLiveURL.value).hostname;
        } else {
            overlayHostName = 'www.youtube.com';
        }

        //save the values to the users chrome profile, close the extension window, and then give them message telling them they might need to refresh
        chrome.storage.sync.set({
            overlayVideoType: optionsForm.overlayVideoType.value,
            ytPlaylistID: optionsForm.ytPlaylistID.value,
            ytVideoID: optionsForm.ytVideoID.value,
            ytLiveID: optionsForm.ytLiveID.value,
            otherVideoURL: optionsForm.otherVideoURL.value,
            otherLiveURL: optionsForm.otherLiveURL.value,
            overlayHostName: overlayHostName,
            overlayVideoLocationHorizontal: optionsForm.overlayVideoLocationHorizontal.value,
            overlayVideoLocationVertical: optionsForm.overlayVideoLocationVertical.value,
            mainVideoFade: optionsForm.mainVideoFade.value,
            videoOverlayWidth: optionsForm.videoOverlayWidth.value,
            videoOverlayHeight: optionsForm.videoOverlayHeight.value,
            mainVideoVolumeDuringCommercials: optionsForm.mainVideoVolumeDuringCommercials.value,
            mainVideoVolumeDuringNonCommercials: optionsForm.mainVideoVolumeDuringNonCommercials.value,
            shouldHideYTBackground: optionsForm.shouldHideYTBackground.checked,
            commercialDetectionMode: optionsForm.commercialDetectionMode.value,
            mismatchCountThreshold: optionsForm.mismatchCountThreshold.value,
            matchCountThreshold: optionsForm.matchCountThreshold.value,
            colorDifferenceMatchingThreshold: optionsForm.colorDifferenceMatchingThreshold.value,
            manualOverrideCooldown: optionsForm.manualOverrideCooldown.value,
            isDebugMode: optionsForm.isDebugMode.checked,
            isPiPMode: optionsForm.isPiPMode.checked,
            pipLocationHorizontal: optionsForm.pipLocationHorizontal.value,
            pipLocationVertical: optionsForm.pipLocationVertical.value,
            pipHeight: optionsForm.pipHeight.value,
            pipWidth: optionsForm.pipWidth.value,
            shouldClickNextOnPlaySpotify: optionsForm.shouldClickNextOnPlaySpotify.checked,
            isOverlayVideoZoomMode: optionsForm.isOverlayVideoZoomMode.checked,
            isOtherSiteTroubleshootMode: optionsForm.isOtherSiteTroubleshootMode.checked,
            isOppositePixelDetectionMode: optionsForm.isOppositePixelDetectionMode.checked
        }, function () {

            //TODO: get these values to update after extension has already been initiated - partially completed with background_update_preferences
            chrome.runtime.sendMessage({ action: "background_update_preferences" });
            //note: order of when the window is closed is important as firefox stops processing anything in popup.js once the popup window is closed
            window.close();
            //TODO: get this message to actually display correctly for firefox
            if (!isFirefox) {
                //TODO: only show this message if one of these values have been updated and extension has already been initiated
                alert("Changes saved successfully! Note: If extension has already been initiated, you may need to refresh page for some updates take effect.");
            }

        });

    } else {
        alert('Field missing. Please input all fields.');
    }

}


//uncollapse advanced settings if user clicks button to do so
document.getElementById("expand-button").onclick = function () {
    this.classList.toggle("button-hidden");
    var content = this.nextElementSibling;
    content.style.display = "block";
    //reduce size of elements to account for firefox scroll bar showing over fields
    document.getElementsByTagName('form')[0].style.width = '288px';
    document.getElementsByTagName('h1')[0].style.fontSize = '35px';
}


//close chrome extension window if they click to close
document.getElementById("close-button").onclick = function () {
    window.close();
}


//show/hide ID and URL fields when their corresponding radio button is checked/unchecked
function toggleIDFieldVisability() {
    let idFields = document.getElementsByClassName('id-field-wrapper');
    for (let i = 0, max = idFields.length; i < max; i++) {
        idFields[i].style.display = 'none';
    }
    document.getElementById(optionsForm.overlayVideoType.value).style.display = 'block';
}


//TODO: combine this function and one above for cleaner code
function toggleModeInstructionsVisability() {
    let modeInstructions = document.getElementsByClassName('commercial-detection-mode-instructions-wrapper');
    for (let i = 0, max = modeInstructions.length; i < max; i++) {
        modeInstructions[i].style.display = 'none';
    }
    document.getElementById(optionsForm.commercialDetectionMode.value).style.display = 'block';
}


//show/hide PiP fields when PiP mode checkbox is checked/unchecked
function togglePiPFieldsVisability() {
    if (optionsForm.isPiPMode.checked) {
        document.getElementsByClassName('pip-fields-wrapper')[0].style.display = 'block';
    } else {
        document.getElementsByClassName('pip-fields-wrapper')[0].style.display = 'none';
    }
}


function setKeyboardShortcutText() {
    if (isFirefox) {
        let keyboardShortcuts = document.getElementsByClassName('keyboard-shortcut');
        for (let i = 0, max = keyboardShortcuts.length; i < max; i++) {
            keyboardShortcuts[i].innerText = "Ctrl + Alt + C";
        }
    }
}