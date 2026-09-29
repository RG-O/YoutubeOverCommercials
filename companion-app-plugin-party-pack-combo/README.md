## Advanced Logo Analyzer and Plugin Party Pack Desktop Tray Application

This is the [Advanced Logo Analyzer](/companion-app/README.md) and a collection of various plugins bundled into a single application that runs in the system tray.

## Plugins Included

Overlay Plugins:

- [VLC Over Commercials](/custom-plugins/examples/vlc-over-commercials) - Automatically play anything you would like from your PC's VLC player over top of commercials (requires install of VLC)
- [Overlay Any Window](/custom-plugins/examples/overlay-any-window) - Have literally any open window on your PC be shown over top of commercials
- [Commercial Push Notifications](examples/commercial-push-notifications) - Send notifications to your phone when commercials start and end

Detection/Trigger Plugins:

- [Voice Commercial Trigger](/custom-plugins/examples/say-no-to-commercials) - Set your own keywords or phrases to trigger blocking commercials or removing the blocker
- [Hand Gesture Commercial Trigger](/custom-plugins/examples/thumbs-down-commercials) - Connect to your webcam and give a thumbs down to block commercials and a thumbs up to remove the blocker
- [AI Commercial Detector](/custom-plugins/examples/local-ai-commercial-detector) - Use local AI to determine if a TV broadcast is currently in commercial or not (requires install of Ollama and recommeded NVIDIA RTX 3060+ GPU with 8GB+ VRAM)

## Setup

### Option 1: Install from exe (Windows)

1. Download the exe from the [GitHub release](https://github.com/RG-O/YoutubeOverCommercials/releases/tag/advanced-logo-analyzer-release-v1.0) TODO: This is just the Advanced Logo Analyzer link! I need to update this link!
2. Run the downloaded exe (note: you may need to click "More info" in the Windows popup to see the run option)
3. Follow the installation wizard
4. Run the application and it will appear in your system tray

### Option 2 (Advanced): Run from Python

1. Install Python 3.13+
2. Clone this repo
3. Install dependencies from requirements.txt
4. Run companion-app-plugin-party-pack-combo.py

## Use

### Using the Advanced Logo Analyzer

1. Open the browser extension settings and set MODE OF COMMERCIAL DETECTION to Logo Edge Mismatch
1. Click Save & Apply button

### Using the Plugin Party Pack

1. Open the browser extension settings and set MODE OF COMMERCIAL DETECTION and/or OVERLAY TYPE AND SOURCE to their respective plugin options
1. Set Plugin Type to Plugin Party Pack
1. Check which specific plugins you would like to enable
1. Scroll down to the very bottom to adjust plugin specific settings
1. Click Save & Apply button
