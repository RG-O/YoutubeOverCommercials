
//AI commercial detection that runs entirely inside the offscreen document
//uses the Minus-v0.1 vision language model (https://huggingface.co/TheGarageDev/Minus-v0.1) the same way the Minus chrome extension does (https://github.com/garagehq/Minus-chrome-extension)
//note: all javascript and wasm is bundled with the extension in lib/transformers, only the model weights (data, not code) are downloaded from hugging face and then cached by the browser
//note: relies on videoElement and viewing globals from offscreen.js which is loaded before this module in offscreen.html

import { AutoModelForImageTextToText, AutoProcessor, RawImage, env } from '../lib/transformers/transformers.min.js';

const AI_MODEL_ID = 'TheGarageDev/Minus-v0.1';
const AI_MODEL_DTYPE = { vision_encoder: 'q8', embed_tokens: 'q8', decoder_model_merged: 'q4' };
const AI_PROMPT = 'Is this an advertisement? Answer Yes or No.';
const AI_PROMPT_TEXT = `<|startoftext|><|im_start|>user\n<image>${AI_PROMPT}<|im_end|>\n<|im_start|>assistant\n`;
//keeping frames to 512px wide so the model processes them as a single tile which keeps inference fast
const AI_FRAME_MAX_WIDTH = 512;
const AI_FRAME_MAX_HEIGHT = 512;

//never load any code from a CDN, everything is served from the extension package
env.allowLocalModels = false;
env.allowRemoteModels = true;
env.useBrowserCache = true;
env.backends.onnx.wasm.wasmPaths = {
    mjs: chrome.runtime.getURL('lib/transformers/ort-wasm-simd-threaded.asyncify.mjs'),
    wasm: chrome.runtime.getURL('lib/transformers/ort-wasm-simd-threaded.asyncify.wasm'),
};
env.backends.onnx.wasm.numThreads = 1; //offscreen document isn't cross origin isolated so threads are not available
env.backends.onnx.wasm.proxy = false;

var aiModelState = 'not-loaded'; //not-loaded, loading, ready, error
var aiModelError = null;
var aiModelLoadPromise = null;
var aiModel;
var aiProcessor;
var aiYesTokenIds = [];
var aiNoTokenIds = [];
var aiDownloadProgressByFile = {};
var aiFrameCanvas;
var aiFrameCtx;
var isAIClassifying = false;


chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
    if (message.target == 'offscreen') {
        if (message.action == 'ai-model-status') {

            //starts loading the model if it hasn't been already so the content script can just keep asking for status
            if (aiModelState === 'not-loaded' || (aiModelState === 'error' && message.shouldRetryOnError)) {
                loadAIModel();
            }

            sendResponse(getAIModelStatus());

        } else if (message.action == 'ai-classify-frame') {

            classifyCurrentFrame(message.maskRects)
                .then((pAd) => {
                    sendResponse({ wasSuccessfulCall: true, pAd: pAd });
                })
                .catch((error) => {
                    sendResponse({ wasSuccessfulCall: false, error: String(error?.message ?? error) });
                });

            return true; //keep message channel open for async response

        }
    }
});


function getAIModelStatus() {

    let loaded = 0;
    let total = 0;
    for (const file of Object.values(aiDownloadProgressByFile)) {
        loaded += file.loaded;
        total += file.total;
    }

    return {
        state: aiModelState,
        error: aiModelError,
        progress: total > 0 ? Math.floor((loaded / total) * 100) : 0,
    };

}


function loadAIModel() {

    if (aiModelLoadPromise) {
        return aiModelLoadPromise;
    }

    aiModelState = 'loading';
    aiModelError = null;
    aiDownloadProgressByFile = {};

    aiModelLoadPromise = (async () => {

        //the q4 decoder uses an operator that only exists on webgpu, so there is no cpu fallback for this model
        const gpuAdapter = navigator.gpu ? await navigator.gpu.requestAdapter() : null;
        if (!gpuAdapter) {
            throw new Error('WebGPU is not available. Enable hardware acceleration in Chrome settings and make sure your graphics drivers are up to date.');
        }

        const progressCallback = (progressInfo) => {
            if (progressInfo.status === 'progress' && progressInfo.total) {
                aiDownloadProgressByFile[progressInfo.file] = { loaded: progressInfo.loaded, total: progressInfo.total };
            }
        };

        aiProcessor = await AutoProcessor.from_pretrained(AI_MODEL_ID, { progress_callback: progressCallback });
        aiModel = await AutoModelForImageTextToText.from_pretrained(AI_MODEL_ID, {
            device: 'webgpu',
            dtype: AI_MODEL_DTYPE,
            progress_callback: progressCallback,
        });

        //collecting every way the tokenizer could start the words yes and no
        aiYesTokenIds = getFirstTokenIds(['Yes', ' Yes', 'yes', ' yes']);
        aiNoTokenIds = getFirstTokenIds(['No', ' No', 'no', ' no']);

        //warm up run so shaders get compiled before the first real frame and to verify inference actually works on this gpu
        const warmUpCanvas = new OffscreenCanvas(64, 64);
        const warmUpCtx = warmUpCanvas.getContext('2d');
        warmUpCtx.fillStyle = 'black';
        warmUpCtx.fillRect(0, 0, 64, 64);
        await runAIModel(RawImage.fromCanvas(warmUpCanvas).rgb());

        aiModelState = 'ready';

    })()
        .catch((error) => {
            console.error('Live Commercial Blocker: Failed to load AI model:', error);
            aiModelState = 'error';
            aiModelError = String(error?.message ?? error);
            aiModel = null;
            aiProcessor = null;
            aiModelLoadPromise = null;
        });

    return aiModelLoadPromise;

}


function getFirstTokenIds(words) {

    const tokenIds = new Set();
    for (const word of words) {
        const ids = aiProcessor.tokenizer.encode(word, { add_special_tokens: false });
        if (ids.length > 0) {
            tokenIds.add(Number(ids[0]));
        }
    }
    return [...tokenIds];

}


//returns the probability (0-1) that the current frame of the tab is a commercial
async function classifyCurrentFrame(maskRects) {

    if (aiModelState !== 'ready') {
        throw new Error('AI model is not ready');
    }

    if (!viewing || !videoElement || !videoElement.videoWidth) {
        throw new Error('Tab is not being viewed');
    }

    //only ever run one frame at a time so the gpu doesn't get backed up
    if (isAIClassifying) {
        throw new Error('Previous frame is still being analyzed');
    }

    isAIClassifying = true;

    try {

        const videoWidth = videoElement.videoWidth;
        const videoHeight = videoElement.videoHeight;
        const scale = Math.min(AI_FRAME_MAX_WIDTH / videoWidth, AI_FRAME_MAX_HEIGHT / videoHeight, 1);
        const frameWidth = Math.round(videoWidth * scale);
        const frameHeight = Math.round(videoHeight * scale);

        if (!aiFrameCanvas || aiFrameCanvas.width !== frameWidth || aiFrameCanvas.height !== frameHeight) {
            aiFrameCanvas = new OffscreenCanvas(frameWidth, frameHeight);
            aiFrameCtx = aiFrameCanvas.getContext('2d', { willReadFrequently: true });
            aiFrameCtx.imageSmoothingQuality = 'high';
        }

        aiFrameCtx.drawImage(videoElement, 0, 0, frameWidth, frameHeight);

        //blacking out anything the extension itself is showing on top of the main video (like the overlay video) so the model only judges the main video
        //note: mask rects are percentages of the window so they line up no matter the capture resolution
        if (maskRects) {
            aiFrameCtx.fillStyle = 'black';
            for (const rect of maskRects) {
                aiFrameCtx.fillRect(
                    Math.floor(rect.left * frameWidth),
                    Math.floor(rect.top * frameHeight),
                    Math.ceil(rect.width * frameWidth),
                    Math.ceil(rect.height * frameHeight)
                );
            }
        }

        return await runAIModel(RawImage.fromCanvas(aiFrameCanvas).rgb());

    } finally {
        isAIClassifying = false;
    }

}


//runs a single decode step and compares how likely the model is to answer yes vs no
async function runAIModel(image) {

    const inputs = await aiProcessor(image, AI_PROMPT_TEXT, { add_special_tokens: false });
    const { logits } = await aiModel({ ...inputs });

    const [, sequenceLength, vocabSize] = logits.dims;
    const lastPositionOffset = (sequenceLength - 1) * vocabSize;
    const logitsData = logits.data;

    const yesLogits = aiYesTokenIds.map((id) => Number(logitsData[lastPositionOffset + id]));
    const noLogits = aiNoTokenIds.map((id) => Number(logitsData[lastPositionOffset + id]));

    //softmax over only the yes/no tokens, subtracting the max for numerical stability
    const maxLogit = Math.max(...yesLogits, ...noLogits);
    const yesMass = yesLogits.reduce((sum, logit) => sum + Math.exp(logit - maxLogit), 0);
    const noMass = noLogits.reduce((sum, logit) => sum + Math.exp(logit - maxLogit), 0);

    if (typeof logits.dispose === 'function') {
        logits.dispose();
    }

    return yesMass / (yesMass + noMass);

}
