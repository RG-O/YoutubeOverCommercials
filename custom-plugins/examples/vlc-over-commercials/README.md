# VLC Over Commercials

This plugin can be used to automatically play anything with VLC(TM) over top of commercials.

## Instructions

### Prerequisites

1. Have the newest version of VLC installed on your PC.
1. Have Live Commercial Blocker extension installed and enabled on your browser. 
([installation instructions](/README.md#installation))
1. Have Python 3.13+ installed. ([Python For Beginners](https://www.python.org/about/gettingstarted/))

### Setup

1. Clone this entire repo and open [vlc-over-commercials.py](vlc-over-commercials.py) or copy/paste code 
from [vlc-over-commercials.py](vlc-over-commercials.py) into your own local python file.
1. pip install [requirements.txt](requirements.txt)
1. Run the python script
1. Navigate over to browser and open Live Commercial Blocker settings
1. Set "OVERLAY TYPE AND SOURCE" to "Overlay Plugin"
1. Set "API or WebSocket and URL" to "API"
1. Set to "http://localhost:64144"
1. Click the refresh button if need be
1. Verify you get successful connection to plugin. 
1. Scroll down to plugin settings and enter desired stream or file URL into the 
"Video URL" field
1. Click "Save & Apply"
1. Go to whatever website you like to stream from and set it to full screen
1. Click Ctrl + Shift + F (Firefox: Ctrl + Alt + C) to initiate the extension.
1. Follow any additional on screen instructions
1. Enjoy while VLC automatically plays over top of commercials

## Help

If you need any help feel free to reach out on the [extension discord](/README.md#discord) 
or report any issues or enhancement requests on the [issues tab](https://github.com/RG-O/YoutubeOverCommercials/issues)

## Changelog

### Version 1.1.1

- Fixed black bars showing around some videos (like DVD rips and TV recordings) by measuring the size VLC actually displays them at
- Fixed the overlay size not updating when a stream changes shape or when VLC wasn't ready yet the first time
- Fixed VLC taking keyboard focus away from the browser, which caused the Windows taskbar to show over the stream
- Removed the "Should Attempt to Hide Taskbar" setting since it is no longer needed
- Improved security by only allowing VLC's web interface to be reached from your own PC, using a new random password each time
- Fixed the plugin not working when another program is already using port 8080
- Fixed video sizing not working when VLC is set to a language other than English
- Fixed VLC showing on the wrong monitor or at the wrong size when using multiple monitors or display scaling

## Disclaimers and Licensing

VLC is a trademark of the VideoLAN organization. 
This plugin is not affiliated with VLC or VideoLAN.