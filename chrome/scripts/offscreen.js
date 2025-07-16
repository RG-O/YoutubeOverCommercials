
var constraints;
var media;
var videoElement;
var canvas;
var ctx;
//TODO: combine
var canvasAI;
var ctxAI;
var viewing = false;
var audioContext;
var audioSource;
var audioAnalyzer;
var audioDataArray;
var isAudioConnected = false;
var openAIAPIKey;
var newWidth;


chrome.runtime.onMessage.addListener(function (message) {
    if (message.target == 'offscreen') {
        if (message.action == 'start-viewing') {
            constraints = message.constraints;
            startViewing(constraints);
        } else if (message.action == 'start-viewing-ai-openai') {
            if (message.api) {
                openAIAPIKey = 'Bearer ' + message.api;
                constraints = message.constraints;
                startViewing(constraints);
            }
        } else if (message.action == 'start-listening') {
            constraints = message.constraints;
            startListening(constraints);
        } else if (message.action == 'stop-viewing') {
            stopViewing();
        } else if (message.action == 'resume-viewing') {
            //does not currently work, need to close and reopen offscreen in order to pause and resume viewing tab
            startViewing(constraints);
        } else if (message.action == 'disconnect-tab-audio') {
            if (isAudioConnected) {
                audioSource.disconnect(audioContext.destination);
                isAudioConnected = false;
            }
        } else if (message.action == 'connect-tab-audio') {
            if (!isAudioConnected) {
                audioSource.connect(audioContext.destination);
                isAudioConnected = true;
            }
        } else if (message.action == 'close') {
            window.close();
        }
    }
});


async function startViewing(constraints) {

    if (!viewing) {

        media = await navigator.mediaDevices.getUserMedia(constraints);

        videoElement = document.createElement('video');
        videoElement.srcObject = media;
        videoElement.muted = true;
        videoElement.play();

        canvas = document.createElement('canvas');
        canvas.width = 1;
        canvas.height = 1;
        //canvas.width = 30; //debug-high
        //canvas.height = 30; //debug-high
        ctx = canvas.getContext('2d', { willReadFrequently: true });

        //TODO: combine with above dynamically
        canvasAI = document.createElement('canvas');
        //TODO: only update if larger than
        //480
        //360
        //240
        //144
        let screenAspectRatio = constraints.video.mandatory.maxWidth / constraints.video.mandatory.maxHeight;
        newWidth = 144 * screenAspectRatio;
        canvasAI.width = newWidth;
        canvasAI.height = 144;
        //canvas.width = 30; //debug-high
        //canvas.height = 30; //debug-high
        ctxAI = canvasAI.getContext('2d', { willReadFrequently: true });

        viewing = true;

    }

}


async function startListening(constraints) {

    if (!viewing) {

        media = await navigator.mediaDevices.getUserMedia(constraints);

        audioContext = new AudioContext();
        audioSource = audioContext.createMediaStreamSource(media);
        audioAnalyzer = audioContext.createAnalyser();
        audioAnalyzer.fftSize = 512;
        audioAnalyzer.minDecibels = -127;
        audioAnalyzer.maxDecibels = 0;
        audioAnalyzer.smoothingTimeConstant = 0;
        audioSource.connect(audioAnalyzer);
        //make sure audio still plays for user
        audioSource.connect(audioContext.destination);
        isAudioConnected = true;

        audioDataArray = new Uint8Array(audioAnalyzer.frequencyBinCount);

        viewing = true;

    }

}


chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
    if (message.target == 'offscreen') {
        if (message.action == 'capture-screenshot') {

            if (viewing) {

                ctx.drawImage(videoElement, message.coordinates.x, message.coordinates.y, 1, 1, 0, 0, 1, 1);
                //ctx.drawImage(videoElement, message.coordinates.x, message.coordinates.y, 30, 30, 0, 0, 30, 30); //debug-high
                //let image = canvas.toDataURL('image/png'); //debug-high

                let pixelColorUnformated = ctx.getImageData(0, 0, 1, 1).data;
                let pixelColor = { r: pixelColorUnformated[0], g: pixelColorUnformated[1], b: pixelColorUnformated[2] };

                //sendResponse({ pixelColor: pixelColor, image: image, myCoordinates: message.coordinates }); //debug-high
                sendResponse({ pixelColor: pixelColor });

            } else {

                //startViewing(constraints);

                //return pixel color as white
                let pixelColor = { r: 255, g: 255, b: 255 };
                sendResponse({ pixelColor: pixelColor });

            }

        } else if (message.action == 'capture-audio-level') {

            audioAnalyzer.getByteFrequencyData(audioDataArray);
            let volumeSum = 0;
            for (const volume of audioDataArray) {
                volumeSum += volume;
            }
            let averageVolume = volumeSum / audioDataArray.length;
            let audioLevel = Math.round(averageVolume * 100 / 127);

            sendResponse({ audioLevel: audioLevel });

        }
    }
});


chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
    if (message.target == 'offscreen') {
        if (message.action == 'capture-ai-commercial-chance') {

            if (viewing) {

                console.log('start ai');

                ctxAI.drawImage(videoElement, 0, 0, newWidth, 144);
                ////ctx.drawImage(videoElement, message.coordinates.x, message.coordinates.y, 30, 30, 0, 0, 30, 30); //debug-high
                let image = canvasAI.toDataURL('image/png'); //debug-high

                //let pixelColorUnformated = ctx.getImageData(0, 0, 1, 1).data;
                //let pixelColor = { r: pixelColorUnformated[0], g: pixelColorUnformated[1], b: pixelColorUnformated[2] };

                ////sendResponse({ pixelColor: pixelColor, image: image, myCoordinates: message.coordinates }); //debug-high

                //openAIAPIKey
                const fetchStart = performance.now();
                fetch("https://api.openai.com/v1/chat/completions", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "Authorization": openAIAPIKey
                    },
                    //body: JSON.stringify({
                    //    model: "gpt-4", // or "gpt-3.5-turbo"
                    //    messages: [
                    //        { role: "user", content: "Say hello!" }
                    //    ],
                    //    max_tokens: 50
                    //})
                    body: JSON.stringify({
                        model: "gpt-4.1-mini",
                        messages: [
                            {
                                role: "system",
                                content: [
                                    { 
                                        type: "text", 
                                        //text: "Reply to each input with only a percentage value in standard decimal notation to the hundredths place, such as \"0.03\". The value must be between 0.00 and 1.00, inclusive. Do not add any other text, explanation, or formatting—only the numeric value.\n\n# Output Format\n\n- Single line containing only a number between 0.00 and 1.00 (inclusive), with two decimal places (e.g., 0.00, 0.03, 1.00).\n\n# Examples\n\nInput: [Any prompt]\nOutput: 0.42\n\n(Remember: Respond with only the percentage value as described, no matter what the input is.)" 
                                        text: "Reply to each input with only a percentage value in standard decimal notation to the hundredths place, such as \"0.03\". The value must be between 0.00 and 1.00, inclusive. Do not add any other text, explanation, or formatting—only the numeric value."
                                    },
                                ]
                            },
                            {
                                role: "user",
                                content: [
                                    //{ type: "text", text: "What does this image show?" },
                                    //{ type: "text", text: "This is a screenshot of live tv. Give me just the percentage chance that this tv channel is currently on commercial break." },
                                    { 
                                        type: "text", 
                                        //text: "Pretend you are a TV watching expert that only answers in percentages and always gives their best guess. This is a screenshot of my TV. Judging by this screenshot alone, what is the percentage chance that this screenshot is of a TV commercial or break away from the programming? Only answer in a percentage. Do not tell me that you can't."
                                        //text: "This is a screenshot of live TV. What is the percentage chance that this TV channel is currently on commercial break?"
                                        //text: "This is a screenshot of live TV of sports. What is the percentage chance that this TV channel is currently on commercial break? Look for clues like lack of graphics or lack of sports."
                                        //text: "This is a screenshot from a live sports TV broadcast. Based only on this image, estimate the probability that the TV channel is currently on a commercial break. For this purpose, define 'commercial break' broadly to include traditional ads, movie trailers, network promos, sports promos, upcoming show previews, or anything not part of the live sports event or its immediate commentary. Please take into account that you are only seeing a single frame in time, and your confidence should reflect that uncertainty."
                                        text: "This is a screenshot of live TV. What are the chances this is a commercial break and not a live baseball broadcast?"
                                    },
                                    {
                                        type: "image_url",
                                        image_url: {
                                            url: image
                                        }
                                    }
                                ]
                            }
                        ],
                        max_tokens: 5
                    })
                })
                .then(response => response.json())
                .then(data => {
                    const fetchEnd = performance.now();
                    console.log('here!');
                    let fetchTime = ((fetchEnd - fetchStart) / 1000).toFixed(3);
                    let chanceOfCommercial = formatAsPercentage(data.choices[0].message.content);
                    let totalTokens = data.usage.total_tokens;
                    console.log(chanceOfCommercial);
                    sendResponse({ chanceOfCommercial: chanceOfCommercial, data: data, image: image, fetchTime: fetchTime, totalTokens: totalTokens });
                })
                    .catch(error => {
                    //TODO: send current state if error
                    console.error("Error:", error);
                });

                //setTimeout(() => {
                //    sendResponse({ chanceOfCommercial: 'blah' });
                //}, 10000);



            } else {

                sendResponse({ chanceOfCommercial: false });

            }

            return true; //keep message channel open for async response

        }
    }
});


function stopViewing() {

    if (viewing) {

        viewing = false;

        //TODO: is pausing really necessary at all here?
        videoElement.pause();

        media.getTracks().forEach(function (track) {
            track.stop();
            //track.enabled = false;
        });

        //media = undefined;

    }

}


//TODO: check if correct format
function formatAsPercentage(value) {
    return (value * 100).toFixed(0);
}