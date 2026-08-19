
var isFirefox = false; //********************
var profiles = {};
var gridCells;
var pipGridCells;
var hasPreviouslyInstalledCompanionApp;
var isCompanionAppCallSuccess = true;
var hasGrantedMicAccess = false;
var isLastExtensionInitiatedTabStillOpen;
var hasPreviouslyInstalledPluginTrigger;
var hasPreviouslyInstalledPluginOverlay;
var isPluginTriggerCallSuccess = false;
var isPluginOverlayCallSuccess = false;
var hasAlreadyCalledPluginOverlayManifestViaAPI = false;
var hasAlreadyCalledPluginOverlayManifestViaWS = false;
var hasAlreadyCalledPluginTriggerManifestViaWS = false;
var pluginTriggerManifest;
var pluginOverlayManifest;
var pluginDualManifest;
var pluginTriggerPreferences;
var pluginOverlayPreferences;
var pluginDualPreferences;
var allPluginPreferences;
var hasLoadedDualPluginManifest = false;
var pluginWSScript;

//variables that currently cannot be updated after initiation of the extension. declaring them here to see if user updates them to see if I should tell them to refresh.
var overlayVideoType; //note: this variable can sorta change
var shouldHideYTBackground;
var isOtherSiteTroubleshootMode;
var isOverlayVideoZoomMode;
var commercialDetectionMode;
var shouldShuffleYTPlaylist;
var isDebugMode;
var isDoubleClapMode;
var isPluginOverlayMode;
var isPluginCommercialTriggerMode;

//TODO: I now have such a crazy amount of user set values that are stored/retrieved all over the place, is there a way to create a singular location to manage them?
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
    'profiles',
    'totalCommercialsBlockedSeconds',
    'todayCommercialsBlockedSeconds',
    'firstCommercialTimerDate',
    'lastCommercialTimerDate',
    'hasPreviouslyInstalledCompanionApp',
    'isDoubleClapMode',
    'clapSensitivity',
    'isDoubleClapOnlyReturnMode',
    'isPluginOverlayMode',
    'isPluginCommercialTriggerMode',
    'pluginOverlayFramework',
    'pluginOverlayAPIURL',
    'pluginOverlayWSURL',
    'pluginCommercialTriggerWSURL',
    'hasPreviouslyInstalledPluginTrigger',
    'hasPreviouslyInstalledPluginOverlay',
    'pluginTriggerPreferences',
    'pluginOverlayPreferences',
    'pluginDualPreferences',
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
    commercialDetectionMode = result.commercialDetectionMode ?? 'auto-pixel-normal';
    //adjusting to updated settings for people that have already downloaded the extension (people set to opposite pixel mode will need to reselect in updated settings)
    if (commercialDetectionMode === 'auto') {
        commercialDetectionMode = 'auto-pixel-normal';
    }
    optionsForm.commercialDetectionMode.value = commercialDetectionMode;
    optionsForm.mismatchCountThreshold.value = result.mismatchCountThreshold ?? 8;
    optionsForm.matchCountThreshold.value = result.matchCountThreshold ?? 2;
    optionsForm.colorDifferenceMatchingThreshold.value = result.colorDifferenceMatchingThreshold ?? 16;
    optionsForm.manualOverrideCooldown.value = result.manualOverrideCooldown ?? 45;
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
    optionsForm.isDoubleClapMode.checked = result.isDoubleClapMode ?? false;
    optionsForm.clapSensitivityRange.value = result.clapSensitivity ?? 40;
    optionsForm.clapSensitivity.value = result.clapSensitivity ?? 40;
    optionsForm.isDoubleClapOnlyReturnMode.checked = result.isDoubleClapOnlyReturnMode ?? false;
    optionsForm.isPluginOverlayMode.checked = result.isPluginOverlayMode ?? false;
    optionsForm.isPluginCommercialTriggerMode.checked = result.isPluginCommercialTriggerMode ?? false;
    optionsForm.pluginOverlayFramework.value = result.pluginOverlayFramework ?? 'api';
    optionsForm.pluginOverlayAPIURL.value = result.pluginOverlayAPIURL ?? 'http://localhost:64144';
    optionsForm.pluginOverlayWSURL.value = result.pluginOverlayWSURL ?? 'ws://localhost:64146';
    optionsForm.pluginCommercialTriggerWSURL.value = result.pluginCommercialTriggerWSURL ?? 'ws://localhost:64145';
    //TODO: add default profile here
    //TODO: get url/id to display in dropdown after profile name
    profiles = result.profiles || {};
    for (const name in profiles) {
        const option = document.createElement("option");
        option.value = name;
        option.textContent = name;
        optionsForm.profileSelect.appendChild(option);
    }
    const today = new Date().toDateString();
    const totalCommercialsBlockedSeconds = result.totalCommercialsBlockedSeconds || 0;
    const todayCommercialsBlockedSeconds = result.todayCommercialsBlockedSeconds || 0;
    const firstCommercialTimerDate = result.firstCommercialTimerDate || today;
    const lastCommercialTimerDate = result.lastCommercialTimerDate || today;
    hasPreviouslyInstalledCompanionApp = result.hasPreviouslyInstalledCompanionApp ?? false;
    hasPreviouslyInstalledPluginTrigger = result.hasPreviouslyInstalledPluginTrigger ?? false;
    hasPreviouslyInstalledPluginOverlay = result.hasPreviouslyInstalledPluginOverlay ?? false;
    pluginTriggerPreferences = result.pluginTriggerPreferences ?? {};
    pluginOverlayPreferences = result.pluginOverlayPreferences ?? {};
    pluginDualPreferences = result.pluginDualPreferences ?? {};
    allPluginPreferences = [
        pluginOverlayPreferences,
        pluginTriggerPreferences,
        pluginDualPreferences
    ];

    //setting duplicated fields
    optionsForm.pluginOverlayFrameworkDuplicate.value = optionsForm.pluginOverlayFramework.value;
    optionsForm.pluginOverlayAPIURLDuplicate.value = optionsForm.pluginOverlayAPIURL.value;
    optionsForm.pluginOverlayWSURLDuplicate.value = optionsForm.pluginOverlayWSURL.value;
    optionsForm.pluginCommercialTriggerWSURLDuplicate.value = optionsForm.pluginCommercialTriggerWSURL.value;

    //Allows me to have certain fields on the popup twice. Only one needs to be the real field.
    document.querySelectorAll("[data-sync]").forEach(input => {
        if (input.type === 'radio' || input.type === 'checkbox' || input.type === 'select-one') {
            input.addEventListener("change", dataSync);
        } else {
            input.addEventListener("input", dataSync);
        }
    });

    document.getElementById(optionsForm.commercialDetectionMode.value).style.display = 'block';
    const modeRadios = document.forms["optionsForm"].elements["commercialDetectionMode"];
    for (let i = 0, max = modeRadios.length; i < max; i++) {
        modeRadios[i].addEventListener('change', toggleModeInstructionsVisability);
        modeRadios[i].addEventListener('change', toggleAutoDimensionsFieldVisability);
        modeRadios[i].addEventListener('change', toggleDimensionsFieldsVisability);
        modeRadios[i].addEventListener('change', pingCompanionApp);
        modeRadios[i].addEventListener('change', getPluginTriggerManifest);
        modeRadios[i].addEventListener('change', enableSaveButton);
        modeRadios[i].addEventListener('change', toggleDoubleClapUI);
    }

    document.getElementById(optionsForm.overlayVideoType.value).style.display = 'block';
    const videoTypeRadios = document.forms["optionsForm"].elements["overlayVideoType"];
    for (let i = 0, max = videoTypeRadios.length; i < max; i++) {
        videoTypeRadios[i].addEventListener('change', toggleIDFieldVisability);
        videoTypeRadios[i].addEventListener('change', toggleWithIDProfileSaveButtonVisability);
        videoTypeRadios[i].addEventListener('change', updateSaveProfileButtonsText);
        videoTypeRadios[i].addEventListener('change', getPluginOverlayManifest);
        videoTypeRadios[i].addEventListener('change', enableSaveButton);
    }

    const pluginOverlayFrameworkRadios = document.forms["optionsForm"].elements["pluginOverlayFramework"];
    for (let i = 0, max = pluginOverlayFrameworkRadios.length; i < max; i++) {
        pluginOverlayFrameworkRadios[i].addEventListener('change', updatePluginOverlayFramework);
        pluginOverlayFrameworkRadios[i].addEventListener('change', getPluginOverlayManifest);
    }
    //TODO: is there a prettier way to do this?
    const pluginOverlayFrameworkDuplicateRadios = document.forms["optionsForm"].elements["pluginOverlayFrameworkDuplicate"];
    for (let i = 0, max = pluginOverlayFrameworkDuplicateRadios.length; i < max; i++) {
        //note: remember that change/input event listeners only listen for user actions, not javascript actions
        pluginOverlayFrameworkDuplicateRadios[i].addEventListener('change', updatePluginOverlayFramework);
        pluginOverlayFrameworkDuplicateRadios[i].addEventListener('change', getPluginOverlayManifest);
    }

    setTextFieldsToSelectAll();
    setKeyboardShortcutText();
    grabCommercialTimeBlockedStats(today, totalCommercialsBlockedSeconds, todayCommercialsBlockedSeconds, firstCommercialTimerDate, lastCommercialTimerDate);

    document.getElementById('shouldOverlayVideoSizeAndLocationAutoSet').addEventListener('change', toggleDimensionsFieldsVisability);
    document.getElementById('isPiPMode').addEventListener('change', togglePiPFieldsVisability);
    optionsForm.profileSelect.addEventListener('change', applyProfile);
    optionsForm.isDoubleClapMode.addEventListener('change', toggleDoubleClapUI);
    optionsForm.isPluginOverlayMode.addEventListener('change', getPluginOverlayManifest);
    optionsForm.isPluginCommercialTriggerMode.addEventListener('change', getPluginTriggerManifest);
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
    optionsForm.clapSensitivityRange.addEventListener('input', function (e) {
        setClapSensitivityField();
    });
    optionsForm.clapSensitivity.addEventListener('input', function (e) {
        setClapSensitivityRangeField();
    });
    optionsForm.companionAppPingRetry.addEventListener("click", function (event) {
        event.preventDefault(); //prevent popup from being reloaded
        pingCompanionApp();
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

    //TODO: combine these somehow
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

    document.getElementById('pull-button-pluginCommercialTriggerWSURL').addEventListener('click', async (event) => {
        event.preventDefault();
        refreshPluginTriggerWSManifest();
    });

    document.getElementById('pull-button-pluginOverlayAPIURL').addEventListener('click', async (event) => {
        event.preventDefault();
        refreshPluginOverlayAPIManifest();
    });

    document.getElementById('pull-button-pluginOverlayWSURL').addEventListener('click', async (event) => {
        event.preventDefault();
        refreshPluginOverlayWSManifest();
    });

    document.getElementById('pull-button-pluginCommercialTriggerWSURLDuplicate').addEventListener('click', async (event) => {
        event.preventDefault();
        refreshPluginTriggerWSManifest();
    });

    document.getElementById('pull-button-pluginOverlayAPIURLDuplicate').addEventListener('click', async (event) => {
        event.preventDefault();
        refreshPluginOverlayAPIManifest();
    });

    document.getElementById('pull-button-pluginOverlayWSURLDuplicate').addEventListener('click', async (event) => {
        event.preventDefault();
        refreshPluginOverlayWSManifest();
    });

    //clear cache on buy me a coffee image to show updated supporter count
    document.getElementById('buy-me-coffee').src = `https://img.buymeacoffee.com/button-api/?text=Buy me a coffee&emoji=${today}&slug=ryango&button_colour=FFDD00&font_colour=000000&font_family=Cookie&outline_colour=000000&coffee_colour=ffffff`;

    //check if user granted extension mic access for later double clap mode checks
    navigator.permissions.query({ name: "microphone" }).then((result) => {
        if (result.state === "granted") {
            hasGrantedMicAccess = true;
        }

        //TODO: Do complete overhull of which fields hide/show (or enable/disable) when various commercial detection modes and overlay types are chosen
        runAllToggles();

        //capturing for comparison on save
        overlayVideoType = optionsForm.overlayVideoType.value;
        shouldHideYTBackground = optionsForm.shouldHideYTBackground.checked;
        isOtherSiteTroubleshootMode = optionsForm.isOtherSiteTroubleshootMode.checked;
        isOverlayVideoZoomMode = optionsForm.isOverlayVideoZoomMode.checked;
        //commercialDetectionMode = optionsForm.commercialDetectionMode.value; //declared above
        shouldShuffleYTPlaylist = optionsForm.shouldShuffleYTPlaylist.checked;
        isDebugMode = optionsForm.isDebugMode.checked;
        isDoubleClapMode = optionsForm.isDoubleClapMode.checked;
        isPluginOverlayMode = optionsForm.isPluginOverlayMode.checked;
        isPluginCommercialTriggerMode = optionsForm.isPluginCommercialTriggerMode.checked;
    });

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
            if (otherVideoURLObj.pathname.toLowerCase().endsWith('.mp4') || otherVideoURLObj.pathname.toLowerCase().endsWith('.mkv')) {
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

        //capture plugin preferences
        if (isSetToDualPlugin()) {
            if (pluginDualManifest) {
                pluginDualPreferences = capturePluginPreferences(pluginDualManifest, 'custom-plugin-dual-manifest-container');
            }
        } else {
            let areDualPluginPreferencesUpdated = false;

            if (isAnyPluginOverlayMode() && pluginOverlayManifest) {
                pluginOverlayPreferences = capturePluginPreferences(pluginOverlayManifest, 'custom-plugin-overlay-manifest-container');

                //setting dual plugin settings if the plugin says it is capable in case the plugin expects its settings to be in pluginDualPreferences
                if (optionsForm.pluginOverlayFramework.value === 'ws' && pluginOverlayManifest?.capabilities.includes("trigger")) {
                    pluginDualPreferences = { ...pluginOverlayPreferences };

                    areDualPluginPreferencesUpdated = true;
                }
            }
            
            if (isAnyPluginTriggerMode() && pluginTriggerManifest) {
                pluginTriggerPreferences = capturePluginPreferences(pluginTriggerManifest, 'custom-plugin-trigger-manifest-container');

                //setting dual plugin settings if the plugin says it is capable in case the plugin expects its settings to be in pluginDualPreferences
                if (!areDualPluginPreferencesUpdated && pluginTriggerManifest?.capabilities?.includes("overlay")) {
                    pluginDualPreferences = { ...pluginTriggerPreferences };
                }
            }
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
            shouldShuffleYTPlaylist: optionsForm.shouldShuffleYTPlaylist.checked,
            isDoubleClapMode: optionsForm.isDoubleClapMode.checked,
            clapSensitivity: optionsForm.clapSensitivity.value,
            isDoubleClapOnlyReturnMode: optionsForm.isDoubleClapOnlyReturnMode.checked,
            isPluginOverlayMode: optionsForm.isPluginOverlayMode.checked,
            isPluginCommercialTriggerMode: optionsForm.isPluginCommercialTriggerMode.checked,
            pluginOverlayFramework: optionsForm.pluginOverlayFramework.value,
            pluginOverlayAPIURL: optionsForm.pluginOverlayAPIURL.value,
            pluginOverlayWSURL: optionsForm.pluginOverlayWSURL.value,
            pluginCommercialTriggerWSURL: optionsForm.pluginCommercialTriggerWSURL.value,
            pluginTriggerPreferences: pluginTriggerPreferences,
            pluginOverlayPreferences: pluginOverlayPreferences,
            pluginDualPreferences: pluginDualPreferences,
        }, function () {

            let shouldDirectToMicConfig = false;
            let shouldShowRefreshMessage = false;

            //bring user to clap configuration page if they are trying to use it but haven't set up their mic yet
            if ((optionsForm.commercialDetectionMode.value === 'manual-clap' || optionsForm.isDoubleClapMode.checked) && !hasGrantedMicAccess) {
                shouldDirectToMicConfig = true;
            }

            let isSwitchingToOrFromAudioAudioOnlyOverlay = false;
            if (
                overlayVideoType !== optionsForm.overlayVideoType.value &&
                (
                    overlayVideoType == 'spotify' ||
                    overlayVideoType == 'other-tabs' ||
                    optionsForm.overlayVideoType.value == 'spotify' ||
                    optionsForm.overlayVideoType.value == 'other-tabs'
                )
            ) {
                isSwitchingToOrFromAudioAudioOnlyOverlay = true;
            }

            if (
                isSwitchingToOrFromAudioAudioOnlyOverlay ||
                shouldHideYTBackground !== optionsForm.shouldHideYTBackground.checked ||
                isOtherSiteTroubleshootMode !== optionsForm.isOtherSiteTroubleshootMode.checked ||
                isOverlayVideoZoomMode !== optionsForm.isOverlayVideoZoomMode.checked ||
                commercialDetectionMode !== optionsForm.commercialDetectionMode.value ||
                shouldShuffleYTPlaylist !== optionsForm.shouldShuffleYTPlaylist.checked ||
                isDebugMode !== optionsForm.isDebugMode.checked ||
                isDoubleClapMode !== optionsForm.isDoubleClapMode.checked ||
                isPluginOverlayMode !== optionsForm.isPluginOverlayMode.checked ||
                isPluginCommercialTriggerMode !== optionsForm.isPluginCommercialTriggerMode.checked
            ) {
                shouldShowRefreshMessage = true;
            }

            chrome.runtime.sendMessage({ action: "background_update_preferences" })
                .then((response) => {
                    if (!response.isLastExtensionInitiatedTabStillOpen) {
                        shouldShowRefreshMessage = false;
                    }

                    closePopupOnSave(shouldShowRefreshMessage, shouldDirectToMicConfig);
                })
                .catch((error) => {
                    console.log(error);
                    closePopupOnSave(shouldShowRefreshMessage, shouldDirectToMicConfig);
                });

        });

    } else {
        alert('Field missing. Please input all fields.');
    }

}


function closePopupOnSave(shouldShowRefreshMessage, shouldDirectToMicConfig) {
    if (shouldShowRefreshMessage) {
        alert("One or more settings that you updated will need a page refresh and then a reinitiation of the extension in order to take effect.");
    }

    //bring user to clap configuration page if they are trying to use it but haven't set up their mic yet
    if (shouldDirectToMicConfig) {
        alert("You will now be taken to a special extension page to configure your microphone settings");

        let url = chrome.runtime.getURL('mic-settings-for-double-clap.html?page-open-reason=forced-configuration');
        window.open(url, '_blank');
    }

    //note: order of when the window is closed is important as firefox stops processing anything in popup.js once the popup window is closed
    window.close();
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
    const url = new URL(tab.url);

    if (param) {
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
        if (url.hostname === 'www.youtube.com') {
            alert('Warning: It is highly recommended that you use one of the YouTube options above for YouTube overlays.');
        }

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


function toggleDoubleClapUI() {
    if (optionsForm.commercialDetectionMode.value === 'manual-clap' || optionsForm.isDoubleClapMode.checked) {
        document.getElementsByClassName('clap-sensitivity-wrapper')[0].style.display = 'block';
    } else {
        document.getElementsByClassName('clap-sensitivity-wrapper')[0].style.display = 'none';
    }

    if (optionsForm.commercialDetectionMode.value === 'manual-clap') {
        document.getElementsByClassName('double-clap-only-return-mode-wrapper')[0].style.display = 'none';
    } else {
        document.getElementsByClassName('double-clap-only-return-mode-wrapper')[0].style.display = 'block';
    }

    if (hasGrantedMicAccess) {
        document.getElementById('double-clap-mode-starter-instructions').style.display = 'none';
        document.getElementById('double-clap-mode-returner-instructions').style.display = 'block';
    } else {
        document.getElementById('double-clap-mode-starter-instructions').style.display = 'block';
        document.getElementById('double-clap-mode-returner-instructions').style.display = 'none';
    }
}


function setClapSensitivityField() {
    optionsForm.clapSensitivity.value = optionsForm.clapSensitivityRange.value;
}


function setClapSensitivityRangeField() {
    optionsForm.clapSensitivityRange.value = optionsForm.clapSensitivity.value;
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
    pingCompanionApp();
    enableSaveButton();
    setClapSensitivityRangeField();
    toggleDoubleClapUI();
    updatePluginOverlayFramework();
    getPluginManifests();
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
            shouldShuffleYTPlaylist: optionsForm.shouldShuffleYTPlaylist.checked,
            isDoubleClapMode: optionsForm.isDoubleClapMode.checked,
            clapSensitivity: optionsForm.clapSensitivity.value,
            isDoubleClapOnlyReturnMode: optionsForm.isDoubleClapOnlyReturnMode.checked,
            isPluginOverlayMode: optionsForm.isPluginOverlayMode.checked,
            isPluginCommercialTriggerMode: optionsForm.isPluginCommercialTriggerMode.checked,
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

            //TODO: this could easily be a loop, right?
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
            if (typeof profiles[selectedProfile].isDoubleClapMode !== 'undefined') { optionsForm.isDoubleClapMode.checked = profiles[selectedProfile].isDoubleClapMode; }
            if (typeof profiles[selectedProfile].clapSensitivity !== 'undefined') { optionsForm.clapSensitivity.value = profiles[selectedProfile].clapSensitivity; }
            if (typeof profiles[selectedProfile].isDoubleClapOnlyReturnMode !== 'undefined') { optionsForm.isDoubleClapOnlyReturnMode.checked = profiles[selectedProfile].isDoubleClapOnlyReturnMode; }
            if (typeof profiles[selectedProfile].isPluginOverlayMode !== 'undefined') { optionsForm.isPluginOverlayMode.checked = profiles[selectedProfile].isPluginOverlayMode; }
            if (typeof profiles[selectedProfile].isPluginCommercialTriggerMode !== 'undefined') { optionsForm.isPluginCommercialTriggerMode.checked = profiles[selectedProfile].isPluginCommercialTriggerMode; }

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


function grabCommercialTimeBlockedStats(today, totalCommercialsBlockedSeconds, todayCommercialsBlockedSeconds, firstCommercialTimerDate, lastCommercialTimerDate) {
    let statsElm = document.getElementById('commercial-time-blocked-stats');

    //do not show at all if no stats collected yet
    if (!statsElm || totalCommercialsBlockedSeconds === 0) return;

    const totalHours = totalCommercialsBlockedSeconds / 3600;
    const roundedTotal = Math.ceil(totalHours * 10) / 10;
    statsElm.textContent = `You blocked ${roundedTotal} hours of commercials since ${firstCommercialTimerDate}.`;

    //do not show daily count if no count yet today
    if (lastCommercialTimerDate === today) {
        const dailyMinutes = todayCommercialsBlockedSeconds / 60;
        const roundedDaily = Math.ceil(dailyMinutes * 10) / 10;
        statsElm.textContent += `\n${roundedDaily} minutes of commercials blocked today.`;
    }
}


function pingCompanionApp() {
    if (optionsForm.commercialDetectionMode.value === 'auto-pixel-advanced-logo') {
        isCompanionAppCallSuccess = false;
        document.getElementById('companion-app-loading').style.display = 'block';
        document.getElementById('save-button').disabled = true;
        document.getElementById('companion-app-ping-error').style.display = 'none'; //here for when retriggered from error

        fetch("http://localhost:64143/ping-advanced-logo-analysis")
            .then(response => response.json())
            .then((response) => {
                //successful ping
                displayPingCompanionAppSuccess(response.version);
            })
            .catch(() => {
                //error with ping
                displayPingCompanionAppError();
            });
    }
}


function displayPingCompanionAppSuccess(version) {
    isCompanionAppCallSuccess = true;
    document.getElementById('companion-app-loading').style.display = 'none';
    document.getElementById('companion-app-additional-setup').style.display = 'none';
    document.getElementById('companion-app-ping-error').style.display = 'none';
    //TODO: Add dynamic check to show "(latest)" here
    document.getElementById('companion-app-ping-success').textContent = `Verified Advanced Logo Analyzer companion app version ${version} (latest) is running properly on this machine.`;
    document.getElementById('companion-app-ping-success').style.display = 'block';
    document.getElementById('companion-app-instructions').style.display = 'block';
    enableSaveButton();

    if (!hasPreviouslyInstalledCompanionApp) {
        //setting values to recommended settings for this mode //TODO: better way for UX for this?
        optionsForm.mismatchCountThreshold.value = 10;
        optionsForm.matchCountThreshold.value = 1;

        //knowing for next time if user has previously installed app to give them error instead of only instructions if app not found
        hasPreviouslyInstalledCompanionApp = true;
        chrome.storage.sync.set({ hasPreviouslyInstalledCompanionApp: hasPreviouslyInstalledCompanionApp });
    }
}


function displayPingCompanionAppError() {
    isCompanionAppCallSuccess = false;
    //TODO: maybe let users save with warning instead of blocking them
    document.getElementById('companion-app-loading').style.display = 'none';
    document.getElementById('companion-app-ping-success').style.display = 'none';
    document.getElementById('companion-app-instructions').style.display = 'none';

    if (hasPreviouslyInstalledCompanionApp) {
        document.getElementById('companion-app-ping-error').style.display = 'block';
        document.getElementById('companion-app-additional-setup').style.display = 'none';
    } else {
        document.getElementById('companion-app-ping-error').style.display = 'none';
        document.getElementById('companion-app-additional-setup').style.display = 'block';
    }
}


function getPluginManifests() {
    if (isAnyPluginOverlayMode()) {
        getPluginOverlayManifest();
    }

    if (isAnyPluginTriggerMode()) {
        getPluginTriggerManifest();
    }
}


function getPluginOverlayManifest() {
    if (isAnyPluginOverlayMode()) {
        document.getElementById('save-button').disabled = true;
        displayClass('custom-plugin-overlay-messaging-container');

        if (optionsForm.overlayVideoType.value !== 'custom-plugin-overlay' && optionsForm.isPluginOverlayMode.checked) {
            document.getElementById('custom-plugin-overlay-settings-checkbox-duplicate').style.display = 'block';
        } else {
            document.getElementById('custom-plugin-overlay-settings-checkbox-duplicate').style.display = 'none';
        }

        if (optionsForm.pluginOverlayFramework.value === 'api' && !hasAlreadyCalledPluginOverlayManifestViaAPI) {
            isPluginOverlayCallSuccess = false;

            showPluginOverlayLoading();
            getPluginOverlayManifestViaAPI();
        } else if (optionsForm.pluginOverlayFramework.value === 'ws' && !hasAlreadyCalledPluginOverlayManifestViaWS) {
            isPluginOverlayCallSuccess = false;

            showPluginOverlayLoading();
            getPluginManifestsViaWS();
        } else {
            enableSaveButton();

            if (isPluginOverlayCallSuccess) {
                document.getElementById('custom-plugin-overlay-manifest-container').style.display = 'block';
            }
        }
    } else {
        enableSaveButton();
        hideClass('custom-plugin-overlay-messaging-container');
        document.getElementById('custom-plugin-overlay-settings-checkbox-duplicate').style.display = 'none';
        document.getElementById('custom-plugin-overlay-manifest-container').style.display = 'none';
        document.getElementById('custom-plugin-dual-manifest-container').style.display = 'none';

        if (hasLoadedDualPluginManifest && isPluginTriggerCallSuccess) {
            document.getElementById('custom-plugin-trigger-manifest-container').style.display = 'block';
        }
    }
}


function displayPluginOverlayManifestSuccess(manifest) {
    isPluginOverlayCallSuccess = true;

    hideClass('custom-plugin-overlay-loading');
    hideClass('custom-plugin-overlay-additional-setup');
    hideClass('custom-plugin-overlay-manifest-error');

    displayClass('plugins-section');
    displayClass('custom-plugin-overlay-manifest-success');

    enableSaveButton();

    if (isSetToDualPlugin()) {
        if (!hasLoadedDualPluginManifest) {
            //TODO: move this to chrome.runtime.onMessage.addListener and then I no longer need hasLoadedDualPluginManifest?
            loadDualPluginManifest(manifest);
        }
    } else {
        pluginOverlayManifest = manifest;

        document.getElementById('custom-plugin-dual-manifest-container').style.display = 'none';

        const pluginOverlayManifestContainerElm = document.getElementById('custom-plugin-overlay-manifest-container');
        pluginOverlayManifestContainerElm.style.display = 'block';
        
        //clearing preferences if different plugin used last time.
        let previousPluginOverlayPreferences = getLatestPluginPreferences(pluginOverlayManifest.id);
        displayPluginManifest(pluginOverlayManifestContainerElm, pluginOverlayManifest, previousPluginOverlayPreferences);
    }

    if (!hasPreviouslyInstalledPluginOverlay) {
        //knowing for next time if user has previously installed app to give them error instead of only instructions if app not found
        hasPreviouslyInstalledPluginOverlay = true;
        chrome.storage.sync.set({ hasPreviouslyInstalledPluginOverlay: hasPreviouslyInstalledPluginOverlay });
    }
}


function displayPluginOverlayManifestError() {
    isPluginOverlayCallSuccess = false;

    hideClass('custom-plugin-overlay-loading');
    hideClass('custom-plugin-overlay-manifest-success');
    document.getElementById('custom-plugin-overlay-manifest-container').style.display = 'none';
    document.getElementById('custom-plugin-dual-manifest-container').style.display = 'none';

    if (optionsForm.isPluginOverlayMode.checked) {
        document.getElementById('expand-button').style.color = 'red';
        document.querySelector('label[for="isPluginOverlayMode"]').style.color = 'red';
    }

    if (hasPreviouslyInstalledPluginOverlay) {
        displayClass('custom-plugin-overlay-manifest-error');
        hideClass('custom-plugin-overlay-additional-setup');
    } else {
        hideClass('custom-plugin-overlay-manifest-error');
        displayClass('custom-plugin-overlay-additional-setup');
    }
}


function getPluginTriggerManifest() {
    if (isAnyPluginTriggerMode()) {
        document.getElementById('save-button').disabled = true;
        displayClass('custom-plugin-trigger-messaging-container');

        if (optionsForm.commercialDetectionMode.value !== 'custom-plugin-trigger' && optionsForm.isPluginCommercialTriggerMode.checked) {
            document.getElementById('custom-plugin-trigger-settings-checkbox-duplicate').style.display = 'block';
        } else {
            document.getElementById('custom-plugin-trigger-settings-checkbox-duplicate').style.display = 'none';
        }

        if (!hasAlreadyCalledPluginTriggerManifestViaWS) {
            isPluginTriggerCallSuccess = false;

            showPluginTriggerLoading();
            getPluginManifestsViaWS();
        } else {
            enableSaveButton();

            if (isPluginTriggerCallSuccess) {
                document.getElementById('custom-plugin-trigger-manifest-container').style.display = 'block';
            }
        }
    } else {
        enableSaveButton();
        hideClass('custom-plugin-trigger-messaging-container');
        document.getElementById('custom-plugin-trigger-settings-checkbox-duplicate').style.display = 'none';
        document.getElementById('custom-plugin-trigger-manifest-container').style.display = 'none';
        document.getElementById('custom-plugin-dual-manifest-container').style.display = 'none';

        if (hasLoadedDualPluginManifest && isPluginOverlayCallSuccess) {
            document.getElementById('custom-plugin-overlay-manifest-container').style.display = 'block';
        }
    }
}


function displayPluginTriggerManifestSuccess(manifest) {
    isPluginTriggerCallSuccess = true;

    hideClass('custom-plugin-trigger-loading');
    hideClass('custom-plugin-trigger-additional-setup');
    hideClass('custom-plugin-trigger-manifest-error');

    displayClass('plugins-section');
    displayClass('custom-plugin-trigger-manifest-success');
    displayClass('custom-plugin-trigger-instructions');

    enableSaveButton();

    if (isSetToDualPlugin()) {
        //TODO: move this to chrome.runtime.onMessage.addListener?
        if (!hasLoadedDualPluginManifest) {
            loadDualPluginManifest(manifest);
        }
    } else {
        pluginTriggerManifest = manifest;

        document.getElementById('custom-plugin-dual-manifest-container').style.display = 'none';

        const pluginTriggerManifestContainerElm = document.getElementById('custom-plugin-trigger-manifest-container');
        pluginTriggerManifestContainerElm.style.display = 'block';

        //clearing preferences if different plugin used last time.
        let previousPluginTriggerPreferences = getLatestPluginPreferences(pluginTriggerManifest.id);
        displayPluginManifest(pluginTriggerManifestContainerElm, pluginTriggerManifest, previousPluginTriggerPreferences);
    }

    if (!hasPreviouslyInstalledPluginTrigger) {
        //knowing for next time if user has previously installed app to give them error instead of only instructions if app not found
        hasPreviouslyInstalledPluginTrigger = true;
        chrome.storage.sync.set({ hasPreviouslyInstalledPluginTrigger: hasPreviouslyInstalledPluginTrigger });
    }
}


function displayPluginTriggerManifestError() {
    isPluginTriggerCallSuccess = false;

    hideClass('custom-plugin-trigger-loading');
    hideClass('custom-plugin-trigger-instructions');
    hideClass('custom-plugin-trigger-manifest-success');
    document.getElementById('custom-plugin-trigger-manifest-container').style.display = 'none';
    document.getElementById('custom-plugin-dual-manifest-container').style.display = 'none';

    if (optionsForm.isPluginCommercialTriggerMode.checked) {
        document.getElementById('expand-button').style.color = 'red';
        document.querySelector('label[for="isPluginCommercialTriggerMode"]').style.color = 'red';
    }

    if (hasPreviouslyInstalledPluginTrigger) {
        displayClass('custom-plugin-trigger-manifest-error');
        hideClass('custom-plugin-trigger-additional-setup');
    } else {
        hideClass('custom-plugin-trigger-manifest-error');
        displayClass('custom-plugin-trigger-additional-setup');
    }
}


function showPluginOverlayLoading() {
    displayClass('custom-plugin-overlay-loading');
    hideClass('custom-plugin-overlay-manifest-error');
    hideClass('custom-plugin-overlay-manifest-success');
    hideClass('custom-plugin-overlay-additional-setup');
}


function showPluginTriggerLoading() {
    displayClass('custom-plugin-trigger-loading');
    hideClass('custom-plugin-trigger-manifest-error');
    hideClass('custom-plugin-trigger-manifest-success');
    hideClass('custom-plugin-trigger-instructions');
    hideClass('custom-plugin-trigger-additional-setup');
}


function loadDualPluginManifest(manifest) {
    hasLoadedDualPluginManifest = true;

    //TODO: should I use { ...manifest } when assigning these?
    pluginOverlayManifest = manifest;
    pluginTriggerManifest = manifest;
    pluginDualManifest = manifest;

    const pluginOverlayManifestContainerElm = document.getElementById('custom-plugin-overlay-manifest-container');
    const pluginTriggerManifestContainerElm = document.getElementById('custom-plugin-trigger-manifest-container');
    pluginOverlayManifestContainerElm.style.display = 'none';
    pluginTriggerManifestContainerElm.style.display = 'none';

    const pluginDualManifestContainerElm = document.getElementById('custom-plugin-dual-manifest-container');
    pluginDualManifestContainerElm.style.display = 'block';

    //set most most recent save to this plugin as pluginDualPreferences, it doesn't necessarly had to have been used as a dual plugin last time it was saved
    let previousPluginDualPreferences = getLatestPluginPreferences(pluginDualManifest.id);

    displayPluginManifest(pluginDualManifestContainerElm, pluginDualManifest, previousPluginDualPreferences);
    //adding to all 3 in case user switches off dual
    displayPluginManifest(pluginOverlayManifestContainerElm, pluginOverlayManifest, previousPluginDualPreferences);
    displayPluginManifest(pluginTriggerManifestContainerElm, pluginTriggerManifest, previousPluginDualPreferences);
}


//get most recent save of plugin preferences. doing it this way so user can switch back and forth as using a dual plugin
function getLatestPluginPreferences(id) {
    const result = allPluginPreferences
        .filter(pluginPreferences => pluginPreferences.id === id)
        .reduce((latest, current) => {
            if (!latest || current.lastSavedTimestamp >= latest.lastSavedTimestamp) {
                return current;
            }

            return latest;
        }, null);

    return result ?? {};
}


function isAnyPluginOverlayMode() {
    return !!(optionsForm.overlayVideoType.value === 'custom-plugin-overlay' || optionsForm.isPluginOverlayMode.checked)
}


function isAnyPluginTriggerMode() {
    return !!(optionsForm.commercialDetectionMode.value === 'custom-plugin-trigger' || optionsForm.isPluginCommercialTriggerMode.checked)
}


function isSetToDualPlugin() {
    return !!(
        optionsForm.pluginOverlayFramework.value === 'ws' &&
        optionsForm.pluginOverlayWSURL.value === optionsForm.pluginCommercialTriggerWSURL.value &&
        isAnyPluginOverlayMode() &&
        isAnyPluginTriggerMode()
    )
}


function refreshPluginOverlayAPIManifest() {
    hasAlreadyCalledPluginOverlayManifestViaAPI = false;
    hasLoadedDualPluginManifest = false;
    getPluginOverlayManifest();
}


function refreshPluginOverlayWSManifest() {
    hasAlreadyCalledPluginOverlayManifestViaWS = false;
    hasLoadedDualPluginManifest = false;
    getPluginOverlayManifest();
}


function refreshPluginTriggerWSManifest() {
    hasAlreadyCalledPluginTriggerManifestViaWS = false;
    hasLoadedDualPluginManifest = false;
    getPluginTriggerManifest();
}


function getPluginOverlayManifestViaAPI() {
    hasAlreadyCalledPluginOverlayManifestViaAPI = true;

    fetch(optionsForm.pluginOverlayAPIURL.value + "/plugin-manifest")
        .then(response => response.json())
        .then((response) => {
            if (optionsForm.pluginOverlayFramework.value === 'api') {
                displayPluginOverlayManifestSuccess(response.data);
            }
            
        })
        .catch((error) => {
            console.log(error);
            if (optionsForm.pluginOverlayFramework.value === 'api') {
                displayPluginOverlayManifestError();
            }
        });
}


function getPluginManifestsViaWS() {
    let isPluginOverlayModeTemp = false;
    if (
        isAnyPluginOverlayMode() &&
        optionsForm.pluginOverlayFramework.value === 'ws' &&
        !hasAlreadyCalledPluginOverlayManifestViaWS
    ) {
        isPluginOverlayModeTemp = true;
        hasAlreadyCalledPluginOverlayManifestViaWS = true;
    }

    let isPluginCommercialTriggerModeTemp = false;
    if (
        isAnyPluginTriggerMode() &&
        !hasAlreadyCalledPluginTriggerManifestViaWS
    ) {
        isPluginCommercialTriggerModeTemp = true;
        hasAlreadyCalledPluginTriggerManifestViaWS = true;
    }

    if (isPluginOverlayModeTemp || isPluginCommercialTriggerModeTemp) {
        const payload = {
            type: "plugin_manifest",
            timestamp: Date.now(),
            data: {
                preferences: {
                    isPluginOverlayMode: isPluginOverlayModeTemp,
                    pluginOverlayFramework: 'ws',
                    pluginOverlayWSURL: optionsForm.pluginOverlayWSURL.value,
                    isPluginCommercialTriggerMode: isPluginCommercialTriggerModeTemp, //TODO: add real value here to do them both at the same time if I can?
                    pluginCommercialTriggerFramework: 'ws',
                    pluginCommercialTriggerWSURL: optionsForm.pluginCommercialTriggerWSURL.value, //TODO: add real value here to do them both at the same time if I can?
                },
                utilities: {
                    isFirefox: isFirefox,
                    isFirefoxPopup: isFirefox,
                }
            },
            meta: {
                wsOpenedBy: 'popup',
            },
        };

        if (isFirefox) {
            if (!pluginWSScript) {
                pluginWSScript = document.createElement('script');
                pluginWSScript.src = "/scripts/plugin-ws-client.js";
                //pluginWSScript.type = "module";
                document.body.appendChild(pluginWSScript);
                pluginWSScript.addEventListener('load', function () {
                    ws.initWSPlugins(payload);
                });
            } else {
                ws.initWSPlugins(payload);
            }
        } else {
            chrome.runtime.sendMessage({
                action: "chrome-connect-to-ws-plugins",
                payload: payload,
            });
        }
    }
}


function enableSaveButton() {
    if (
        (optionsForm.commercialDetectionMode.value !== 'auto-pixel-advanced-logo' || isCompanionAppCallSuccess) &&
        ((optionsForm.overlayVideoType.value !== 'custom-plugin-overlay' && !optionsForm.isPluginOverlayMode.checked) || isPluginOverlayCallSuccess) &&
        ((optionsForm.commercialDetectionMode.value !== 'custom-plugin-trigger' && !optionsForm.isPluginCommercialTriggerMode.checked) || isPluginTriggerCallSuccess)
    ) {
        document.getElementById('save-button').disabled = false;
    }

    if (!optionsForm.isPluginOverlayMode.checked || isPluginOverlayCallSuccess) {
        document.querySelector('label[for="isPluginOverlayMode"]').style.removeProperty('color');
    }

    if (!optionsForm.isPluginCommercialTriggerMode.checked || isPluginTriggerCallSuccess) {
        document.querySelector('label[for="isPluginCommercialTriggerMode"]').style.removeProperty('color');
    }

    if (
        (!optionsForm.isPluginOverlayMode.checked || isPluginOverlayCallSuccess) &&
        (!optionsForm.isPluginCommercialTriggerMode.checked || isPluginTriggerCallSuccess)
    ) {
        document.getElementById('expand-button').style.removeProperty('color');
    }
}


function updatePluginOverlayFramework() {
    //resetting when these change
    hasAlreadyCalledPluginOverlayManifestViaAPI = false;
    hasAlreadyCalledPluginOverlayManifestViaWS = false;
    hasLoadedDualPluginManifest = false;

    const apiSelected = document.getElementById("pluginOverlayFramework-api").checked;

    document.getElementById("pluginOverlayAPIURL").disabled = !apiSelected;
    document.getElementById("pull-button-pluginOverlayAPIURL").disabled = !apiSelected;

    document.getElementById("pluginOverlayWSURL").disabled = apiSelected;
    document.getElementById("pull-button-pluginOverlayWSURL").disabled = apiSelected;

    //TODO: is there a prettier way to do this?
    const apiSelectedDuplicate = document.getElementById("pluginOverlayFramework-apiDuplicate").checked;

    document.getElementById("pluginOverlayAPIURLDuplicate").disabled = !apiSelectedDuplicate;
    document.getElementById("pull-button-pluginOverlayAPIURLDuplicate").disabled = !apiSelectedDuplicate;

    document.getElementById("pluginOverlayWSURLDuplicate").disabled = apiSelectedDuplicate;
    document.getElementById("pull-button-pluginOverlayWSURLDuplicate").disabled = apiSelectedDuplicate;
}


function displayPluginManifest(container, manifest, preferences = {}) {
    //TODO: rename various variables
    const savedValues = preferences.preferences ?? {};

    if (manifest.secondaryColor) {
        const { r, g, b } = hexToRgb(manifest.secondaryColor);
        if (!isLightColor(r, g, b)) {
            container.style.color = '#fff' //white
        }
    }
    container.style.backgroundColor = manifest.secondaryColor ?? "#dadcdc"; //greyblue

    const title = container.querySelector("#plugin-title");
    title.textContent = manifest.name;
    title.style.color = manifest.primaryColor ?? "#000"; //black

    const version = container.querySelector("#plugin-version");
    version.textContent = manifest.version;

    const description = container.querySelector("#plugin-description");
    if (manifest.description) {
        description.textContent = manifest.description;
    } else {
        description.remove();
    }

    const settings = container.querySelector("#plugin-settings");
    settings.replaceChildren(settings.firstElementChild); //clearing out settings except for settings header

    if (manifest.preferences) {
        //const settingsHeader = container.querySelector("#plugin-settings-header");
        //settingsHeader.textContent = manifest.name + " Settings:"

        manifest.preferences.forEach(field => {
            const wrapper = document.createElement("div");
            wrapper.className = "general-field";

            const label = document.createElement("label");
            label.textContent = field.label;

            let input;

            switch (field.type) {
                case "text":
                case "number":
                    input = document.createElement("input");
                    input.type = field.type;
                    input.value = savedValues[field.key] ?? field.default ?? "";
                    input.dataset.key = field.key;
                    break;

                case "checkbox":
                    label.htmlFor = field.key;
                    input = document.createElement("input");
                    input.type = "checkbox";
                    input.style.accentColor = manifest.primaryColor ?? "#12384d";
                    input.id = field.key;
                    input.name = field.key;
                    input.checked = savedValues[field.key] ?? field.default ?? false;
                    input.dataset.key = field.key;
                    wrapper.appendChild(input);
                    break;

                case "radio":
                    input = document.createElement("div");
                    const selectedValue = getValidOptionValue(
                        savedValues[field.key],
                        field.options,
                        field.default
                    );
                    field.options.forEach(opt => {
                        const radioWrapper = document.createElement("div");
                        const radio = document.createElement("input");
                        radio.type = "radio";
                        input.style.accentColor = manifest.primaryColor ?? "#12384d";
                        radio.name = field.key;
                        radio.value = opt.value;
                        radio.checked = opt.value === selectedValue;
                        radio.dataset.key = field.key;
                        const radioLabel = document.createElement("label");
                        radioLabel.textContent = opt.label;
                        radioWrapper.appendChild(radio);
                        radioWrapper.appendChild(radioLabel);
                        input.appendChild(radioWrapper);
                    });
                    break;

                case "select":
                    input = document.createElement("select");
                    field.options.forEach(opt => {
                        const option = document.createElement("option");
                        option.value = opt.value;
                        option.textContent = opt.label;
                        input.appendChild(option);
                    });
                    input.value = getValidOptionValue(
                        savedValues[field.key],
                        field.options,
                        field.default
                    );
                    input.dataset.key = field.key;
                    break;

                case "textarea":
                    input = document.createElement("textarea");
                    input.value = savedValues[field.key] ?? field.default ?? "";
                    input.dataset.key = field.key;
                    break;
            }

            wrapper.appendChild(label);
            if (field.description) {
                const description = document.createElement("div");
                description.className = "note";
                description.textContent = field.description;
                wrapper.appendChild(description);
            }
            if (field.type !== "checkbox") {
                wrapper.appendChild(input); //doing this earlier for checkbox
            }
            settings.appendChild(wrapper);
        });
    } else {
        settings.remove();
    }

    if (manifest?.capabilities?.includes("screenshots")) {
        container.querySelector("#plugin-screenshot-disclaimer").style.display = 'block';
    }
}


function capturePluginPreferences(pluginManifest, pluginManifestContainerElmID) {
    const preferences = {};
    const pluginManifestContainerElm = document.getElementById(pluginManifestContainerElmID);

    pluginManifestContainerElm.querySelectorAll("[data-key]").forEach(input => {
        if (input.type === "radio") {
            if (input.checked) {
                preferences[input.dataset.key] = input.value;
            }
        } else if (input.type === "checkbox") {
            preferences[input.dataset.key] = input.checked;
        } else {
            preferences[input.dataset.key] = input.value;
        }
    });

    return {
        id: pluginManifest.id,
        version: pluginManifest.version,
        capabilities: pluginManifest.capabilities,
        lastSavedTimestamp: Date.now(),
        preferences: preferences,
    }
}


function getValidOptionValue(savedValue, options, defaultValue) {
    if (options.some(opt => opt.value === savedValue)) {
        return savedValue;
    }

    if (options.some(opt => opt.value === defaultValue)) {
        return defaultValue;
    }

    return options[0]?.value ?? "";
}


function hexToRgb(hex) {
    hex = hex.replace(/^#/, "");

    if (hex.length === 3) {
        hex = hex.split("").map(c => c + c).join("");
    }

    return {
        r: parseInt(hex.slice(0, 2), 16),
        g: parseInt(hex.slice(2, 4), 16),
        b: parseInt(hex.slice(4, 6), 16)
    };
}


function isLightColor(r, g, b) {
    return (r * 0.299 + g * 0.587 + b * 0.114) > 150
}


function displayClass(className) {
    const elements = document.getElementsByClassName(className);

    for (const element of elements) {
        element.style.display = 'block';
    }
}


function hideClass(className) {
    const elements = document.getElementsByClassName(className);

    for (const element of elements) {
        element.style.display = 'none';
    }
}


function closeChromeOffscreenDoc(pluginCommercialTriggerWSOpenedBy, pluginOverlayWSOpenedBy, dualWSOpenedBy, totalWSConnectionsInQueue) {
    if (!isFirefox) {
        //do not want to close offscreen if it is currently in use by the other plugins //TODO: check if currently in use by mic as well
        if (
            pluginCommercialTriggerWSOpenedBy !== 'content' &&
            pluginOverlayWSOpenedBy !== 'content' &&
            dualWSOpenedBy !== 'content' &&
            totalWSConnectionsInQueue <= 0
        ) {
            chrome.runtime.sendMessage({
                target: "offscreen",
                action: "close"
            });
        }
    }
}


function dataSync(event) {
    const input = event.target;
    const key = input.dataset.sync;

    document.querySelectorAll(`[data-sync="${key}"]`).forEach(other => {
        if (other === input) return;
        if (input.id === other.id) return;

        switch (input.type) {
            case "radio":
                //TODO: clean this up
                if (other.value === input.value) {
                    if (input.checked) {
                        if (!other.checked) {
                            other.checked = true;
                        }
                    } else {
                        if (other.checked) {
                            other.checked = false;
                        }
                    }
                }
                break;

            case "checkbox":
                other.checked = input.checked;
                break;

            default:
                other.value = input.value;
        }
    });
}


chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
    if (message.action == 'forward_message_from_plugin_ws') {
        handlePluginWSMessage(message);
    }
});


function handlePluginWSMessage(message) {
    if (message.sender === "trigger-plugin") {
        if (message.connectionState === "failed") {
            hasAlreadyCalledPluginTriggerManifestViaWS = true;
            displayPluginTriggerManifestError();
            closeChromeOffscreenDoc(message.pluginCommercialTriggerWSOpenedBy, message.pluginOverlayWSOpenedBy, message.dualWSOpenedBy, message.totalWSConnectionsInQueue);
        } else if (message.connectionState === "connected") {
            if (message.payload.type === "plugin_manifest") {
                hasAlreadyCalledPluginTriggerManifestViaWS = true;
                displayPluginTriggerManifestSuccess(message.payload.data);
                closeChromeOffscreenDoc(message.pluginCommercialTriggerWSOpenedBy, message.pluginOverlayWSOpenedBy, message.dualWSOpenedBy, message.totalWSConnectionsInQueue);
            }
        } //else ignore all other connectionStates
    } else if (message.sender === "overlay-plugin") {
        if (message.connectionState === "failed") {
            if (optionsForm.pluginOverlayFramework.value === 'ws') {
                hasAlreadyCalledPluginOverlayManifestViaWS = true;
                displayPluginOverlayManifestError();
            }
            closeChromeOffscreenDoc(message.pluginCommercialTriggerWSOpenedBy, message.pluginOverlayWSOpenedBy, message.dualWSOpenedBy, message.totalWSConnectionsInQueue);
        } else if (message.connectionState === "connected") {
            if (message.payload.type === "plugin_manifest") {
                if (optionsForm.pluginOverlayFramework.value === 'ws') {
                    hasAlreadyCalledPluginOverlayManifestViaWS = true;
                    displayPluginOverlayManifestSuccess(message.payload.data);
                }
                closeChromeOffscreenDoc(message.pluginCommercialTriggerWSOpenedBy, message.pluginOverlayWSOpenedBy, message.dualWSOpenedBy, message.totalWSConnectionsInQueue);
            }
        } //else ignore all other connectionStates
    } else if (message.sender === "dual-plugin") {
        if (message.connectionState === "failed") {
            hasAlreadyCalledPluginTriggerManifestViaWS = true;
            hasAlreadyCalledPluginOverlayManifestViaWS = true;
            displayPluginTriggerManifestError();
            displayPluginOverlayManifestError();
            closeChromeOffscreenDoc(message.pluginCommercialTriggerWSOpenedBy, message.pluginOverlayWSOpenedBy, message.dualWSOpenedBy, message.totalWSConnectionsInQueue);
        } else if (message.connectionState === "connected") {
            if (message.payload.type === "plugin_manifest") {
                hasAlreadyCalledPluginTriggerManifestViaWS = true;
                hasAlreadyCalledPluginOverlayManifestViaWS = true;
                displayPluginTriggerManifestSuccess(message.payload.data);
                displayPluginOverlayManifestSuccess(message.payload.data);
                closeChromeOffscreenDoc(message.pluginCommercialTriggerWSOpenedBy, message.pluginOverlayWSOpenedBy, message.dualWSOpenedBy, message.totalWSConnectionsInQueue);
            }
        } //else ignore all other connectionStates
    }
}
