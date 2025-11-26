

const urlParameters = new URLSearchParams(window.location.search);
const purpose = urlParameters.get('purpose');
const videoURL = urlParameters.get('video-url');


if (purpose === 'opposite-mode-instructions') {

    let regularModeElms = document.getElementById('regular-mode');
    regularModeElms.style.display = 'none';
    let oppositeModeElms = document.getElementById('opposite-mode');
    oppositeModeElms.style.display = 'block';

} else if (purpose === 'advanced-logo-mode-instructions') {

    let regularModeElms = document.getElementById('regular-mode');
    regularModeElms.style.display = 'none';
    let advancedLogoModeElms = document.getElementById('advanced-logo-mode');
    advancedLogoModeElms.style.display = 'block';

} else if (purpose === 'overlay-video-container') {

    document.getElementById('all-content').style.display = 'none';
    document.getElementsByTagName('body')[0].style.backgroundColor = "black";
    document.getElementsByTagName('html')[0].style.cursor = 'default';

    video = document.createElement("video");
    video.controls = true;
    video.autoplay = true;
    video.muted = false;
    video.src = videoURL;
    video.className = "overlay-video";
    document.body.appendChild(video);

    //wait a little bit for the video to load //TODO: get indicator of when completely loaded
    setTimeout(() => {
        let script = document.createElement('script');
        script.src = "/scripts/overlay.js";
        document.body.appendChild(script);
    }, 2000);

} else if (purpose === 'rtc') {

    setTimeout(() => {
        let script = document.createElement('script');
        script.src = "/scripts/rtc.js";
        document.body.appendChild(script);
    }, 500);

}//else regular pixel mode instructions
