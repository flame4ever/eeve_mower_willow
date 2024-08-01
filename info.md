# EEVE Mower Willow - Home Assistant Integration

This integration allows you to control and monitor your EEVE Willow lawn mower directly from Home Assistant. With this integration, you can track the mower's status, battery level, GPS location, and more. You can also send commands to start mowing, stop mowing, and return the mower to the docking station.

## Automation Examples

### Start mowing in the morning
```yaml
- alias: Mower - Start mowing in the morning
  id: 12345678-1234-1234-1234-123456789abc # Make this unique
  trigger:
    - platform: time
      at:
        - "08:00:00"
  action:
  - service: switch.turn_on
    target:
      entity_id: switch.willow_start_mowing
```

Send a message when mowing starts
```yaml
- alias: Mower - Notification when mowing starts
  id: 23456789-2345-2345-2345-234567890bcd # Make this unique
  trigger:
    - platform: state
      entity_id: sensor.willow_mowing_state # Change entities
      to: "mowing"
  action:
    - service: notify.mobile_app_your_phone_app # Change entities
      data:
        message: "🌿 Willow started mowing."
        data:
          url: "/lovelace-mower/mower"
          push:
            thread-id: "mower-group"
```

Send a message when the mower is done charging
```yaml
- alias: Mower - Notification when done charging
  id: 34567890-3456-3456-3456-345678901cde # Make this unique
  trigger:
    - platform: template
      value_template: "{{ states.sensor.willow_battery.state == 100 }}" # Change entities
  action:
    - service: notify.mobile_app_your_phone_app # Change entities
      data:
        message: "🔋 Willow is fully charged."
        data:
          url: "/lovelace-mower/mower"
          push:
            thread-id: "mower-group"
```

Send a message when there is an error while charging
```yaml
- alias: Mower - Notification when charging error occurs
  id: 45678901-4567-4567-4567-456789012def # Make this unique
  trigger:
    - platform: state
      entity_id: sensor.willow_charging_state # Change entities
      from: "charging"
      to: "error"
  action:
    - service: notify.mobile_app_your_phone_app # Change entities
      data:
        message: "🚨 Willow encountered an error while charging."
        data:
          url: "/lovelace-mower/mower"
          push:
            thread-id: "mower-group"
```

Send a message when the mower starts charging
```yaml
- alias: Mower - Notification when charging starts
  id: 56789012-5678-5678-5678-567890123ef0 # Make this unique
  trigger:
    - platform: state
      entity_id: sensor.willow_charging_state # Change entities
      to: "charging"
  action:
    - service: notify.mobile_app_your_phone_app # Change entities
      data:
        message: "⚡ Willow started charging."
        data:
          url: "/lovelace-mower/mower"
          push:
            thread-id: "mower-group"
```
Lovelace Examples
```yaml
type: vertical-stack
cards:
  - type: entities
    entities:
      - entity: sensor.willow_battery
        name: Battery Level
        icon: mdi:battery
      - entity: sensor.willow_mowing_state
        name: Mowing State
        icon: mdi:robot-mower
      - entity: sensor.willow_gps
        name: GPS Location
        icon: mdi:map-marker
    title: Mower Info
    header:
      type: picture
      image: /local/willow.jpg
      tap_action:
        action: none
      hold_action:
        action: none
  - type: horizontal-stack
    cards:
      - type: gauge
        entity: sensor.willow_battery
        min: 0
        max: 100
        name: Battery Level
        unit: '%'
        severity:
          green: 60
          yellow: 40
          red: 20
      - type: gauge
        entity: sensor.willow_mowing_speed
        min: 0
        max: 10
        name: Mowing Speed
        unit: 'km/h'
        severity:
          green: 5
          yellow: 3
          red: 1
```