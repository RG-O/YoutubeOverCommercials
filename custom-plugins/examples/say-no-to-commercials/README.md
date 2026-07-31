# Say NO to Commercials Plugin

This plugin can be used to speak set words or phrases to block or unblock live TV commercials. 
Upon first use, it downloads the Vosk speech recognition AI model to locally 
process speech.

## Instructions

### Prerequisites

1. Have Live Commercial Blocker extension installed and enabled on your browser. 
([installation instructions](/#installation))
1. Have Python 3.13+ installed. ([Python For Beginners](https://www.python.org/about/gettingstarted/))

### Setup

1. Clone this entire repo and open [say-no-to-commercials.py](say-no-to-commercials.py) or copy/paste code 
from [say-no-to-commercials.py](say-no-to-commercials.py) into your own local python file.
1. pip install [requirements.txt](requirements.txt)
1. Run the python script
1. Navigate over to browser and open Live Commercial Blocker settings
1. Set "MODE OF COMMERCIAL DETECTION" to "Trigger Plugin"
1. Set "WebSocket URL" to "ws://localhost:64145"
1. Click the refresh button if need be
1. Verify you get successful connection to plugin. 
1. Scroll down to plugin settings and set your camera and gesture preferences.
1. Click "Save & Apply"
1. Go to whatever website you like to stream from and set it to full screen
1. Click Ctrl + Shift + F (Firefox: Ctrl + Alt + C) to initiate the extension 
which will then connect to the plugin.
1. Upon first use, the plugin will download and unpack the Vosk speech recognition AI
model (50–100 MB)
1. After download, gesture towards your camera when there is a commercial to block it!

## Help

If you need any help feel free to reach out on the [extension discord](/#discord) 
or report any issues or enhancement requests on the [issues tab](https://github.com/RG-O/YoutubeOverCommercials/issues)
