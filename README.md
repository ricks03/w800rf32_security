# W800RF32 Security

Custom Home Assistant integration that extends the standard w800rf32 component to support both:
- **Standard X10 devices** (motion sensors, keypads, switches)
- **DS10A security sensors** (door/window sensors with battery monitoring)

## Installation

1. Copy this folder to `/config/custom_components/w800rf32_security/`
2. Restart Home Assistant
3. Add configuration to `configuration.yaml`

## Configuration

```yaml
w800rf32_security:
  device: /dev/ttyUSB0    # Your W800RF32 serial device

binary_sensor:
  - platform: w800rf32_security
    devices:
      # X10 motion sensor
      a1:
        name: motion_hall
        device_type: x10              # Required: "x10" or "security"
        device_class: motion
        off_delay:
          seconds: 5
      
      # X10 motion sensor
      c3:
        name: motion_kitchen
        device_type: x10
        device_class: motion
      
      # DS10A door sensor
      5a:
        name: bedroom_door
        device_type: security         # Required: "x10" or "security"
        device_class: door
      
      # DS10A window sensor
      3f:
        name: front_window
        device_type: security
        device_class: window
```

### Required Configuration Fields

For each device you MUST specify:
- `name` - Friendly name
- `device_type` - Either `x10` or `security`

Optional fields:
- `device_class` - Type of sensor (motion, door, window, etc.)
- `off_delay` - Auto-off delay (useful for motion sensors)

### Why device_type is Required

Some addresses like `a1`, `c3`, `f5` could be either X10 or security sensors. By explicitly specifying the type, there's no ambiguity.

## Device Types

### X10 Devices (`device_type: x10`)

**Address format:** House code (a-p) + unit number (1-16)
- Examples: `a1`, `c3`, `p16`
- Supported: Motion sensors, keypads, remotes, switches
- Events: On/Off commands

### Security Sensors (`device_type: security`)

**Address format:** 2-digit hexadecimal (00-ff)
- Examples: `5a`, `3f`, `a1` (yes, same as X10 address!)
- Supported: DS10A door/window sensors
- Events: Open/closed with battery status

**Security sensor attributes:**
- `low_battery` - Boolean indicating if battery is low
- `min_delay` - Boolean indicating minimum delay mode
- `last_update` - ISO timestamp of last update

## Example Automations

### Low Battery Alert

```yaml
automation:
  - id: ds10a_low_battery_alert
    alias: "Door Sensor Low Battery Alert"
    trigger:
      platform: state
      entity_id:
        - binary_sensor.bedroom_door
        - binary_sensor.front_window
      attribute: low_battery
      to: true
    action:
      - service: notify.notify
        data:
          title: "Door Sensor Low Battery"
          message: "{{ trigger.to_state.name }} needs a battery replacement!"
```

### Door Open Notification

```yaml
automation:
  - id: door_opened
    alias: "Bedroom Door Opened"
    trigger:
      platform: state
      entity_id: binary_sensor.bedroom_door
      to: 'on'
    action:
      - service: notify.notify
        data:
          message: "Bedroom door was opened"
```

## Troubleshooting

### Enable Debug Logging

Add to `configuration.yaml`:
```yaml
logger:
  default: info
  logs:
    custom_components.w800rf32_security: debug
    W800rf32: debug
```

This shows:
- Raw packet data in hex
- Security sensor detection
- X10 event parsing
- Event dispatching

### Finding Device Addresses

**For X10 devices:**
- Set on the device (usually DIP switches or dial)
- Format: House code (A-P) + Unit (1-16)

**For DS10A sensors:**
- Enable debug logging
- Trigger the sensor (open/close)
- Look for log entry like:
  ```
  RAW PACKET: 5a3f8001
  Security event: {'device_type': 'ds10a', 'address': '5a', ...}
  ```
- Use the `address` value in your config

### Common Issues

**Component doesn't load:**
- Verify files are in `/config/custom_components/w800rf32_security/`
- Check serial device path (`/dev/ttyUSB0` or similar)
- Check logs for errors

**X10 devices not responding:**
- Verify `device_type: x10` is set
- Check address format (e.g., `a1`, not `A1` or `1a`)
- Enable debug logging to see received packets

**Security sensors not responding:**
- Verify `device_type: security` is set
- Check address is 2-digit hex (e.g., `5a`, `3f`)
- Trigger sensor and check debug logs
- Verify address matches configuration

## Technical Details

This integration:
1. Opens the W800RF32 serial connection directly
2. Intercepts raw 4-byte packets
3. Checks if packet is security sensor (using upper nibble matching)
4. Routes security packets to custom parser
5. Routes standard X10 packets to the W800rf32 library
6. Dispatches events to appropriate binary sensor entities

The integration uses the proven `pyW800rf32` library for X10 parsing (same as Home Assistant core) while adding DS10A security sensor support on top.
