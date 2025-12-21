"""Support for w800rf32 devices with security sensor support."""

import logging

import voluptuous as vol

from homeassistant.const import (
    CONF_DEVICE,
    EVENT_HOMEASSISTANT_START,
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import dispatcher_send
from homeassistant.helpers.typing import ConfigType

DATA_W800RF32 = "data_w800rf32"
DOMAIN = "w800rf32_security"

# Signal names for event dispatching
W800RF32_DEVICE = "w800rf32_{}"  # For standard X10 devices
SIGNAL_SECURITY_EVENT = f"{DOMAIN}_security"  # For security sensors

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: vol.Schema({vol.Required(CONF_DEVICE): cv.string})}, extra=vol.ALLOW_EXTRA
)


class SecuritySensorParser:
    """Parser for X10 security devices (DS10A, KR10A, etc.)"""
    
    @staticmethod
    def is_security_packet(data):
        """Check if packet is from a security sensor."""
        if len(data) != 4:
            return False
        
        upper_nibble_0 = (data[0] >> 4) & 0x0F
        upper_nibble_1 = (data[1] >> 4) & 0x0F
        
        return upper_nibble_0 == upper_nibble_1
    
    @staticmethod
    def parse(data):
        """Parse security sensor packet."""
        if not SecuritySensorParser.is_security_packet(data):
            return None
        
        # Validate DS10A function byte - only bits 0, 2, 7 allowed (mask 0x85)
        if data[2] & ~0x85:
            return None

        address = ((data[0] & 0x0F) << 4) | (data[1] & 0x0F)
        low_battery = bool(data[2] & 0x01)
        min_delay = not bool(data[2] & 0x10) # FIXED: was data[1] & 0x10
        byte2 = data[2]
        
        if byte2 & 0x80:
            contact_state = "closed"
        else:
            contact_state = "open"
        
        return {
            "device_type": "ds10a",
            "address": "{:02x}".format(address),
            "state": contact_state,
            "low_battery": low_battery,
            "min_delay": min_delay
        }


class X10Event:
    """X10 Event class - implements exact parsing from pyW800rf32 library.
    
    This is copied directly from pyW800rf32/lowlevel.py to ensure
    compatibility with the original library's X10 parsing.
    """
    
    # House code lookup table from pyW800rf32
    hcodeDict = {
        0b0110: 'A', 0b1110: 'B', 0b0010: 'C', 0b1010: 'D',
        0b0001: 'E', 0b1001: 'F', 0b0101: 'G', 0b1101: 'H',
        0b0111: 'I', 0b1111: 'J', 0b0011: 'K', 0b1011: 'L',
        0b0000: 'M', 0b1000: 'N', 0b0100: 'O', 0b1100: 'P'
    }
    
    def __init__(self, data):
        """Initialize from 4-byte packet using pyW800rf32 parsing logic."""
        if len(data) != 4:
            raise ValueError("X10 packet must be 4 bytes")
        
        # Validate packet (from pyW800rf32 parse function)
        if data[0] + data[1] != 0xFF or data[2] + data[3] != 0xFF:
            raise ValueError("Invalid X10 packet - checksum failed")
        
        # Parse using exact logic from pyW800rf32 DecodeW800Packet class
        self.device = None
        self.command = None
        self.data = data
        self._get_x10code_and_cmd(data)
    
    def _get_x10code_and_cmd(self, data):
        """Parse X10 code and command - copied from pyW800rf32 lowlevel.py"""
        xb3 = "{0:08b}".format(data[0])  # format binary string
        b3 = int(xb3[::-1], 2)  # reverse the string and assign to byte 3
        xb1 = "{0:08b}".format(data[2])  # format binary string
        b1 = int(xb1[::-1], 2)  # reverse the string and assign to byte 1
        
        # Get the house code
        house_code = self.hcodeDict[b3 & 0x0f]
        
        # Next find unit number
        x = b1 >> 3
        x1 = (b1 & 0x02) << 1
        y = (b3 & 0x20) >> 2
        unit_number = x + x1 + y + 1
        
        # Find command
        # 0x19 and 0x11 map to dim and bright but we don't support dim and
        # bright here. 0x11 and 0x19 will not map correctly on all keypads.
        # 4 unit keypads such as RSS18 will work but 5 unit kepads with
        # DIM./BRIGHT keys will not be supported.
        if b1 == 0x19:
            self.command = 'Off'
        elif b1 == 0x11:
            self.command = 'On'
            unit_number += 1
        elif b1 & 0x05 == 4:
            self.command = 'Off'
        elif b1 & 0x05 == 0:
            self.command = 'On'
        
        self.device = "{0}{1}".format(house_code, unit_number)


def setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the w800rf32_security component."""
    
    import serial
    import threading
    
    security_parser = SecuritySensorParser()
    device = config[DOMAIN][CONF_DEVICE]
    
    # State tracking
    connection_state = {
        'serial': None,
        'thread': None,
        'running': False
    }
    
    def read_loop():
        """Read and parse packets from W800RF32."""
        while connection_state['running']:
            try:
                # Read 4-byte packet
                data = connection_state['serial'].read(4)
                if len(data) != 4:
                    continue
                
                _LOGGER.debug("RAW PACKET: %s", data.hex())
                
                # Try security sensor first
                security_event = security_parser.parse(data)
                if security_event:
                    _LOGGER.debug("Security sensor detected: %s", security_event)
                    dispatcher_send(hass, SIGNAL_SECURITY_EVENT, security_event)
                    continue
                
                # Try X10 parsing
                try:
                    x10_event = X10Event(data)
                    _LOGGER.debug(
                        "Standard X10 event for device: %s, command: %s",
                        x10_event.device,
                        x10_event.command
                    )
                    
                    # Dispatch to appropriate device
                    device_id = x10_event.device.lower()
                    signal = W800RF32_DEVICE.format(device_id)
                    dispatcher_send(hass, signal, x10_event)
                    
                except ValueError as err:
                    _LOGGER.debug("Not a valid X10 or security packet: %s", err)
                    
            except serial.SerialException as err:
                _LOGGER.error("Serial error: %s", err)
                break
            except Exception as err:
                _LOGGER.error("Unexpected error in read loop: %s", err)
    
    def start_connection(event):
        """Start the W800RF32 connection."""
        try:
            connection_state['serial'] = serial.Serial(
                port=device,
                baudrate=4800,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                xonxoff=False,
                timeout=1
            )
            connection_state['running'] = True
            connection_state['thread'] = threading.Thread(target=read_loop, daemon=True)
            connection_state['thread'].start()
            _LOGGER.info("W800RF32 Security started on %s", device)
        except Exception as err:
            _LOGGER.error("Failed to connect to %s: %s", device, err)
    
    def stop_connection(event):
        """Stop the W800RF32 connection."""
        connection_state['running'] = False
        if connection_state['thread'] and connection_state['thread'].is_alive():
            connection_state['thread'].join(timeout=2)
        if connection_state['serial'] and connection_state['serial'].is_open:
            connection_state['serial'].close()
        _LOGGER.info("W800RF32 Security connection closed")
    
    hass.bus.listen_once(EVENT_HOMEASSISTANT_START, start_connection)
    hass.bus.listen_once(EVENT_HOMEASSISTANT_STOP, stop_connection)
    
    hass.data[DATA_W800RF32] = connection_state
    
    return True
