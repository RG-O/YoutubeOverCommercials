# Commercial Push Notifications

This plugin can be used to send notifications via ntfy to your phone to let you know when commercials start and end.

## Instructions

### Prerequisites

1. Have Live Commercial Blocker extension installed and enabled on your browser
([installation instructions](/README.md#installation))
1. Install [ntfy](https://ntfy.sh/) to your phone from Google Play or the Apple App Store
1. Have Python 3.13+ installed ([Python For Beginners](https://www.python.org/about/gettingstarted/))

### Setup

1. Clone this entire repo and open [commercial-push-notifications.py](commercial-push-notifications.py) or copy/paste code 
from [commercial-push-notifications.py](commercial-push-notifications.py) into your own local python file
1. pip install [requirements.txt](requirements.txt)
1. Run the python script
1. Navigate over to browser and open Live Commercial Blocker settings
1. Set "OVERLAY TYPE AND SOURCE" to "Overlay Plugin"
1. Set "API or WebSocket and URL" to "WS"
1. Set to "ws://localhost:64146"
1. Click the refresh button if need be
1. Verify you get successful connection to plugin
1. Scroll down to plugin settings and enter in a topic (NOTE: this must be unique to you and not match any other ntfy topics in the world)
1. Click "Save & Apply"
1. Go to whatever website you like to stream from and set it to full screen
1. Click Ctrl + Shift + F (Firefox: Ctrl + Alt + C) to initiate the extension
1. Follow any additional on screen instructions
1. Open the ntfy app on your phone and subscribe to the topic you created in step #10

## Pro Tip

Install Buzzkill and/or Tasker on your phone to trigger any actions you want based on the notifications.

## Help

If you need any help feel free to reach out on the [extension discord](/README.md#discord) 
or report any issues or enhancement requests on the [issues tab](https://github.com/RG-O/YoutubeOverCommercials/issues)
