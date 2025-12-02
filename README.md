# Advanced Logo Analyzer Companion Desktop Tray Application

This is a lightweight Python app that runs in the system tray and provides a local server (on `localhost:64143`) for the browser extension to communicate with.

## Features

- Detects network logos on your screen using edge-based computer vision
- Runs entirely offline (no data ever leaves your computer)
- Designed to be used alongside the Chrome or Firefox extension

## Setup

### Option 1: Install from exe

Download the latest Advanced Logo Analyzer release from the [Releases tab](https://github.com/RG-O/YoutubeOverCommercials/releases) and run to install the application. After installation, run the application and it will appear in your system tray.

### Option 2 (Advanced): Run from Python

1. Install Python 3.9+
2. Install dependencies: pip install -r requirements.txt
3. Run: advanced_logo_analyzer.py