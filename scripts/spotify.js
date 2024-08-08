
var playButton;
var nowPlayingWidget;

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
        link.href = 'https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap';
        link.rel = 'stylesheet';
        document.head.appendChild(link);

        var banner = document.createElement('div');
        banner.id = 'custom-banner';

        banner.innerText = 'Message from YTOC Extension: Choose a playlist and hit play.';

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

        waitForElement('[data-testid="control-button-playpause"]').then(() => {

            setTimeout(() => {

                playButton = document.querySelector('[data-testid="control-button-playpause"]');

                waitForElement('[aria-label="Pause"][data-testid="control-button-playpause"]:not([disabled])').then(() => {

                    //wait a split sec so things feel smoother
                    setTimeout(() => {

                        if (document.querySelector('[data-testid="now-playing-widget"]')) {

                            nowPlayingWidget = document.querySelector('[data-testid="now-playing-widget"]');
                            nowPlayingWidgetObserver(nowPlayingWidget);

                        }

                        chrome.runtime.sendMessage({ action: "glimpse_main_tab" });
                        banner.innerText = 'Tab opened for use of the YTOC extension. Do not close until you are done using YTOC extension.';

                    }, 500);

                });

            }, 1000);

        });

    }, 1000);

}