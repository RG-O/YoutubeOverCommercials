

//TODO: which of these don't need to be in offscreen?
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
//const QUIET_NOISE_FLOOR = 0.0195; //volume when attack threshold starts to lower?? or volume when it gets to the lowest?
const QUIET_NOISE_FLOOR = 0.035; //volume when attack threshold starts to lower?? or volume when it gets to the lowest?
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

const queryString = window.location.search;
const urlParams = new URLSearchParams(queryString);
const scriptPurpose = urlParams.get('purpose');
const isDebugMode = urlParams.get('debug');
var clapSensitivity = urlParams.get('sensitivity');

//user set preferences:
var baseAttackThreshold = 0.031;
var minAttackThreshold = 0.025;
var hfThreshold = 1250; //would be nice to have this higher but then it won't work as well with lower quality mics
var attackHoldFrames = 3;
var hfMin = 7000;
var hfMax = 8000;

if (isDebugMode) console.log('double-clap-detector.js running');

var clapPort = null;
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


setClapSensitivity(clapSensitivity);


function setClapSensitivity(clapSensitivity) {
    switch (clapSensitivity) {
        //lowest sensitity (more ideal)
        case '0':
            baseAttackThreshold = 0.035;
            minAttackThreshold = 0.028;
            hfThreshold = 2000; //would be nice to have this higher but then it won't work as well with lower quality mics
            attackHoldFrames = 3;
            hfMin = 8000;
            hfMax = 9000;
            break;
        case '1':
            baseAttackThreshold = 0.034;
            minAttackThreshold = 0.027;
            hfThreshold = 1750; //would be nice to have this higher but then it won't work as well with lower quality mics
            attackHoldFrames = 3;
            hfMin = 7500;
            hfMax = 8500;
            break;
        case '2':
            baseAttackThreshold = 0.032;
            minAttackThreshold = 0.025;
            hfThreshold = 1500; //would be nice to have this higher but then it won't work as well with lower quality mics
            attackHoldFrames = 3;
            hfMin = 7000;
            hfMax = 8000;
            break;
        case '3':
            baseAttackThreshold = 0.031;
            minAttackThreshold = 0.025;
            hfThreshold = 1250; //would be nice to have this higher but then it won't work as well with lower quality mics
            attackHoldFrames = 2;
            hfMin = 7000;
            hfMax = 8000;
            break;
        //highest sensivity (less ideal - more false positives)
        case '4':
            baseAttackThreshold = 0.013;
            minAttackThreshold = 0.013;
            hfThreshold = 700; //would be nice to have this higher but then it won't work as well with lower quality mics
            attackHoldFrames = 3;
            hfMin = 6500;
            hfMax = 7500;
            break;
    }
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
            sendToContent({
                action: "mic-permission-success",
                inUseMicName: inUseMicName
            });

            microphoneContext = new AudioContext();
            microphoneAnalyser = microphoneContext.createAnalyser();
            microphoneAnalyserFrequency = microphoneContext.createAnalyser();
            microphoneAnalyser.fftSize = microphoneAnalyserFrequency.fftSize = 2048; //best to keep this high to help us discriminate what isn't a clap - delay accounted for with attack hold

            microphoneMediaStreamSource = microphoneContext.createMediaStreamSource(stream);
            microphoneMediaStreamSource.connect(microphoneAnalyser);
            microphoneMediaStreamSource.connect(microphoneAnalyserFrequency);

            tData = new Float32Array(microphoneAnalyser.fftSize);
            fData = new Uint8Array(microphoneAnalyserFrequency.frequencyBinCount);

            clapMonitor();
        })
        .catch((error) => {
            if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
                //don't want to open this tab if it is already open
                if (scriptPurpose !== 'listen-double-clap-configure') {
                    //have to open this from here instead of content due to permissions
                    let url = chrome.runtime.getURL('mic-settings-for-double-clap.html?message=permission-error');
                    window.open(url, '_blank');
                }

                sendToContent({ action: "mic-permission-error" }); //this will initiate closing this iframe
            } else {
                console.error(error);
            }
        });
}


function clapMonitor() {
    const startTime = Date.now();

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
    const micNoiseRatio = micNoiseFloor / QUIET_NOISE_FLOOR;
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
            if (isDebugMode) console.log('Time between confirmed claps = ' + clapGap);

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
                sendToContent({ action: "manual-commercial-mode-toggle" });

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


function clamp(v, min, max) {
    return Math.max(min, Math.min(max, v));
}


function sendClapIndicator(text, debugText, resetAfterMs = null) {
    //TODO: had helper function to see if port is open?
    sendToContent({
        action: "update-clap-indicator",
        text: text,
        debugText: debugText,
        resetAfterMs: resetAfterMs
    });
}


function resetClaps() {
    firstClapTime = null;

    if (confirmDoubleClapSuccessTimer) {
        clearTimeout(confirmDoubleClapSuccessTimer);
        confirmDoubleClapSuccessTimer = null;
    }

    clapState = ClapState.IDLE;
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

    sendToContent({
        action: "update-clap-debug-metrics",
        clapDebugOverlayData: clapDebugOverlayData,
    });
}
