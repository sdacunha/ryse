# RYSE Home Assistant Integration

This is a complete rewrite of the RYSE Home Assistant integration, inspired by [@mohamedkallel82](https://github.com/mohamedkallel82). This version is built from the ground up for reliability, modern Home Assistant best practices, and robust Bluetooth support (including Bluetooth proxies).

## Features
- Real time updates for position and state
- Works with ESPHome Bluetooth proxies and direct connections
- Easy pairing and setup from the Home Assistant UI
- Battery status

## Installation

### HACS Installation (Recommended)
1. Make sure you have [HACS](https://hacs.xyz/) installed
2. Add this repository to HACS:
   - Go to HACS > Integrations
   - Click the three dots in the top right
   - Click "Custom repositories"
   - Add `https://github.com/sdacunha/ryse` as a repository
   - Select "Integration" as the category
3. Click the "Download" button for the RYSE integration
4. Restart Home Assistant

### Manual Installation
Download the RYSE Home Assistant component from: https://github.com/sdacunha/ryse/archive/refs/heads/main.zip

Unzip it and then copy the folder `custom_components/ryse` to your Home Assistant under `/homeassistant/custom_components`.

The tree in your Home Assistant should look like this:

    /homeassistant
        └── custom_components
            └── ryse
                └── __init__.py
                └── ...

Reboot your Home Assistant instance and you can now pair your RYSE SmartShades.

## Support & Feedback
If you have questions, suggestions, or want to contribute, please open an issue or pull request on GitHub! My time is limited, so I will do my best to respond to issues and pull requests, I mostly created this integration for my own use.

## TODO
- [ ] Detect if blinds need calibration
- [ ] Add ability to set speed

## Credits
- Inspired by the original [RYSE Home Assistant integration](https://github.com/mohamedkallel82/ryse) by [@mohamedkallel82](https://github.com/mohamedkallel82).
