
var playButton;
var nextButton;
var nowPlayingWidget;
var hasFirstSongPlayed = false;
var isInitialSetupComplete = false;


//run initialSetup() as soon as DOM is loaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initialSetup);
} else {
    initialSetup();
}


chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
    if (message.action == 'pause_spotify') {
        pause();
    } else if (message.action == 'play_spotify') {
        play();
    } else if (message.action == 'next_spotify') {
        if (hasFirstSongPlayed) {
            next();
        } else {
            //play first song before skipping it
            play();
            hasFirstSongPlayed = true;
        }
        
    }
});


function pause() {

    if (playButton != null) {

        if (playButton.ariaLabel == 'Pause') {

            playButton.click();

        }

    } //TODO: add else here to close spotify and then show an error on the main tab saying there was and issue and to refresh

}


function play() {

    if (playButton != null) {

        if (playButton.ariaLabel == 'Play') {

            playButton.click();

        }

        shipNowPlaying();

    } //TODO: add else here to close spotify and then show an error on the main tab saying there was and issue and to refresh

}


function next() {

    if (nextButton != null) {

        //note: only need to hit next button because as of 10/29/24 spotify automatically starts playing after next button is clicked
        nextButton.click();

        //note: don't need to run shipNowPlaying() because nowPlayingWidgetObserver() will detect that the song changed and send the song/artist

    } else if (playButton != null) {

        //just play if nextButton is broken. would rather have the extension be half broken instead of full broken
        if (playButton.ariaLabel == 'Play') {

            playButton.click();

        }

        shipNowPlaying();

    } //TODO: add else here to close spotify and then show an error on the main tab saying there was and issue and to refresh

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


function initialSetup() {

    setTimeout(() => {

        var link = document.createElement('link');
        link.href = 'https://fonts.googleapis.com/css2?family=Montserrat:ital,wght@0,700;1,700&display=swap';
        link.rel = 'stylesheet';
        document.head.appendChild(link);

        var banner = document.createElement('div');
        banner.id = 'custom-banner';

        banner.innerText = 'Message from Live Commercial Blocker: Choose a playlist and hit play.';

        banner.style.position = 'fixed';
        banner.style.top = '0';
        banner.style.left = '0';
        banner.style.width = '100%';
        banner.style.backgroundColor = 'rgb(240, 238, 236)';
        banner.style.color = '#12384d';
        banner.style.textAlign = 'center';
        banner.style.padding = '5px';
        banner.style.zIndex = '1000';
        banner.style.fontSize = '20px';
        banner.style.fontFamily = '"Montserrat", sans-serif';

        document.body.style.marginTop = '35px';

        document.body.appendChild(banner);

        waitForElement('[data-testid="control-button-playpause"]').then(() => {

            setTimeout(() => {

                playButton = document.querySelector('[data-testid="control-button-playpause"]');
                nextButton = document.querySelector('[data-testid="control-button-skip-forward"]');

                waitForElement('[aria-label="Pause"][data-testid="control-button-playpause"]:not([disabled])').then(() => {

                    //wait a split sec so things feel smoother
                    setTimeout(() => {

                        if (document.querySelector('[data-testid="now-playing-widget"]')) {

                            nowPlayingWidget = document.querySelector('[data-testid="now-playing-widget"]');
                            nowPlayingWidgetObserver(nowPlayingWidget);

                        }

                        chrome.runtime.sendMessage({ action: "glimpse_main_tab" });
                        banner.innerText = 'Tab opened for use of the Live Commercial Blocker. Do not close until you are done using Live Commercial Blocker extension.';
                        isInitialSetupComplete = true;

                        setTimeout(() => {

                            pause();

                        }, 500);

                    }, 500);

                });

            }, 1000);

        });

        //check if not logged in
        waitForElement('[data-testid="login-button"]').then(() => {
            //add additional check to lower chance that this is accidentally triggered if spotify makes an update in the future
            waitForElement('[data-testid="signup-button"]').then(() => {
                if (!isInitialSetupComplete) {
                    banner.innerText = 'Message from Live Commercial Blocker: Error Occured. You must be logged into Spotify before initiating extension. Please login to Spotify, go back to tab with stream, refresh tab, and then re-initiate extension.';
                }
            });
        });

    }, 500);

}