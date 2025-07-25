
var isFirefox = false; //********************
var profiles = {};
var gridCells;
var pipGridCells;

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
    'audioLevelThreshold',
    'shouldOverlayVideoSizeAndLocationAutoSet',
    'shouldShuffleYTPlaylist',
    'profiles'
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
    let commercialDetectionMode = result.commercialDetectionMode ?? 'auto-pixel-normal';
    //adjusting to updated settings for people that have already downloaded the extension (people set to opposite pixel mode will need to reselect in updated settings)
    if (commercialDetectionMode === 'auto') {
        commercialDetectionMode = 'auto-pixel-normal';
    }
    optionsForm.commercialDetectionMode.value = commercialDetectionMode;
    optionsForm.mismatchCountThreshold.value = result.mismatchCountThreshold ?? 8;
    optionsForm.matchCountThreshold.value = result.matchCountThreshold ?? 2;
    optionsForm.colorDifferenceMatchingThreshold.value = result.colorDifferenceMatchingThreshold ?? 14;
    optionsForm.manualOverrideCooldown.value = result.manualOverrideCooldown ?? 120;
    optionsForm.isDebugMode.checked = result.isDebugMode ?? false;
    optionsForm.isPiPMode.checked = result.isPiPMode ?? true;
    optionsForm.pipLocationHorizontal.value = result.pipLocationHorizontal ?? 'left';
    optionsForm.pipLocationVertical.value = result.pipLocationVertical ?? 'top';
    optionsForm.pipHeight.value = result.pipHeight ?? 20;
    optionsForm.pipWidth.value = result.pipWidth ?? 20;
    optionsForm.shouldClickNextOnPlaySpotify.checked = result.shouldClickNextOnPlaySpotify ?? true;
    optionsForm.isOverlayVideoZoomMode.checked = result.isOverlayVideoZoomMode ?? false;
    optionsForm.isOtherSiteTroubleshootMode.checked = result.isOtherSiteTroubleshootMode ?? false;
    optionsForm.audioLevelThreshold.value = result.audioLevelThreshold ?? 5;
    optionsForm.shouldOverlayVideoSizeAndLocationAutoSet.checked = result.shouldOverlayVideoSizeAndLocationAutoSet ?? false;
    optionsForm.shouldShuffleYTPlaylist.checked = result.shouldShuffleYTPlaylist ?? false;
    profiles = result.profiles || {};
    for (const name in profiles) {
        const option = document.createElement("option");
        option.value = name;
        option.textContent = name;
        optionsForm.profileSelect.appendChild(option);
    }

    document.getElementById(optionsForm.commercialDetectionMode.value).style.display = 'block';
    const modeRadios = document.forms["optionsForm"].elements["commercialDetectionMode"];
    for (let i = 0, max = modeRadios.length; i < max; i++) {
        modeRadios[i].addEventListener('change', toggleModeInstructionsVisability);
        modeRadios[i].addEventListener('change', toggleAutoDimensionsFieldVisability);
        modeRadios[i].addEventListener('change', toggleDimensionsFieldsVisability);
    }

    document.getElementById(optionsForm.overlayVideoType.value).style.display = 'block';
    const videoTypeRadios = document.forms["optionsForm"].elements["overlayVideoType"];
    for (let i = 0, max = videoTypeRadios.length; i < max; i++) {
        videoTypeRadios[i].addEventListener('change', toggleIDFieldVisability);
        videoTypeRadios[i].addEventListener('change', toggleWithIDProfileSaveButtonVisability);
        videoTypeRadios[i].addEventListener('change', updateSaveProfileButtonsText);
    }

    setTextFieldsToSelectAll();
    setKeyboardShortcutText();

    document.getElementById('shouldOverlayVideoSizeAndLocationAutoSet').addEventListener('change', toggleDimensionsFieldsVisability);
    document.getElementById('isPiPMode').addEventListener('change', togglePiPFieldsVisability);
    optionsForm.profileSelect.addEventListener('change', applyProfile);
    document.getElementById("saveProfile").addEventListener("click", function (event) {
        event.preventDefault(); //prevent popup from being reloaded
        saveProfile(false);
    });
    document.getElementById("saveProfileWithID").addEventListener("click", function (event) {
        event.preventDefault(); //prevent popup from being reloaded
        saveProfile(true);
    });
    optionsForm.deleteProfile.addEventListener("click", function (event) {
        event.preventDefault(); //prevent popup from being reloaded
        showConfirmDeleteProfilePrompt();
    });
    optionsForm.confirmDeleteProfile.addEventListener("click", function (event) {
        event.preventDefault(); //prevent popup from being reloaded
        hideConfirmDeleteProfilePrompt();
        deleteProfile();
    });
    optionsForm.cancelDeleteProfile.addEventListener("click", function (event) {
        event.preventDefault(); //prevent popup from being reloaded
        hideConfirmDeleteProfilePrompt();
    });
    optionsForm.profileName.addEventListener("input", function () {
        //only allow letters, numbers, dashes, and underscores
        optionsForm.profileName.value = optionsForm.profileName.value.replace(/[^A-Za-z0-9-_]/g, '');
        updateSaveProfileButtonsText();
    });

    //adding experimental tag to auto audio detect mode because it doesn't work as universally for firefox
    if (isFirefox) {
        document.getElementsByClassName('firefox-experimental')[0].style.display = 'inline';
        //document.getElementsByTagName('body')[0].style.width = '400px';
        document.getElementsByTagName('body')[0].style.paddingRight = '18px';
    }

    gridCells = document.querySelectorAll('.grid-cell');

    gridCells.forEach(cell => {
        cell.addEventListener('click', () => {
            const x = cell.getAttribute('data-x');
            const y = cell.getAttribute('data-y');

            optionsForm.overlayVideoLocationHorizontal.value = x;
            optionsForm.overlayVideoLocationVertical.value = y;

            clearOverlayDisplayPositionGrid();
            cell.classList.add('selected');
        });
    });

    pipGridCells = document.querySelectorAll('.pip-grid-cell');

    pipGridCells.forEach(cell => {
        cell.addEventListener('click', () => {
            const x = cell.getAttribute('data-pip-x');
            const y = cell.getAttribute('data-pip-y');

            optionsForm.pipLocationHorizontal.value = x;
            optionsForm.pipLocationVertical.value = y;

            clearPiPDisplayPositionGrid();
            cell.classList.add('selected');
        });
    });
    
    document.getElementById('pull-button-ytPlaylistID').addEventListener('click', async (event) => {
        event.preventDefault();
        let id = await getIDFromCurrentTab('list');
        if (id) {
            optionsForm.ytPlaylistID.value = id;
        }
    });

    document.getElementById('pull-button-ytVideoID').addEventListener('click', async (event) => {
        event.preventDefault();
        let id = await getIDFromCurrentTab('v');
        if (id) {
            optionsForm.ytVideoID.value = id;
        }
    });

    document.getElementById('pull-button-ytLiveID').addEventListener('click', async (event) => {
        event.preventDefault();
        let id = await getIDFromCurrentTab('v');
        if (id) {
            optionsForm.ytLiveID.value = id;
        }
    });

    document.getElementById('pull-button-otherVideoURL').addEventListener('click', async (event) => {
        event.preventDefault();
        let id = await getIDFromCurrentTab(false);
        if (id) {
            optionsForm.otherVideoURL.value = id;
        }
    });

    document.getElementById('pull-button-otherLiveURL').addEventListener('click', async (event) => {
        event.preventDefault();
        let id = await getIDFromCurrentTab(false);
        if (id) {
            optionsForm.otherLiveURL.value = id;
        }
    });

    //TODO: Do complete overhull of which fields hide/show (or enable/disable) when various commercial detection modes and overlay types are chosen
    runAllToggles();

});


//TODO: add check to see if user has new profile name entered that wasn't saved yet and then save this at the same time
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
            let otherVideoURLObj = new URL(optionsForm.otherVideoURL.value);
            if (otherVideoURLObj.pathname.toLowerCase().endsWith('.mp4')) {
                //set the overlayHostName to the extension id because if the url is an mp4, it will be inserted onto an extension page
                overlayHostName = window.location.host; //getting extension id from the extension popup
            } else {
                overlayHostName = otherVideoURLObj.hostname;
            }
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
            audioLevelThreshold: optionsForm.audioLevelThreshold.value,
            shouldOverlayVideoSizeAndLocationAutoSet: optionsForm.shouldOverlayVideoSizeAndLocationAutoSet.checked,
            shouldShuffleYTPlaylist: optionsForm.shouldShuffleYTPlaylist.checked
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
    ////reduce size of elements to account for firefox scroll bar showing over fields
    //document.getElementsByTagName('form')[0].style.width = '288px';
    //document.getElementsByTagName('h1')[0].style.fontSize = '35px';
}


//uncollapse profile settings
document.getElementById("newProfile").onclick = function () {
    showProfileUpdateSettings(false);
}


//close chrome extension window if they click to close
document.getElementById("close-button").onclick = function () {
    window.close();
}


function setTextFieldsToSelectAll() {
    document.querySelectorAll("input[type='text']").forEach(function (input) {
        input.addEventListener("focus", function () {
            this.select();
        });
    });
}


async function getIDFromCurrentTab(param) {
    let [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    if (param) {
        const url = new URL(tab.url);

        if (url.hostname === 'www.youtube.com') {
            let id = url.searchParams.get(param);

            if (id) {
                return id;
            } else {
                if (param === 'v') {
                    //TODO: Do something special for firefox here
                    alert('Sorry, YouTube video ID not found. Please navigate to the video you would like to use and try again. Or copy and paste the video ID into the field.');
                    return false;
                } else {
                    //TODO: Do something special for firefox here
                    alert('Sorry, YouTube playlist ID not found. Please navigate to the playlist you would like to use and try again. Or copy and paste the playlist ID into the field.');
                    return false;
                }
            }
            return url.searchParams.get(param) || 'ID not found';
        } else {
            //TODO: Do something special for firefox here
            alert('Must currently be on www.youtube.com in order to pull ID.');
            return false;
        }
    } else {
        return tab.url;
    }
}


function setOverlayDisplayPositionGrid() {
    const x = optionsForm.overlayVideoLocationHorizontal.value;
    const y = optionsForm.overlayVideoLocationVertical.value;
    clearOverlayDisplayPositionGrid();
    gridCells.forEach(cell => {
        if (cell.getAttribute('data-x') === x && cell.getAttribute('data-y') === y) {
            cell.classList.add('selected');
        }
    });
}

function clearOverlayDisplayPositionGrid() {
    gridCells.forEach(cell => cell.classList.remove('selected'));
}


function setPiPDisplayPositionGrid() {
    const x = optionsForm.pipLocationHorizontal.value;
    const y = optionsForm.pipLocationVertical.value;
    clearPiPDisplayPositionGrid();
    pipGridCells.forEach(cell => {
        if (cell.getAttribute('data-pip-x') === x && cell.getAttribute('data-pip-y') === y) {
            cell.classList.add('selected');
        }
    });
}

function clearPiPDisplayPositionGrid() {
    pipGridCells.forEach(cell => cell.classList.remove('selected'));
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


//show/hide auto overlay video dimension checkbox field when pixel modes are selected
function toggleAutoDimensionsFieldVisability() {
    if (optionsForm.commercialDetectionMode.value.indexOf('auto-pixel') < 0) {
        document.getElementsByClassName('auto-dimensions-field-wrapper')[0].style.display = 'none';
    } else {
        document.getElementsByClassName('auto-dimensions-field-wrapper')[0].style.display = 'block';
    }
}


//show/hide overlay video dimension fields when auto-set checkbox is checked/unchecked
function toggleDimensionsFieldsVisability() {
    if (optionsForm.shouldOverlayVideoSizeAndLocationAutoSet.checked && optionsForm.commercialDetectionMode.value.indexOf('auto-pixel') >= 0) {
        document.getElementsByClassName('dimensions-fields-wrapper')[0].style.display = 'none';
    } else {
        document.getElementsByClassName('dimensions-fields-wrapper')[0].style.display = 'block';
    }
}


//show/hide PiP fields when PiP mode checkbox is checked/unchecked
function togglePiPFieldsVisability() {
    if (optionsForm.isPiPMode.checked) {
        document.getElementsByClassName('pip-fields-wrapper')[0].style.display = 'block';
    } else {
        document.getElementsByClassName('pip-fields-wrapper')[0].style.display = 'none';
    }
}


function toggleWithIDProfileSaveButtonVisability() {
    if (optionsForm.overlayVideoType.value === 'spotify' || optionsForm.overlayVideoType.value === 'other-tabs') {
        document.getElementsByClassName('save-profile-with-id-wrapper')[0].style.display = 'none';
    } else {
        document.getElementsByClassName('save-profile-with-id-wrapper')[0].style.display = 'block';
    }
}


function updateSaveProfileButtonsText() {

    if (profiles.hasOwnProperty(optionsForm.profileName.value)) {
        optionsForm.saveProfile.textContent = 'Update Profile';
        optionsForm.saveProfileWithID.textContent = 'Update Profile';
    } else {
        optionsForm.saveProfile.textContent = 'Save New Profile';
        optionsForm.saveProfileWithID.textContent = 'Save New Profile';
    }

    if (optionsForm.overlayVideoType.value === 'yt-playlist') {
        optionsForm.saveProfile.textContent += ' (Exclude Playlist ID)';
        optionsForm.saveProfileWithID.textContent += ' (Include Playlist ID)';
    } else if (optionsForm.overlayVideoType.value === 'yt-video') {
        optionsForm.saveProfile.textContent += ' (Exclude Video ID)';
        optionsForm.saveProfileWithID.textContent += ' (Include Video ID)';
    } else if (optionsForm.overlayVideoType.value === 'yt-live') {
        optionsForm.saveProfile.textContent += ' (Exclude Live Video ID)';
        optionsForm.saveProfileWithID.textContent += ' (Include Live Video ID)';
    } else if (optionsForm.overlayVideoType.value === 'other-video') {
        optionsForm.saveProfile.textContent += ' (Exclude Video URL)';
        optionsForm.saveProfileWithID.textContent += ' (Include Video URL)';
    } else if (optionsForm.overlayVideoType.value === 'other-live') {
        optionsForm.saveProfile.textContent += ' (Exclude Stream URL)';
        optionsForm.saveProfileWithID.textContent += ' (Include Stream URL)';
    } //else do nothing for spotify and other-tabs as there is not an ID/URL to save

}


function hideConfirmDeleteProfilePrompt() {
    optionsForm.deleteProfile.style.display = 'block';
    document.getElementsByClassName("confirm-delete-profile-wrapper")[0].style.display = 'none';
}


function showConfirmDeleteProfilePrompt() {
    if (optionsForm.profileSelect.value) {
        document.getElementsByClassName("confirm-delete-profile-message")[0].textContent = `Are you sure you would like to delete profile ${optionsForm.profileSelect.value}?`;
        optionsForm.deleteProfile.style.display = 'none';
        document.getElementsByClassName("confirm-delete-profile-wrapper")[0].style.display = 'block';
    } else {
        addValidationMessage(optionsForm.profileSelect, 'error', 'Must select a profile to delete.');
    }
}


//run all toggles to make sure all information/fields hide/show/set based on values in the fields
function runAllToggles() {
    toggleModeInstructionsVisability();
    toggleIDFieldVisability();
    toggleAutoDimensionsFieldVisability();
    toggleDimensionsFieldsVisability();
    togglePiPFieldsVisability();
    toggleWithIDProfileSaveButtonVisability();
    updateSaveProfileButtonsText();
    hideConfirmDeleteProfilePrompt();
    setOverlayDisplayPositionGrid();
    setPiPDisplayPositionGrid();
}


function setKeyboardShortcutText() {
    if (isFirefox) {
        let keyboardShortcuts = document.getElementsByClassName('keyboard-shortcut');
        for (let i = 0, max = keyboardShortcuts.length; i < max; i++) {
            keyboardShortcuts[i].innerHTML = `<kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>C</kbd>`;
        }
    }
}


function showProfileUpdateSettings(profileNameText) {
    if (document.getElementById("newProfile")) {
        document.getElementById("newProfile").remove();
    }
    document.getElementsByClassName("profile-settings-wrapper")[0].style.display = "block";
    if (profileNameText) {
        optionsForm.profileName.value = profileNameText;
    }
}


function saveProfile(shouldSaveWithID) {

    hideConfirmDeleteProfilePrompt();

    const profileName = optionsForm.profileName.value.trim();

    if (!profileName) {
        addValidationMessage(optionsForm.profileName, 'error', 'Please enter profile name.');
    } else if (profileName === 'Default') {
        addValidationMessage(optionsForm.profileName, 'error', 'Cannot overwrite Default profile.');
    } else {

        let ytPlaylistID;
        let ytVideoID;
        let ytLiveID;
        let otherVideoURL;
        let otherLiveURL;
        if (shouldSaveWithID) {
            if (optionsForm.overlayVideoType.value === 'yt-playlist') {
                ytPlaylistID = optionsForm.ytPlaylistID.value;
            } else if (optionsForm.overlayVideoType.value === 'yt-video') {
                ytVideoID = optionsForm.ytVideoID.value;
            } else if (optionsForm.overlayVideoType.value === 'yt-live') {
                ytLiveID = optionsForm.ytLiveID.value;
            } else if (optionsForm.overlayVideoType.value === 'other-video') {
                otherVideoURL = optionsForm.otherVideoURL.value;
            } else if (optionsForm.overlayVideoType.value === 'other-live') {
                otherLiveURL = optionsForm.otherLiveURL.value;
            }
        } //else keep all as null

        profiles[profileName] = {
            overlayVideoType: optionsForm.overlayVideoType.value,
            ytPlaylistID: ytPlaylistID,
            ytVideoID: ytVideoID,
            ytLiveID: ytLiveID,
            otherVideoURL: otherVideoURL,
            otherLiveURL: otherLiveURL,
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
            audioLevelThreshold: optionsForm.audioLevelThreshold.value,
            shouldOverlayVideoSizeAndLocationAutoSet: optionsForm.shouldOverlayVideoSizeAndLocationAutoSet.checked,
            shouldShuffleYTPlaylist: optionsForm.shouldShuffleYTPlaylist.checked
        };

        chrome.storage.sync.set({ profiles }, () => {
            if (chrome.runtime.lastError) {
                addValidationMessage(optionsForm.profileName, 'error', 'Sorry, profile not saved. Out of space. Please delete some profiles and try again.');
                return;
            }

            reloadProfileNames(profileName);
            updateSaveProfileButtonsText();
            addValidationMessage(optionsForm.profileName, 'success', 'Profile saved. Click "Save & Apply" button when ready.');
        });

    }
    
}


function applyProfile() {

    let selectedProfile = optionsForm.profileSelect.value;

    if (selectedProfile) {
        if (profiles[selectedProfile]) {

            if (typeof profiles[selectedProfile].overlayVideoType !== 'undefined') { optionsForm.overlayVideoType.value = profiles[selectedProfile].overlayVideoType; }
            if (typeof profiles[selectedProfile].ytPlaylistID !== 'undefined') { optionsForm.ytPlaylistID.value = profiles[selectedProfile].ytPlaylistID; }
            if (typeof profiles[selectedProfile].ytVideoID !== 'undefined') { optionsForm.ytVideoID.value = profiles[selectedProfile].ytVideoID; }
            if (typeof profiles[selectedProfile].ytLiveID !== 'undefined') { optionsForm.ytLiveID.value = profiles[selectedProfile].ytLiveID; }
            if (typeof profiles[selectedProfile].otherVideoURL !== 'undefined') { optionsForm.otherVideoURL.value = profiles[selectedProfile].otherVideoURL; }
            if (typeof profiles[selectedProfile].otherLiveURL !== 'undefined') { optionsForm.otherLiveURL.value = profiles[selectedProfile].otherLiveURL; }
            if (typeof profiles[selectedProfile].overlayVideoLocationHorizontal !== 'undefined') { optionsForm.overlayVideoLocationHorizontal.value = profiles[selectedProfile].overlayVideoLocationHorizontal; }
            if (typeof profiles[selectedProfile].overlayVideoLocationVertical !== 'undefined') { optionsForm.overlayVideoLocationVertical.value = profiles[selectedProfile].overlayVideoLocationVertical; }
            if (typeof profiles[selectedProfile].mainVideoFade !== 'undefined') { optionsForm.mainVideoFade.value = profiles[selectedProfile].mainVideoFade; }
            if (typeof profiles[selectedProfile].videoOverlayWidth !== 'undefined') { optionsForm.videoOverlayWidth.value = profiles[selectedProfile].videoOverlayWidth; }
            if (typeof profiles[selectedProfile].videoOverlayHeight !== 'undefined') { optionsForm.videoOverlayHeight.value = profiles[selectedProfile].videoOverlayHeight; }
            if (typeof profiles[selectedProfile].mainVideoVolumeDuringCommercials !== 'undefined') { optionsForm.mainVideoVolumeDuringCommercials.value = profiles[selectedProfile].mainVideoVolumeDuringCommercials; }
            if (typeof profiles[selectedProfile].mainVideoVolumeDuringNonCommercials !== 'undefined') { optionsForm.mainVideoVolumeDuringNonCommercials.value = profiles[selectedProfile].mainVideoVolumeDuringNonCommercials; }
            if (typeof profiles[selectedProfile].shouldHideYTBackground !== 'undefined') { optionsForm.shouldHideYTBackground.checked = profiles[selectedProfile].shouldHideYTBackground; }
            //note: don't need special commercialDetectionMode adjustment because nobody could have created a profile before the 2.0 update
            if (typeof profiles[selectedProfile].commercialDetectionMode !== 'undefined') { optionsForm.commercialDetectionMode.value = profiles[selectedProfile].commercialDetectionMode; }
            if (typeof profiles[selectedProfile].mismatchCountThreshold !== 'undefined') { optionsForm.mismatchCountThreshold.value = profiles[selectedProfile].mismatchCountThreshold; }
            if (typeof profiles[selectedProfile].matchCountThreshold !== 'undefined') { optionsForm.matchCountThreshold.value = profiles[selectedProfile].matchCountThreshold; }
            if (typeof profiles[selectedProfile].colorDifferenceMatchingThreshold !== 'undefined') { optionsForm.colorDifferenceMatchingThreshold.value = profiles[selectedProfile].colorDifferenceMatchingThreshold; }
            if (typeof profiles[selectedProfile].manualOverrideCooldown !== 'undefined') { optionsForm.manualOverrideCooldown.value = profiles[selectedProfile].manualOverrideCooldown; }
            if (typeof profiles[selectedProfile].isDebugMode !== 'undefined') { optionsForm.isDebugMode.checked = profiles[selectedProfile].isDebugMode; }
            if (typeof profiles[selectedProfile].isPiPMode !== 'undefined') { optionsForm.isPiPMode.checked = profiles[selectedProfile].isPiPMode; }
            if (typeof profiles[selectedProfile].pipLocationHorizontal !== 'undefined') { optionsForm.pipLocationHorizontal.value = profiles[selectedProfile].pipLocationHorizontal; }
            if (typeof profiles[selectedProfile].pipLocationVertical !== 'undefined') { optionsForm.pipLocationVertical.value = profiles[selectedProfile].pipLocationVertical; }
            if (typeof profiles[selectedProfile].pipHeight !== 'undefined') { optionsForm.pipHeight.value = profiles[selectedProfile].pipHeight; }
            if (typeof profiles[selectedProfile].pipWidth !== 'undefined') { optionsForm.pipWidth.value = profiles[selectedProfile].pipWidth; }
            if (typeof profiles[selectedProfile].shouldClickNextOnPlaySpotify !== 'undefined') { optionsForm.shouldClickNextOnPlaySpotify.checked = profiles[selectedProfile].shouldClickNextOnPlaySpotify; }
            if (typeof profiles[selectedProfile].isOverlayVideoZoomMode !== 'undefined') { optionsForm.isOverlayVideoZoomMode.checked = profiles[selectedProfile].isOverlayVideoZoomMode; }
            if (typeof profiles[selectedProfile].isOtherSiteTroubleshootMode !== 'undefined') { optionsForm.isOtherSiteTroubleshootMode.checked = profiles[selectedProfile].isOtherSiteTroubleshootMode; }
            if (typeof profiles[selectedProfile].audioLevelThreshold !== 'undefined') { optionsForm.audioLevelThreshold.value = profiles[selectedProfile].audioLevelThreshold; }
            if (typeof profiles[selectedProfile].shouldOverlayVideoSizeAndLocationAutoSet !== 'undefined') { optionsForm.shouldOverlayVideoSizeAndLocationAutoSet.checked = profiles[selectedProfile].shouldOverlayVideoSizeAndLocationAutoSet; }
            if (typeof profiles[selectedProfile].shouldShuffleYTPlaylist !== 'undefined') { optionsForm.shouldShuffleYTPlaylist.checked = profiles[selectedProfile].shouldShuffleYTPlaylist; }

            showProfileUpdateSettings(selectedProfile);
            runAllToggles();
            addValidationMessage(optionsForm.profileName, 'success', 'Profile loaded. Click "Save & Apply" button when ready.');

        }
    }

}


function deleteProfile() {

    let profileToDelete = optionsForm.profileSelect.value;

    if (profileToDelete) {

        delete profiles[profileToDelete];

        chrome.storage.sync.set({ profiles }, () => {
            hideConfirmDeleteProfilePrompt();
            optionsForm.profileName.value = '';
            reloadProfileNames(false);
            addValidationMessage(optionsForm.profileSelect, 'success', `Profile ${profileToDelete} deleted.`);
        });

    }

}


function reloadProfileNames(profileToSelect) {
    chrome.storage.sync.get("profiles", (data) => {

        //remove options except for top select option
        while (optionsForm.profileSelect.children.length > 1) {
            optionsForm.profileSelect.removeChild(optionsForm.profileSelect.lastChild);
        }

        profiles = data.profiles || {};
        for (const name in profiles) {
            const option = document.createElement("option");
            option.value = name;
            option.textContent = name;
            profileSelect.appendChild(option);
        }

        if (profileToSelect) {
            optionsForm.profileSelect.value = profileToSelect;
        }

    });
}


function addValidationMessage(element, type, message) {

    //TODO: allow more than one validation message show at a time
    clearAllValidationMessages();

    let validationMessage = document.createElement('div');
    validationMessage.className = `${type}-message`;
    validationMessage.textContent = message;
    element.after(validationMessage);

    element.addEventListener("click", removeValidationMessage);
    function removeValidationMessage() {
        element.removeEventListener("click", removeValidationMessage);
        validationMessage.remove();
    }

}


function clearAllValidationMessages() {

    if (document.getElementsByClassName('error-message')[0]) {

        let elements = document.getElementsByClassName('error-message');
        let element;

        while (element = elements[0]) {
            element.parentNode.removeChild(element);
        }

    }

    if (document.getElementsByClassName('success-message')[0]) {

        let elements = document.getElementsByClassName('success-message');
        let element;

        while (element = elements[0]) {
            element.parentNode.removeChild(element);
        }

    }

}
