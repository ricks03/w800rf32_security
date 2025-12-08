Modification of the w800rf32 code in HomeAssistant 2025.12.1 to go into /config/custom_components/w800rf32_security (to override the code in core)

platform: w800rf32_security
devices:
5a:
name: bedroom_door
device_class: door

automation:

id: ds10a_low_battery_alert
alias: "DS10A Door Sensor Low Battery Alert"
description: "Alert when any door sensor has low battery"
trigger:
platform: state
entity_id:
binary_sensor.bedroom_door
attribute: low_battery
to: true
action:
service: persistent_notification.create
data:
title: "Door Sensor Low Battery"
message: "{{ trigger.to_state.name }} needs a battery replacement!"
service: notify.notify # Change to your notification service
data:
title: "Door Sensor Low Battery"
message: "{{ trigger.to_state.name }} battery is low"
template:

sensor:
name: "DS10A Low Battery Count"
state: >
{% set sensors = [
'binary_sensor.bedroom_door',
] %}
{{ sensors | select('state_attr', 'low_battery', true) | list | count }}
attributes:
low_battery_sensors: >
{% set sensors = [
'binary_sensor.bedroom_door',
] %}
{{ sensors | select('state_attr', 'low_battery', true) | map('state_attr', 'friendly_name') | list | join(', ') }}
