# Overlay any Window Plugin

This plugin can be used to automatically place any window open on your PC you choose 
over top of commercials.

## Instructions

### Prerequisites

1. Have Live Commercial Blocker extension installed and enabled on your browser. 
([installation instructions](../README.md#installation))
1. Have Python 3.13+ installed. ([Python For Beginners](https://www.python.org/about/gettingstarted/))

### Setup

1. Clone this entire repo and open [overlay-any-window.py](overlay-any-window.py) or copy/paste code 
from [overlay-any-window.py](overlay-any-window.py) into your own local python file.
1. pip install [requirements.txt](requirements.txt)
1. Run the python script
1. Navigate over to browser and open Live Commercial Blocker settings
1. Set "OVERLAY TYPE AND SOURCE" to "Overlay Plugin"
1. Set "API or WebSocket and URL" to "WS"
1. Set to "ws://localhost:64146"
1. Click the refresh button if need be
1. Verify you get successful connection to plugin. 
1. Scroll down to plugin settings and choose desired window and any additional settings
1. Click "Save & Apply"
1. Go to whatever website you like to stream from and set it to full screen
1. Click Ctrl + Shift + F (Firefox: Ctrl + Alt + C) to initiate the extension.
1. Follow any additional on screen instructions
1. Enjoy while your choosen window automatically displays over top of commercials

## Help

If you need any help feel free to reach out on the [extension discord](../#discord) 
or report any issues or enhancement requests on the [issues tab](https://github.com/RG-O/YoutubeOverCommercials/issues)
