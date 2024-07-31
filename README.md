# EEVE Mower Willow Integration for Home Assistant

![Integration Example](https://github.com/flame4ever/eeve_mower_willow/blob/main/Example.png)

This integration allows you to connect and control your EEVE Mower Willow directly from Home Assistant. By integrating your EEVE Mower Willow with Home Assistant, you can monitor its status, track its location, and control its operations remotely.

## Features

- **Battery Monitoring**: Check the current battery level of your mower.
- **Activity Tracking**: Monitor the current activity of your mower, including whether it's mowing, docking, or in the charging station.
- **Scheduler Status**: View the mower's scheduled activities.
- **GPS Tracking**: Track the mower's real-time location with latitude, longitude, and accuracy.
- **Network Information**: Get detailed information about the mower's network status, including WiFi signal strength, SSID, and connection status.
- **Mobile Network Status**: Monitor the mobile network status and reasons for disconnections.
- **Control Buttons**: Use buttons to reboot or stop the mower.
- **Switches**: Control the mower's operations, such as starting and stopping mowing, and sending the mower back to the dock.

## Installation

### Manual Installation

1. **Download the Integration**: Download the integration files from the GitHub repository.
2. **Add to Custom Components**: Place the downloaded files in the `custom_components/eeve_mower_willow` directory within your Home Assistant configuration directory.
3. **Configure Home Assistant**: Add the EEVE Mower Willow integration to your Home Assistant configuration.

### HACS Installation

1. **Open HACS**: Navigate to the Home Assistant Community Store (HACS) in your Home Assistant UI.
2. **Add Custom Repository**: Click on the three dots menu in the top right corner and select "Custom repositories".
3. **Enter Repository URL**: Add the following URL: `https://github.com/flame4ever/eeve_mower_willow` and select the category as "Integration".
4. **Install the Integration**: After adding the custom repository, search for "EEVE Mower Willow" in HACS and install it.
5. **Restart Home Assistant**: After installation, restart Home Assistant to apply the changes.

## Configuration

To configure the EEVE Mower Willow integration, follow these steps:

1. **Add the Integration**: Go to the Home Assistant UI and navigate to `Configuration` > `Integrations`. Click on the `+` button to add a new integration and search for "EEVE Mower Willow".
2. **Enter IP Address**: Enter the IP address of your EEVE Mower Willow and other required configuration details.
3. **Save and Restart**: Save the configuration and restart Home Assistant to apply the changes.

## Sensor Entities

The integration provides the following sensor entities:

- `sensor.<mower_name>_battery`: Battery level of the mower.
- `sensor.<mower_name>_activities`: Current activity of the mower.
- `sensor.<mower_name>_scheduler`: Scheduler status of the mower.
- `sensor.<mower_name>_gps`: GPS coordinates of the mower.
- `sensor.<mower_name>_network_state`: Network connection state of the mower.
- `sensor.<mower_name>_network_default`: Default network connection of the mower.
- `sensor.<mower_name>_network_mobile_reason`: Reason for mobile network disconnection.
- `sensor.<mower_name>_network_mobile_state`: State of the mobile network connection.
- `sensor.<mower_name>_network_wifi_local_ip`: Local IP address of the mower.
- `sensor.<mower_name>_network_wifi_reason`: Reason for WiFi disconnection.
- `sensor.<mower_name>_network_wifi_signal`: WiFi signal strength percentage.
- `sensor.<mower_name>_network_wifi_ssid`: SSID of the connected WiFi network.
- `sensor.<mower_name>_network_wifi_state`: State of the WiFi connection.

## Control Entities

The integration also provides control entities:

- `button.reboot_mower`: Reboot the mower.
- `button.stop_mower`: Stop the mower's current operation.
- `switch.start_mowing`: Start mowing operation.
- `switch.dock_mower`: Send the mower back to the docking station.

## Contributing

Contributions are welcome! If you find any issues or have suggestions for improvements, please open an issue or submit a pull request on GitHub.

## License

This project is licensed under the GNU General Public License. See the [LICENSE](LICENSE) file for details.

## Support

For support and questions, please open an issue on the GitHub repository.

---

By integrating your EEVE Mower Willow with Home Assistant, you can enhance your smart home setup and enjoy seamless control and monitoring of your mower from a single interface.
