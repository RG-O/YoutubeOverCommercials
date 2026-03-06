
var isFirefox = false; //********************

var isDebugMode = true;
var getStartedButton;
var demoVideo;
var doubleClapIndicator;
var waveCtx;
var attackCtx;
var hfCtx;
var clapCtx;
const CLAP_DEBUG_GRAPH_HISTORY = 120;
const rmsHistory = [];
const attackHistory = [];
const hfHistory = [];
const CLAP_HISTORY_MS = 2000;
var clapIndicatorResetTimer = null;
var doubleClapDetectorIFrameContainer;
var clapPort;


document.addEventListener('DOMContentLoaded', function () {
    getStartedButton = document.getElementById("get-started-button");
    getStartedButton.onclick = function () {
        prepFoClapMonitor();
    }

    if (isFirefox) {
        firefoxSpecificUpdates();
    }

    demoVideo = document.getElementById("demo-vido");

    checkMicAccess();
}, false);


function firefoxSpecificUpdates() {
    let keyboardShortcuts = document.getElementsByClassName('keyboard-shortcut');
    for (let i = 0, max = keyboardShortcuts.length; i < max; i++) {
        keyboardShortcuts[i].innerHTML = `<kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>C</kbd>`;
    }

    document.getElementById('chrome-mic-selection-tip').style.display = 'none';
}


function demoVideoPlayPause() {
    if (demoVideo.paused || demoVideo.ended) {
        demoVideo.play();
    } else {
        demoVideo.pause();
    }
}


function checkMicAccess() {
    navigator.permissions.query({ name: "microphone" }).then((result) => {
        if (result.state === "granted") {
            prepFoClapMonitor();
        }
    });
}


//stop listing for claps when user leaves configuration page to avoid ever having two clap detectors running at the same time
function toggleLeavePage() {
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'hidden') {
            closeDoubleClapDetectorIFrame();
            toggleReenterPage();
        }
    });
}


//reload page upon reentry to open clap detector again
function toggleReenterPage() {
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') {
            location.reload();
        }
    });
}


//TODO: most of this code is duplicated from content.js, can these use shared code?
function prepFoClapMonitor() {
    chrome.storage.sync.get(['clapSensitivity'], (result) => {
        getStartedButton.disabled = true;
        document.getElementById('loading-spinner').style.display = 'block';

        let clapSensitivity = result.clapSensitivity ?? 30;
        form.clapSensitivityRange.value = clapSensitivity;
        form.clapSensitivity.value = clapSensitivity;
        addDoubleClapDetectorIFrame(clapSensitivity);
        launchClapPort();
    });
}


function addDoubleClapDetectorIFrame(clapSensitivity) {
    let insertLocation = document.getElementsByTagName('body')[0];

    doubleClapDetectorIFrameContainer = document.createElement('div');
    doubleClapDetectorIFrameContainer.style.visibility = "hidden";
    insertLocation.appendChild(doubleClapDetectorIFrameContainer);

    let iFrame = document.createElement('iframe');
    //iFrame.style.visibility = "hidden";
    iFrame.style.display = "none";
    let iFrameSource = chrome.runtime.getURL('pixel-select-instructions.html?purpose=listen-double-clap-configure&debug=true&sensitivity=') + clapSensitivity;
    iFrame.src = iFrameSource;
    iFrame.allow = "microphone;";

    doubleClapDetectorIFrameContainer.appendChild(iFrame);
}


function closeDoubleClapDetectorIFrame() {
    //TODO: better way to do this than removing it?
    doubleClapDetectorIFrameContainer.remove();
}


//TODO: make connecting more like it is in content.js
function launchClapPort() {
    //give time for iframe and script to load
    setTimeout(() => {
        //TODO: can I estiblish the port from the other file since I always know that comes second?
        clapPort = chrome.runtime.connect({ name: "clap-detector" });

        clapPort.postMessage({ action: "connected" });

        clapPort.onMessage.addListener(message => {
            if (message.action === "update-clap-indicator") {
                setClapIndicator(message.text, message.debugText, message.resetAfterMs);
            } else if (message.action === "manual-commercial-mode-toggle") {
                demoVideoPlayPause();
            } else if (message.action === "update-clap-debug-metrics") {
                updateClapDebugOverlay(message.clapDebugOverlayData);
            } else if (message.action === "mic-permission-success") {
                toggleLeavePage();
                initiateClapIndicator();
                micReadyPageReconfiguration(message.inUseMicName);
            } else if (message.action === "mic-permission-error") {
                closeDoubleClapDetectorIFrame();
                micPermissionErrorPageReconfiguration();
            }
        });
    }, 1000);
}


function micReadyPageReconfiguration(inUseMicName) {
    document.getElementById('loading-spinner').style.display = 'none';
    getStartedButton.disabled = false;
    getStartedButton.style.display = 'none';
    document.getElementById('grant-access-message').style.display = 'none';
    document.getElementById('mic-access-error').style.display = 'none';

    document.getElementById('show-on-mic-connected').style.display = 'block';

    document.getElementById('microphone-selected').innerText = '\uD83C\uDFA4 ' + inUseMicName;
}


function micPermissionErrorPageReconfiguration() {
    document.getElementById('loading-spinner').style.display = 'none';

    getStartedButton.disabled = false;
    document.getElementById('mic-access-error').style.display = 'block';
}


form.clapSensitivityRange.addEventListener('input', function (e) {
    form.clapSensitivity.value = form.clapSensitivityRange.value;
});
form.clapSensitivity.addEventListener('input', function (e) {
    form.clapSensitivityRange.value = form.clapSensitivity.value;
});

form.clapSensitivityRange.addEventListener('input', (e) => {
    showHideSensitivityWarnings();
});
form.clapSensitivity.addEventListener('input', (e) => {
    showHideSensitivityWarnings();
});


function showHideSensitivityWarnings() {
    clapPort.postMessage({ action: "update-sensitivity", clapSensitivity: form.clapSensitivity.value });
    if (form.clapSensitivity.value > 50 && form.clapSensitivity.value < 100) {
        document.getElementById('sensitivity-warning').style.display = 'block';
        document.getElementById('background-noise-warning-extreme').style.display = 'none';
    } else if (form.clapSensitivity.value == 100) {
        document.getElementById('sensitivity-warning').style.display = 'none';
        document.getElementById('background-noise-warning-extreme').style.display = 'block';
    } else {
        document.getElementById('sensitivity-warning').style.display = 'none';
        document.getElementById('background-noise-warning-extreme').style.display = 'none';
    }
}


document.getElementById("save-button").onclick = function () {
    chrome.storage.sync.set({ clapSensitivity: form.clapSensitivity.value }, function () {
        document.getElementById('show-on-mic-connected').style.display = 'none';
        if (!demoVideo.paused) {
            demoVideo.pause();
        }
        closeDoubleClapDetectorIFrame();

        document.getElementById('show-on-save').style.display = 'block';
    });
}


function updateClapDebugOverlay(clapDebugOverlayData) {
    rmsHistory.push(clapDebugOverlayData.micRMS);
    attackHistory.push(clapDebugOverlayData.micAttack);
    hfHistory.push(clapDebugOverlayData.hf);
    if (rmsHistory.length > CLAP_DEBUG_GRAPH_HISTORY) rmsHistory.shift();
    if (attackHistory.length > CLAP_DEBUG_GRAPH_HISTORY) attackHistory.shift();
    if (hfHistory.length > CLAP_DEBUG_GRAPH_HISTORY) hfHistory.shift();

    //rms graph
    waveCtx.clearRect(0, 0, 280, 80);
    waveCtx.strokeStyle = '#0f0';
    waveCtx.beginPath();
    rmsHistory.forEach((v, i) => {
        const x = (i / CLAP_DEBUG_GRAPH_HISTORY) * 280;
        const y = 80 - Math.min(v / (clapDebugOverlayData.rmsThreshold), 2) * 40;
        i ? waveCtx.lineTo(x, y) : waveCtx.moveTo(x, y);
    });
    waveCtx.stroke();
    waveCtx.strokeStyle = '#ff0';
    const noiseY = 80 - Math.min(clapDebugOverlayData.micNoise / clapDebugOverlayData.rmsThreshold, 2) * 40;
    waveCtx.beginPath();
    waveCtx.moveTo(0, noiseY);
    waveCtx.lineTo(280, noiseY);
    waveCtx.stroke();
    waveCtx.strokeStyle = '#f00';
    waveCtx.beginPath();
    waveCtx.moveTo(0, 80 - 40);
    waveCtx.lineTo(280, 80 - 40);
    waveCtx.stroke();

    //attack graph
    //current attack line
    attackCtx.clearRect(0, 0, 280, 50);
    attackCtx.strokeStyle = '#0ff';
    attackCtx.beginPath();
    attackHistory.forEach((v, i) => {
        const x = (i / CLAP_DEBUG_GRAPH_HISTORY) * 280;
        const y = 50 - Math.min(v / clapDebugOverlayData.attackThreshold, 2) * 25;
        i ? attackCtx.lineTo(x, y) : attackCtx.moveTo(x, y);
    });
    attackCtx.stroke();
    //attack threshold line
    //attackCtx.strokeStyle = '#f00';
    if (clapDebugOverlayData.attackThreshold === clapDebugOverlayData.baseAttackThreshold) {
        attackCtx.strokeStyle = '#ff0000';
        //todo: figure out why newer laptop always here
    } else if (clapDebugOverlayData.attackThreshold === clapDebugOverlayData.minAttackThreshold) {
        attackCtx.strokeStyle = '#4c0000';
    } else {
        attackCtx.strokeStyle = '#990000';
    }
    attackCtx.beginPath();
    attackCtx.moveTo(0, 50 - 25);
    attackCtx.lineTo(280, 50 - 25);
    attackCtx.stroke();

    //HF graph
    hfCtx.clearRect(0, 0, 280, 50);
    hfCtx.strokeStyle = '#0f0';
    hfCtx.beginPath();
    hfHistory.forEach((v, i) => {
        const x = (i / CLAP_DEBUG_GRAPH_HISTORY) * 280;
        const y = 50 - Math.min(v / clapDebugOverlayData.hfThreshold, 2) * 25;
        i ? hfCtx.lineTo(x, y) : hfCtx.moveTo(x, y);
    });
    hfCtx.stroke();
    hfCtx.strokeStyle = '#f00';
    const hfThreshY = 50 - 25;
    hfCtx.beginPath();
    hfCtx.moveTo(0, hfThreshY);
    hfCtx.lineTo(280, hfThreshY);
    hfCtx.stroke();

    //clap timeline
    clapCtx.clearRect(0, 0, 280, 24);
    clapCtx.font = '16px system-ui, Apple Color Emoji, Segoe UI Emoji';
    clapCtx.textBaseline = 'middle';
    for (let i = clapDebugOverlayData.clapTimeline.length - 1; i >= 0; i--) {
        const age = clapDebugOverlayData.now - clapDebugOverlayData.clapTimeline[i].time;
        if (age > CLAP_HISTORY_MS) {
            clapDebugOverlayData.clapTimeline.splice(i, 1);
            continue;
        }

        const x = 280 - (age / CLAP_HISTORY_MS) * 280;
        clapCtx.fillText('\uD83D\uDC4F', x - 8, 12);
    }

    //debug-high
    rmsVal.textContent = clapDebugOverlayData.micRMS.toFixed(3);
    rmsThreshVal.textContent = (clapDebugOverlayData.rmsThreshold).toFixed(3);
    attackVal.textContent = Math.abs(clapDebugOverlayData.micAttack).toFixed(3);
    attackThreshVal.textContent = clapDebugOverlayData.attackThreshold.toFixed(3);
    hfVal.textContent = clapDebugOverlayData.hf.toFixed(0);
    hfThreshVal.textContent = clapDebugOverlayData.hfThreshold;
}


function setClapIndicator(text, debugText, resetAfterMs = null) {
    if (clapIndicatorResetTimer) {
        clearTimeout(clapIndicatorResetTimer);
        clapIndicatorResetTimer = null;
    }

    if (doubleClapIndicator) {
        let newIndicatorText = text;
        if (isDebugMode) {
            newIndicatorText += ' ' + debugText;
        }

        doubleClapIndicator.textContent = newIndicatorText;
    }

    if (resetAfterMs !== null) {
        clapIndicatorResetTimer = setTimeout(resetClapsIndicator, resetAfterMs);
    }
}


function resetClapsIndicator() {
    if (doubleClapIndicator) {
        //microphone
        //clap
        //clap
        let newIndicatorText = '\uD83C\uDFA4 \uD83D\uDC4F \uD83D\uDC4F';
        if (isDebugMode) {
            newIndicatorText += ' waiting for claps...';
        }

        doubleClapIndicator.textContent = newIndicatorText;
    }
}


function initiateClapIndicator() {
    doubleClapIndicator = document.getElementById('double-clap-indicator');
    resetClapsIndicator();

    if (isDebugMode) {
        let clapDebugOverlay = document.getElementById('clap-debug-graph');

        waveCtx = createCanvas('wave', 280, 80, clapDebugOverlay);
        attackCtx = createCanvas('attack', 280, 50, clapDebugOverlay);
        hfCtx = createCanvas('hf', 280, 50, clapDebugOverlay);
        clapCtx = createCanvas('claps', 280, 24, clapDebugOverlay);

        //debug-high
        let clapDebugOverlayHigh = document.getElementById('clap-debug-values');
        function addIndicatorRow(labelText, spanId) {
            const row = document.createElement('div');
            row.classList = 'clap-debug-values-row';
            const label = document.createTextNode(labelText + ': ');
            const valueSpan = document.createElement('span');
            valueSpan.id = spanId;
            row.appendChild(label);
            row.appendChild(valueSpan);
            return row;
        }
        clapDebugOverlayHigh.appendChild(addIndicatorRow('RMS Threshold', 'rmsThreshVal'));
        clapDebugOverlayHigh.appendChild(addIndicatorRow('RMS', 'rmsVal'));
        clapDebugOverlayHigh.appendChild(addIndicatorRow('Attack Threshold', 'attackThreshVal'));
        clapDebugOverlayHigh.appendChild(addIndicatorRow('Attack', 'attackVal'));
        clapDebugOverlayHigh.appendChild(addIndicatorRow('Power in Target Frequency Range Threshold', 'hfThreshVal'));
        clapDebugOverlayHigh.appendChild(addIndicatorRow('Power in Target Frequency Range', 'hfVal'));
    }
}


function createCanvas(id, width, height, parent) {
    const canvas = document.createElement('canvas');
    canvas.id = id;
    canvas.width = width;
    canvas.height = height;
    parent.appendChild(canvas);
    return canvas.getContext('2d'); // return the context directly
}
