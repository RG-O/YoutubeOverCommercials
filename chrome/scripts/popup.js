//TODO: hide ID text fields when corresponding radio button not checked

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
    'shouldHideYTBackground'
], (result) => {

    //set them to default if not set by user yet
    optionsForm.overlayVideoType.value = result.overlayVideoType ?? 'yt-playlist';
    optionsForm.ytPlaylistID.value = result.ytPlaylistID ?? 'PLt982az5t-dVn-HDI4D7fnvMXt8T9_OGB';
    optionsForm.ytVideoID.value = result.ytVideoID ?? '5AMQbxBZohY';
    optionsForm.ytLiveID.value = result.ytLiveID ?? 'QhJcIlE0NAQ';
    optionsForm.otherVideoURL.value = result.otherVideoURL ?? 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/TearsOfSteel.mp4';
    optionsForm.otherLiveURL.value = result.otherLiveURL ?? 'https://tv.youtube.com/watch/_2ONrjDR7S8?vp=0gEEEgIwAQ%3D%3D';
    optionsForm.overlayVideoLocationHorizontal.value = result.overlayVideoLocationHorizontal ?? 'middle';
    optionsForm.overlayVideoLocationVertical.value = result.overlayVideoLocationVertical ?? 'middle';
    optionsForm.mainVideoFade.value = result.mainVideoFade ?? 35;
    optionsForm.videoOverlayWidth.value = result.videoOverlayWidth ?? 75;
    optionsForm.videoOverlayHeight.value = result.videoOverlayHeight ?? 75;
    optionsForm.mainVideoVolumeDuringCommercials.value = result.mainVideoVolumeDuringCommercials ?? 0;
    optionsForm.mainVideoVolumeDuringNonCommercials.value = result.mainVideoVolumeDuringNonCommercials ?? 100;
    optionsForm.shouldHideYTBackground.checked = result.shouldHideYTBackground ?? true;
    
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
        optionsForm.mainVideoVolumeDuringNonCommercials.value
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
            shouldHideYTBackground: optionsForm.shouldHideYTBackground.checked
        }, function () {
            window.close();
            alert("Changes saved successfully! Note: May need to refresh page to have all updates take effect.");
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
}


//close chrome extension window if they click to close
document.getElementById("close-button").onclick = function () {
    window.close();
}