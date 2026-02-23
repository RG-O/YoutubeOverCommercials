
document.getElementById("get-started-button").onclick = function () {
    addDoubleClapDetectorIFrame();
}

function addDoubleClapDetectorIFrame() {
    let insertLocation = document.getElementsByTagName('body')[0];

    let doubleClapDetectorIFrameContainer = document.createElement('div');
    doubleClapDetectorIFrameContainer.style.visibility = "hidden";
    insertLocation.appendChild(doubleClapDetectorIFrameContainer);

    let iFrame = document.createElement('iframe');
    iFrame.style.visibility = "hidden";
    iFrame.src = chrome.runtime.getURL('pixel-select-instructions.html?purpose=listen-double-clap-configure&debug=true');
    iFrame.allow = "microphone;";

    doubleClapDetectorIFrameContainer.appendChild(iFrame);
}
