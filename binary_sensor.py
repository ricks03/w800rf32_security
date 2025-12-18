"""Support for w800rf32 binary sensors with security sensor support."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.components.binary_sensor import (
    DEVICE_CLASSES_SCHEMA,
    PLATFORM_SCHEMA as BINARY_SENSOR_PLATFORM_SCHEMA,
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import CONF_DEVICE_CLASS, CONF_DEVICES, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, event as evt
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.util import dt as dt_util

from . import W800RF32_DEVICE, SIGNAL_SECURITY_EVENT

_LOGGER = logging.getLogger(__name__)

CONF_OFF_DELAY = "off_delay"
CONF_DEVICE_TYPE = "device_type"

DEVICE_TYPE_X10 = "x10"
DEVICE_TYPE_SECURITY = "security"

# Define the device schema
DEVICE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_DEVICE_TYPE): vol.In([DEVICE_TYPE_X10, DEVICE_TYPE_SECURITY]),
        vol.Optional(CONF_DEVICE_CLASS): DEVICE_CLASSES_SCHEMA,
        vol.Optional(CONF_OFF_DELAY): vol.All(
            cv.time_period, cv.positive_timedelta
        ),
    }
)

PLATFORM_SCHEMA = BINARY_SENSOR_PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_DEVICES): {cv.string: DEVICE_SCHEMA}
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the Binary Sensor platform to w800rf32."""
    binary_sensors = []
    
    # device_id --> "c1 or a3" X10 device OR "5a" security sensor
    # entity --> name, device_class, device_type, etc
    for device_id, entity in config[CONF_DEVICES].items():
        device_id_lower = device_id.lower()
        device_type = entity[CONF_DEVICE_TYPE]
        
        # Create appropriate sensor based on device_type
        if device_type == DEVICE_TYPE_SECURITY:
            _LOGGER.debug(
                "Add %s w800rf32_security.binary_sensor SECURITY (address: %s, class %s)",
                entity[CONF_NAME],
                device_id_lower,
                entity.get(CONF_DEVICE_CLASS),
            )
            device = W800SecuritySensor(
                device_id_lower,
                entity[CONF_NAME],
                entity.get(CONF_DEVICE_CLASS),
                entity.get(CONF_OFF_DELAY),
            )
        elif device_type == DEVICE_TYPE_X10:
            _LOGGER.debug(
                "Add %s w800rf32_security.binary_sensor X10 (address: %s, class %s)",
                entity[CONF_NAME],
                device_id_lower,
                entity.get(CONF_DEVICE_CLASS),
            )
            device = W800rf32BinarySensor(
                device_id_lower,
                entity[CONF_NAME],
                entity.get(CONF_DEVICE_CLASS),
                entity.get(CONF_OFF_DELAY),
            )
        else:
            _LOGGER.error(
                "Unknown device_type '%s' for %s - skipping",
                device_type,
                entity[CONF_NAME],
            )
            continue

        binary_sensors.append(device)

    add_entities(binary_sensors)


class W800rf32BinarySensor(BinarySensorEntity):
    """A representation of a w800rf32 binary sensor (standard X10)."""

    _attr_should_poll = False

    def __init__(self, device_id, name, device_class=None, off_delay=None):
        """Initialize the w800rf32 sensor."""
        self._signal = W800RF32_DEVICE.format(device_id)
        self._name = name
        self._device_class = device_class
        self._off_delay = off_delay
        self._state = False
        self._delay_listener = None

    @callback
    def _off_delay_listener(self, now):
        """Switch device off after a delay."""
        self._delay_listener = None
        self.update_state(False)

    @property
    def name(self):
        """Return the device name."""
        return self._name

    @property
    def device_class(self):
        """Return the sensor class."""
        return self._device_class

    @property
    def is_on(self):
        """Return true if the sensor state is True."""
        return self._state

    @callback
    def binary_sensor_update(self, event):
        """Call for control updates from the w800rf32 gateway."""

        # Check if event has the required attributes (our X10Event class)
        if not hasattr(event, 'device') or not hasattr(event, 'command'):
            return

        dev_id = event.device
        command = event.command

        _LOGGER.debug(
            "BinarySensor update (Device ID: %s Command %s ...)", dev_id, command
        )

        # Update the w800rf32 device state
        if command in ("On", "Off"):
            is_on = command == "On"
            self.update_state(is_on)

        if self.is_on and self._off_delay is not None and self._delay_listener is None:
            self._delay_listener = evt.async_call_later(
                self.hass, self._off_delay, self._off_delay_listener
            )

    def update_state(self, state):
        """Update the state of the device."""
        self._state = state
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Register update callback."""
        async_dispatcher_connect(self.hass, self._signal, self.binary_sensor_update)


class W800SecuritySensor(BinarySensorEntity):
    """A representation of a DS10A security sensor."""

    _attr_should_poll = False

    def __init__(self, address, name, device_class=None, off_delay=None):
        """Initialize the security sensor."""
        self._address = address
        self._attr_name = name
        self._attr_device_class = device_class or BinarySensorDeviceClass.DOOR
        self._off_delay = off_delay
        self._attr_is_on = False
        self._attr_extra_state_attributes = {}
        self._delay_listener = None

    @callback
    def _handle_event(self, event):
        """Handle security sensor event."""
        # Check if this event is for our sensor
        if event.get("device_type") != "ds10a":
            return
            
        if event.get("address") != self._address:
            return

        _LOGGER.debug(
            "Security sensor update (Address: %s State: %s)", 
            self._address, 
            event.get("state")
        )

        # Update state
        state = event.get("state")
        self._attr_is_on = (state == "open")

        # Update attributes
        self._attr_extra_state_attributes = {
            "low_battery": event.get("low_battery", False),
            "min_delay": event.get("min_delay", False),
            "last_update": dt_util.utcnow().isoformat(),
        }

        # Handle off_delay
        if self._attr_is_on:
            self._schedule_off_delay()
        else:
            self._cancel_off_delay()

        self.async_write_ha_state()

    def _schedule_off_delay(self):
        """Schedule automatic off."""
        self._cancel_off_delay()

        if self._off_delay:
            @callback
            def turn_off(now):
                self._attr_is_on = False
                self._delay_listener = None
                self.async_write_ha_state()

            self._delay_listener = evt.async_call_later(
                self.hass, self._off_delay, turn_off
            )

    def _cancel_off_delay(self):
        """Cancel off delay."""
        if self._delay_listener:
            self._delay_listener()
            self._delay_listener = None

    async def async_added_to_hass(self) -> None:
        """Register update callback."""
        async_dispatcher_connect(self.hass, SIGNAL_SECURITY_EVENT, self._handle_event)
