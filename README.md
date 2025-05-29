# RYSE HomeAssistant component
A full-featured Homeassistant component to drive RYSE BLE devices.

> This is a fork of the original [RYSE Home Assistant integration](https://github.com/mohamedkallel82/ryse) by [@mohamedkallel82](https://github.com/mohamedkallel82), with added support for Bluetooth proxies and HACS installation.

## What's Different in This Fork?

This fork adds several improvements to the original integration:

1. **Bluetooth Proxy Support**
   - Works with Home Assistant's Bluetooth proxy system
   - Automatically uses proxy when available
   - Maintains compatibility with direct Bluetooth connections
   - Better device tracking and unavailability handling

2. **HACS Integration**
   - Easy installation through HACS
   - Automatic updates
   - Better integration with Home Assistant ecosystem

3. **Code Improvements**
   - Updated Bluetooth implementation using Home Assistant's native Bluetooth APIs
   - Better error handling and logging
   - Improved device state management

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
Download the RYSE home Assistant component from: https://github.com/mohamedkallel82/ryse/archive/refs/heads/main.zip

Unzip it and then copy the folder `custom_components/ryse`  to your HomeAssistant under `/homeassistant/custom_components`.

the tree in your Home Assistant should be be like the following:


    /homeassistant
        └── custom_components
            └── ryse
                └── __init__.py
                └── bluetooth.py
                └── cover.py
                └── ...

## Usage
Reboot your home assistant and now you can play with RYSE BLE devices via your Home Assistant.

The following video show how to pair a RYSE BLE device with home assistant: 

[![Watch the video](https://img.youtube.com/vi/G24vZGYZ-_o/0.jpg)](https://youtu.be/G24vZGYZ-_o)

## Bluetooth Proxy Support
This integration now supports Home Assistant's Bluetooth proxy system. To use it:

1. Make sure you have a Bluetooth proxy set up in your Home Assistant instance
2. The integration will automatically use the proxy when available
3. No additional configuration is needed - the integration will work with both direct Bluetooth connections and proxies
