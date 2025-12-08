"""Binary sensor platform for W800RF32 with security support."""
import logging
from datetime import timedelta

import voluptuous as vol

from homeassistant.components.binary_sensor import (
    PLATFORM_SCHEMA,
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import CONF_DEVICE_CLASS, CONF_DEVICES, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.util import dt as dt_util

from . import SIGNAL_SECURITY_EVENT, SIGNAL_STANDARD_EVENT

_LOGGER = logging.getLogger(__name__)

CONF_OFF_DELAY = "off_delay"

DEVICE_SCHEMA = vol.Schema({
    vol.Required(CONF_NAME): cv.string,
    vol.Optional(CONF_DEVICE_CLASS): cv.string,
    vol.Optional(CONF_OFF_DELAY): cv.positive_time_period,
})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_DEVICES): {cv.string: DEVICE_SCHEMA}
})


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up W800RF32 binary sensors."""
    sensors = []
    
    for address, device_config in config[CONF_DEVICES].items():
        # Check if hex address (security sensor) or alphanumeric (standard X10)
        if _is_hex_address(address):
            sensors.append(
                W800SecuritySensor(
                    address.lower(),
                    device_config[CONF_NAME],
                    device_config.get(CONF_DEVICE_CLASS),
                    device_config.get(CONF_OFF_DELAY),
                )
            )
        else:
            sensors.append(
                W800StandardSensor(
                    address.lower(),
                    device_config[CONF_NAME],
                    device_config.get(CONF_DEVICE_CLASS),
                    device_config.get(CONF_OFF_DELAY),
                )
            )
    
    async_add_entities(sensors)


def _is_hex_address(address: str) -> bool:
    """Check if address is hex format (security sensor)."""
    try:
        int(address, 16)
        return len(address) == 2
    except ValueError:
        return False


class W800StandardSensor(BinarySensorEntity):
    """Standard X10 binary sensor."""
    
    def __init__(self, address, name, device_class, off_delay):
        """Initialize sensor."""
        self._address = address
        self._attr_name = name
        self._attr_device_class = device_class
        self._off_delay = off_delay
        self._attr_is_on = False
        self._off_delay_listener = None
    
    async def async_added_to_hass(self):
        """Subscribe to events."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_STANDARD_EVENT, self._handle_event
            )
        )
    
    @callback
    def _handle_event(self, event):
        """Handle X10 event."""
        house_code = event.get('house_code', '').lower()
        unit = event.get('unit')
        
        # Build address string
        if unit:
            event_address = f"{house_code}{unit}"
        else:
            event_address = house_code
        
        if event_address != self._address:
            return
        
        command = event.get('command')
        
        if command == 'on':
            self._attr_is_on = True
            self._schedule_off_delay()
        elif command == 'off':
            self._attr_is_on = False
            self._cancel_off_delay()
        
        self.async_write_ha_state()
    
    def _schedule_off_delay(self):
        """Schedule automatic off."""
        self._cancel_off_delay()
        
        if self._off_delay:
            @callback
            def turn_off(now):
                self._attr_is_on = False
                self._off_delay_listener = None
                self.async_write_ha_state()
            
            self._off_delay_listener = async_call_later(
                self.hass, self._off_delay.total_seconds(), turn_off
            )
    
    def _cancel_off_delay(self):
        """Cancel off delay."""
        if self._off_delay_listener:
            self._off_delay_listener()
            self._off_delay_listener = None


class W800SecuritySensor(BinarySensorEntity):
    """Security sensor (DS10A)."""
    
    def __init__(self, address, name, device_class, off_delay):
        """Initialize sensor."""
        self._address = address
        self._attr_name = name
        self._attr_device_class = device_class or BinarySensorDeviceClass.DOOR
        self._off_delay = off_delay
        self._attr_is_on = False
        self._attr_extra_state_attributes = {}
        self._off_delay_listener = None
    
    async def async_added_to_hass(self):
        """Subscribe to events."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_SECURITY_EVENT, self._handle_event
            )
        )
    
    @callback
    def _handle_event(self, event):
        """Handle security event."""
        if event.get('device_type') != 'ds10a':
            return
        
        if event.get('address') != self._address:
            return
        
        # Update state
        state = event.get('state')
        self._attr_is_on = (state == 'open')
        
        # Update attributes
        self._attr_extra_state_attributes = {
            'low_battery': event.get('low_battery', False),
            'min_delay': event.get('min_delay', False),
            'last_update': dt_util.utcnow().isoformat(),
        }
        
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
                self._off_delay_listener = None
                self.async_write_ha_state()
            
            self._off_delay_listener = async_call_later(
                self.hass, self._off_delay.total_seconds(), turn_off
            )
    
    def _cancel_off_delay(self):
        """Cancel off delay."""
        if self._off_delay_listener:
            self._off_delay_listener()
            self._off_delay_listener = None
