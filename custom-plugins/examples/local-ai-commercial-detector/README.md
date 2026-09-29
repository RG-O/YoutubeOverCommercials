# AI Commercial Detector

This is a plugin for the Live Commercial Blocker browser extension. This plugin calls a local AI 
vision model on your computer via Ollama to determine if a TV broadcast is currently in a commercial or not.

## Instructions

### System Requirements

- Probably NVIDIA RTX 3060+ GPU with 8GB+ VRAM (you might be able to get away with less, but 
less speed and/or accuracy will greatly reduce the usefullness of this plugin)

### Prerequisites

1. Have Live Commercial Blocker extension installed and enabled on your browser. 
([installation instructions](/README.md#installation))
1. Have Python 3.13+ installed.
	1. You can skip this step if you choose to go the exe path down below.
1. Have [Ollama](https://ollama.com/download) installed and running on your computer.
1. Have a vision model installed.
	1. After Ollama is installed and running, open a command prompt and run `ollama pull qwen2.5vl:7b` 
(this will be about a ~6GB download).

### Setup

#### Option 1: Install from exe (Windows)

1. This plugin is one of the plugins included in the Plugin Party Pack which has an exe. 
Installation instructions for that can be found [here](/companion-app-plugin-party-pack-combo/README.md).
1. Make sure the Plugin Party Pack is running and then navigate over to browser and open Live Commercial 
Blocker settings
1. Set MODE OF COMMERCIAL DETECTION to Detection/Trigger Plugin
1. Set Plugin Type to Plugin Party Pack
1. Check the AI Commercial Detector checkbox
1. Click "Save & Apply"

#### Option 2: Run from Python

1. Clone this entire repo and open [local-ai-commercial-detector.py](local-ai-commercial-detector.py) or copy/paste code 
from [local-ai-commercial-detector.py](local-ai-commercial-detector.py) into your own local python file.
1. pip install [requirements.txt](requirements.txt)
1. Run the python script
1. Navigate over to browser and open Live Commercial Blocker settings
1. Set MODE OF COMMERCIAL DETECTION to Detection/Trigger Plugin
1. Set "WebSocket URL" to "ws://localhost:64145"
1. Click the refresh button if need be
1. Verify you get successful connection to plugin.
1. Click "Save & Apply"

### Use

1. Go to whatever website you like to stream from and set it to full screen
1. Click Ctrl + Shift + F (Firefox: Ctrl + Alt + C) to initiate the extension 
which will then connect to the plugin.
1. You'll see in the corner the status of the AI Commercial Detector as it detects commercials vs regular programming

### Tips and Tinkering

- After enabling the plugin in the extension settings, you can scroll down and see a whole bunch of settings you can 
adjust for it such as the AI prompts, batch size, prompt frequency, etc.
- It can be useful to go into the extension settings within additional settings and check to enable debug mode. In a fresh 
streaming session this will place additional information including every model response to help with troubleshooting and 
tinkering you prompts.
- The way the extension/plugin works is that it takes full screenshots of your browser and sends it to the plugin so this 
plugin can't really be used with any of the video overlay modes without the video overlay getting in the way of the 
actual stream it is supposed to be checking for commercials. So either use one of the audio only overlays or use the 
VLC Over Commercials plugin (also included in the Plugin Party Pack).

## Help

If you need any help feel free to reach out on the [extension discord](/README.md#discord) 
or report any issues or enhancement requests on the [issues tab](https://github.com/RG-O/YoutubeOverCommercials/issues)

## Donate

If you appreciate this plugin or the Live Commercial Blocker browser extension and you would like to show your 
support, please consider donating https://www.buymeacoffee.com/ryango :)