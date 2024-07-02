
var playButton;
var nowPlayingWidget;


chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
    if (message.action == 'initial_play_spotify') {

        initialPlay();

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', addBanner);
        } else {
            addBanner();
        }

    } else if (message.action == 'pause_spotify') {

        pause();

    } else if (message.action == 'play_spotify') {

        play();

    }
});


function initialPlay() {
    //TODO: add some not logged in check

    //TODO: Add timeout on this?
    waitForElement('[data-testid="control-button-playpause"]').then(() => {

        //TODO: see if I can do another check here besides waiting a sec
        setTimeout(() => {

            playButton = document.querySelector('[data-testid="control-button-playpause"]');

            if (document.querySelector('[data-testid="now-playing-widget"]')) {

                nowPlayingWidget = document.querySelector('[data-testid="now-playing-widget"]');
                nowPlayingWidgetObserver(nowPlayingWidget);

            }

            if (document.getElementById('device-picker-icon-button')) {

                //check to see if playing somewhere else
                //TODO: remove check to see if playing somewhere else and instead figure out how to get to play in new tab without user interacting with tab
                if (document.getElementById('device-picker-icon-button').classList.contains('control-button--active')) {

                    play();

                } else {

                    requestUserPlay();

                }

            } else {

                requestUserPlay();

            }

            //TODO: add check to see if nothing is queued up
            ////check to see if main play button is disabled, meaning they have nothing queued up to play
            //if (playButton.disabled) {
            //    console.log('play button was DISABLED');
            //    //so just play very first play button of some other playlist that we see, should be the playlist they listened too most recently
            //    document.querySelector('[data-testid="play-button"]').click();
            //    //wait a sec and make sure playlist selected is playing
            //    setTimeout(() => {
            //        play();
            //    }, 1000);
            //}
            
        }, 1500);

    });

}


function pause() {

    if (playButton != null) {

        if (playButton.ariaLabel == 'Pause') {

            playButton.click();

        }

    }
    
}


function play() {

    if (playButton != null) {

        if (playButton.ariaLabel == 'Play') {

            playButton.click();

        }

        shipNowPlaying();

    }

}


function waitForElement(target) {

    return new Promise(resolve => {

        if (document.querySelector(target)) {
            return resolve(document.querySelector(target));
        }

        const observer = new MutationObserver(mutations => {

            if (document.querySelector(target)) {
                observer.disconnect();
                resolve(document.querySelector(target));
            }

        });

        observer.observe(document.body, {
            childList: true,
            subtree: true
        });

    });

}


function requestUserPlay() {

    chrome.runtime.sendMessage({
        action: "glimpse_spotify"
    });

    alert(
        `Note: You need to now manually play spotify from this tab.
You will not need to return to this tab again as the YTOC extension will automatically pause and play spotify from this point forward after you manually hit play.`
    );

    //wait for user to click play and then send them back to main tab
    waitForElement('[aria-label="Pause"][data-testid="control-button-playpause"]').then(() => {

        chrome.runtime.sendMessage({ action: "glimpse_main_tab" });
        shipNowPlaying();

    });
    
    //TODO: add banner for this message instead of alert

}


//checks to see when song and artist now playing changes
function nowPlayingWidgetObserver(nowPlayingWidget) {

    const observer = new MutationObserver((mutationsList) => {
        for (let mutation of mutationsList) {
            if (mutation.type === 'attributes' && mutation.attributeName === 'aria-label') {
                shipNowPlaying();
            }
        }
    });

    const config = { attributes: true, attributeFilter: ['aria-label'] };

    observer.observe(nowPlayingWidget, config);

}


function shipNowPlaying() {

    let text = nowPlayingWidget.ariaLabel ?? 'Playing Spotify';

    chrome.runtime.sendMessage({
        action: "background_update_logo_text",
        text: text
    });

}


function addBanner() {

    var link = document.createElement('link');
    link.href = 'https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap';
    link.rel = 'stylesheet';
    document.head.appendChild(link);

    var banner = document.createElement('div');
    banner.id = 'custom-banner';

    banner.innerText = 'Tab opened for use of the YTOC extension. Do not close until you are done using YTOC extension.';

    banner.style.position = 'fixed';
    banner.style.top = '0';
    banner.style.left = '0';
    banner.style.width = '100%';
    banner.style.backgroundColor = 'black';
    banner.style.color = 'red';
    banner.style.textAlign = 'center';
    banner.style.padding = '5px';
    banner.style.zIndex = '1000';
    banner.style.fontSize = '20px';
    banner.style.fontFamily = 'Roboto, Arial, sans-serif';
    banner.style.boxShadow = '0 2px 4px rgba(0,0,0,0.2)';

    document.body.style.marginTop = '35px';

    document.body.appendChild(banner);

}