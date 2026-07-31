# Python WebSocket Overlay Template

This template creates a local server WebSocket that the Live Commercial Blocker browser 
extension connects to and calls when a commercial trigger and other status updates occur.

## Instructions

### Prerequisites

1. Have Live Commercial Blocker extension installed and enabled on your browser. 
([installation instructions](/#installation))
1. Have Python 3.13+ installed. ([Python For Beginners](https://www.python.org/about/gettingstarted/))

### Setup

1. Clone this entire repo and open [server.py](server.py) or copy/paste code 
from [server.py](server.py) into your own local python file.
1. pip install [requirements.txt](requirements.txt)
1. Run the python script
1. Navigate over to browser and open Live Commercial Blocker settings
1. Set "OVERLAY TYPE AND SOURCE" to "Overlay Plugin"
1. Set "API or WebSocket and URL" to "WS"
1. Set to "ws://localhost:64146" - Note: you can change this later in 
the script / extension if you would like
1. Click the refresh button if need be
1. Verify you get successful connection to plugin. You can also scroll down to 
See example extension manifest.
1. Click "Save & Apply"
1. Go to whatever website you like to stream from and set it to full screen
1. Click Ctrl + Shift + F (Firefox: Ctrl + Alt + C) to initiate the extension 
which will then connect to the plugin.
1. You can then view the logging in the plugin console.

### Modifying Template

1. Update the plugin name, id, version, and manifest to whatever fits your plugin.
1. Modify the template to do whatever you would like when commercials start and end.
See the examples folder if you need inspiration.

### Testing Tips

I recommend setting "MODE OF COMMERCIAL DETECTION" to "Manual - Keyboard" to 
make testing quicker and easier. Also check "Enable Debug Mode" in Additional Settings 
and then show the dev tool console in your browser to see more information that the 
plugin can pass through.
