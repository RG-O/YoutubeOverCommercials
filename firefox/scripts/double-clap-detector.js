
var microphoneContext;
var microphoneAnalyser;
var microphoneAnalyserFrequency;
var microphoneMediaStreamSource;
var tData;
var fData;
var micRMS;
var micNoise = 0;
var lastRMS = 0;
var rmsThreshold;
var micAttack;
var attackThreshold;
const SECOND_CLAP_TIME_WINDOW_MIN = 190;
const SECOND_CLAP_TIME_WINDOW_MAX = 440;
var firstClapTime;
var secondClapTime;
var lastClapDetectedAt = 0;
var attackFramesHeld = 0;
const ALPHA = 0.01;
const NOISE_MULTIPLIER = 3.2;
var micNoiseFloor = 0.003;
var hf;
var isClap;
var now;
const clapTimeline = [];
const ClapState = {
    IDLE: 'IDLE',
    ONE_CLAP: 'ONE_CLAP',
    ARMED: 'ARMED'
};
var clapState = ClapState.IDLE;
var firstClapTime = null;
var confirmDoubleClapSuccessTimer = null;
var clapMonitorLastRanTime;
var consecutiveClapMonitorRunDelays = 0;
var wasLastClapMonitorRunSlowErrorConfirmed = false;
var attackHoldFrames = 3;
var clapPort = null;

//note: since firefox handles mic permissions differently and you can't port directly between this script and the content one...
//the firefox version injects this js directly into the same frame as the content script so it shares all the same variables and functions as the content script...
//except for the configuration page, that behaves the same way as chrome
//TODO: set up some sort of namespaces or imports/exports for the variables/functions in this file
var isInContentFrame = false;
if (typeof mainVideoCollection !== 'undefined') {
    isInContentFrame = true;
} else {
    let queryString = window.location.search;
    let urlParams = new URLSearchParams(queryString);
    window.scriptPurpose = urlParams.get('purpose') ?? 'listen-double-clap';
    window.isDebugMode = urlParams.get('debug');
    window.clapSensitivity = urlParams.get('sensitivity') ?? 30;
}

//user set preferences:
var quietNoiseFloor;
var baseAttackThreshold;
var minAttackThreshold;
var hfThreshold;
var hfMin;
var hfMax;
const minSensitivityValues = {
    quietNoiseFloor: 0.06,
    baseAttackThreshold: 0.05,
    minAttackThreshold: 0.04,
    hfThreshold: 2300,
    hfMin: 8200,
    hfMax: 9200
};
const maxSensitivityValues = {
    quietNoiseFloor: 0.005,
    baseAttackThreshold: 0.008,
    minAttackThreshold: 0.007,
    hfThreshold: 500,
    hfMin: 6500,
    hfMax: 7500
};

if (isDebugMode) console.log('double-clap-detector.js running');

setClapSensitivity(clapSensitivity);


if (isInContentFrame) {
    prepFoClapMonitor();
} else {
    chrome.runtime.onConnect.addListener(p => {
        if (p.name === "clap-detector") {
            if (isDebugMode) console.log('clap-detector connected');
            clapPort = p;
            clapPort.onDisconnect.addListener(() => {
                clapPort = null;
            });

            clapPort.onMessage.addListener(message => {
                if (message.action === "connected") {
                    prepFoClapMonitor();
                } else if (message.action === "update-sensitivity") {
                    clapSensitivity = message.clapSensitivity;
                    setClapSensitivity(clapSensitivity);
                }
            });
        }
    });
}


function setClapSensitivity(clapSensitivity) {
    const percent = clamp(clapSensitivity, 0, 100);
    const t = percent / 100;

    quietNoiseFloor = lerp(minSensitivityValues.quietNoiseFloor, maxSensitivityValues.quietNoiseFloor, t);
    baseAttackThreshold = lerp(minSensitivityValues.baseAttackThreshold, maxSensitivityValues.baseAttackThreshold, t);
    minAttackThreshold = lerp(minSensitivityValues.minAttackThreshold, maxSensitivityValues.minAttackThreshold, t);
    hfThreshold = lerp(minSensitivityValues.hfThreshold, maxSensitivityValues.hfThreshold, t);
    hfMin = lerp(minSensitivityValues.hfMin, maxSensitivityValues.hfMin, t);
    hfMax = lerp(minSensitivityValues.hfMax, maxSensitivityValues.hfMax, t);
}


function sendToContent(data) {
    if (clapPort) {
        clapPort.postMessage(data);
    } else {
        if (isDebugMode) console.log('clapPort not connected');
    }
}


function prepFoClapMonitor() {
    navigator.mediaDevices.getUserMedia({
        audio: {
            channelCount: 2,
            echoCancellation: false,
            noiseSuppression: false,
            autoGainControl: false,
        }
    })
        .then((stream) => {
            //microphone permission granted

            if (isDebugMode) console.log('microphone connected');

            let inUseMicName = stream.getAudioTracks()[0].label;
            sendMicPermissionSuccess(inUseMicName);

            microphoneContext = new AudioContext();
            microphoneAnalyser = microphoneContext.createAnalyser();
            microphoneAnalyserFrequency = microphoneContext.createAnalyser();
            microphoneAnalyser.fftSize = microphoneAnalyserFrequency.fftSize = 2048; //best to keep this high to help us discriminate what isn't a clap - delay accounted for with attack hold

            microphoneMediaStreamSource = microphoneContext.createMediaStreamSource(stream);
            microphoneMediaStreamSource.connect(microphoneAnalyser);
            microphoneMediaStreamSource.connect(microphoneAnalyserFrequency);

            tData = new Float32Array(microphoneAnalyser.fftSize);
            fData = new Uint8Array(microphoneAnalyserFrequency.frequencyBinCount);

            clapMonitorLastRanTime = Date.now();
            clapMonitor();
        })
        .catch((error) => {
            if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
                //don't want to open this tab if it is already open
                //TODO: can I even do this from the a content script in firefox?
                if (scriptPurpose !== 'listen-double-clap-configure' || isInContentFrame) {
                    //have to open this from here instead of content due to permissions
                    let url = chrome.runtime.getURL('mic-settings-for-double-clap.html?message=permission-error');
                    window.open(url, '_blank');
                }

                sendMicPermissionError();
            } else {
                console.error(error);
            }
        });
}


function clapMonitor() {
    const startTime = Date.now();

    performanceCheck(startTime);

    microphoneAnalyser.getFloatTimeDomainData(tData);
    microphoneAnalyserFrequency.getByteFrequencyData(fData);

    let sum = 0;
    for (let v of tData) sum += v * v;
    micRMS = Math.sqrt(sum / tData.length);

    micNoise = micNoise ? micNoise * (1 - ALPHA) + micRMS * ALPHA : micRMS;
    micAttack = micRMS - lastRMS;
    lastRMS = micRMS;
    rmsThreshold = micNoise * NOISE_MULTIPLIER;
    let isRMSHit = micRMS > rmsThreshold;

    micNoiseFloor = micNoiseFloor * 0.99 + micRMS * 0.01;
    const micNoiseRatio = micNoiseFloor / quietNoiseFloor;
    attackThreshold = clamp(
        baseAttackThreshold / Math.sqrt(micNoiseRatio),
        minAttackThreshold,
        baseAttackThreshold
    );

    //increasing window that attack is eligible because it sometimes takes a little for HF to hit after clap
    if (micAttack > attackThreshold) {
        attackFramesHeld = attackHoldFrames;
    } else if (attackFramesHeld > 0) {
        attackFramesHeld--;
    }
    let isAttackHit = attackFramesHeld > 0;

    const ny = microphoneContext.sampleRate / 2;
    const b0 = Math.floor(hfMin / ny * fData.length);
    const b1 = Math.floor(hfMax / ny * fData.length);
    hf = 0;
    for (let i = b0; i <= b1; i++) hf += fData[i];
    let isHFHit = hf > hfThreshold;

    isClap = isRMSHit && isAttackHit && isHFHit;
    now = performance.now();

    if (isClap) {
        if (isDebugMode) {
            console.log("attackFramesHeld: " + attackFramesHeld);
            console.log("micRMS: " + micRMS.toFixed(3));
            console.log("rmsThreshold: " + rmsThreshold.toFixed(3));
            console.log("micAttack: " + micAttack.toFixed(3));
            console.log("attackThreshold: " + attackThreshold.toFixed(3));
            console.log("hf: " + hf);
            console.log("hfThreshold: " + hfThreshold);
        }

        attackFramesHeld = 0;

        //remove potentially counting the same clap spike twice
        if (now - lastClapDetectedAt > 40) {
            lastClapDetectedAt = now;
            onClap(now);
            if (isDebugMode) clapTimeline.push({ time: now });
        }
    }

    if (isDebugMode) sendClapDebugOverlay();

    const elapsed = Date.now() - startTime;
    const delay = Math.max(0, 16 - elapsed); //60Hz-ish
    //TODO: somehow prevent certain websites from drastically slowing this loop down
    setTimeout(() => {
        clapMonitor();
    }, delay);
}


function onClap(now) {
    switch (clapState) {
        case ClapState.IDLE: {
            // first clap
            firstClapTime = now;

            sendClapIndicator(
                // microphone
                // green square (first clap registered)
                // clap
                '\uD83C\uDFA4 \uD83D\uDFE9 \uD83D\uDC4F',
                'first clap detected, waiting for second clap...',
                SECOND_CLAP_TIME_WINDOW_MAX + 500
            );

            clapState = ClapState.ONE_CLAP;
            break;
        }

        case ClapState.ONE_CLAP: {
            const clapGap = now - firstClapTime;
            if (isDebugMode) console.log('Time between confirmed claps = ' + clapGap.toFixed(0));

            if (clapGap < SECOND_CLAP_TIME_WINDOW_MIN) {
                // Second clap too fast -> clear claps
                sendClapIndicator(
                    // microphone
                    // green square
                    // red X
                    // clap
                    '\uD83C\uDFA4 \uD83D\uDFE9 \u274C \uD83D\uDC4F',
                    'second clap too fast, resetting...',
                    1000
                );
                resetClaps();
                break;
            }

            if (clapGap > SECOND_CLAP_TIME_WINDOW_MAX && clapGap < SECOND_CLAP_TIME_WINDOW_MAX + 250) {
                // Narrow late miss -> clear claps
                sendClapIndicator(
                    // microphone
                    // green square
                    // clap
                    // red X
                    '\uD83C\uDFA4 \uD83D\uDFE9 \uD83D\uDC4F \u274C',
                    'second clap too slow, resetting...',
                    1000
                );
                resetClaps();
                break;
            }

            if (clapGap > SECOND_CLAP_TIME_WINDOW_MAX + 500) {
                // Way too slow -> treat as first app
                firstClapTime = now;

                sendClapIndicator(
                    // microphone
                    // green square
                    // clap
                    '\uD83C\uDFA4 \uD83D\uDFE9 \uD83D\uDC4F',
                    'first clap detected, waiting for second clap...',
                    SECOND_CLAP_TIME_WINDOW_MAX + 500
                );
                break;
            }

            // Valid second clap -> wait to make sure no third clap
            sendClapIndicator(
                // microphone
                // green square
                // green square
                '\uD83C\uDFA4 \uD83D\uDFE9 \uD83D\uDFE9',
                'second clap detected, waiting for no more claps...'
            );

            //TODO: get isCommercialState from content.js
            //wait longer when it isn't commercial to avoid accidentally cutting away from the game and shorter during commercials to get back to the game sooner
            //const guardAfter = isCommercialState ? 800 : 1500;
            //does it feel less janky to the user when this doesn't change ever?
            const guardAfter = 1250;

            confirmDoubleClapSuccessTimer = setTimeout(() => {
                // No third clap -> success
                sendManualCommercialModeToggle();

                sendClapIndicator(
                    // microphone
                    // green check
                    // green check
                    '\uD83C\uDFA4 \u2705 \u2705',
                    'successful double clap!',
                    1000
                );

                resetClaps();
            }, guardAfter);

            clapState = ClapState.ARMED;
            break;
        }

        case ClapState.ARMED: {
            // Third clap detected -> cancel and clear claps
            sendClapIndicator(
                // microphone
                // red X
                // red X
                // red X
                '\uD83C\uDFA4 \u274C \u274C \u274C',
                'third clap detected, resetting...',
                1000
            );

            resetClaps();
            break;
        }
    }
}


function resetClaps() {
    firstClapTime = null;

    if (confirmDoubleClapSuccessTimer) {
        clearTimeout(confirmDoubleClapSuccessTimer);
        confirmDoubleClapSuccessTimer = null;
    }

    clapState = ClapState.IDLE;
}


function clamp(v, min, max) {
    return Math.max(min, Math.min(max, v));
}


function lerp(a, b, t) {
    return a + (b - a) * t;
}


//checks for slowdowns in clap monitoring and let user know //TODO: avoid these slowdowns completely
function performanceCheck(timeNow) {
    let timeBetweenClapMonitorRuns = timeNow - clapMonitorLastRanTime;
    if (timeBetweenClapMonitorRuns > 500) {
        consecutiveClapMonitorRunDelays++;
        if (consecutiveClapMonitorRunDelays > 10) {
            sendSlowClapMonitorIssue();

            wasLastClapMonitorRunSlowErrorConfirmed = true;
        }
    } else {
        consecutiveClapMonitorRunDelays = 0;
        if (wasLastClapMonitorRunSlowErrorConfirmed) {
            sendClapIndicator(
                // microphone
                // clap
                // clap
                '\uD83C\uDFA4 \uD83D\uDC4F \uD83D\uDC4F',
                'waiting for claps...'
            );

            wasLastClapMonitorRunSlowErrorConfirmed = false;
        }
    }
    clapMonitorLastRanTime = timeNow;
}


function sendClapIndicator(text, debugText, resetAfterMs = null) {
    if (isInContentFrame) {
        setClapIndicator(text, resetAfterMs);
    } else {
        sendToContent({
            action: "update-clap-indicator",
            text: text,
            debugText: debugText,
            resetAfterMs: resetAfterMs
        });
    }
}


function sendManualCommercialModeToggle() {
    if (isInContentFrame) {
        manualCommercialModeToggle();
    } else {
        sendToContent({ action: "manual-commercial-mode-toggle" });
    }
}


function sendClapDebugOverlay() {
    const clapDebugOverlayData = {
        clapTimeline,
        micRMS,
        micAttack,
        micNoise,
        hf,
        now,
        rmsThreshold,
        attackThreshold,
        baseAttackThreshold,
        minAttackThreshold,
        hfThreshold,
    }

    if (isInContentFrame) {
        updateClapDebugOverlay(clapDebugOverlayData);
    } else {
        sendToContent({
            action: "update-clap-debug-metrics",
            clapDebugOverlayData: clapDebugOverlayData,
        });
    }
}


function sendMicPermissionSuccess(inUseMicName) {
    if (isInContentFrame) {
        micPermissionSuccess(inUseMicName);
    } else {
        sendToContent({
            action: "mic-permission-success",
            inUseMicName: inUseMicName
        });
    }
}


function sendMicPermissionError() {
    if (isInContentFrame) {
        micPermissionError();
    } else {
        sendToContent({ action: "mic-permission-error" }); //this will initiate closing this iframe
    }
}


function sendSlowClapMonitorIssue() {
    if (isInContentFrame) {
        slowClapMonitorIssue();
    } else {
        sendToContent({ action: "slow-clap-monitor-issue" });
    }
}