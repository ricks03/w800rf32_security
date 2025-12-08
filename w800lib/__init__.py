"""
W800RF32 library with security sensor support
Embedded in custom component for HAOS compatibility
"""
import serial
import threading
import logging
from .security_parser import SecuritySensorParser

_LOGGER = logging.getLogger(__name__)


class W800rf32:
    """W800RF32 receiver with security sensor support."""
    
    def __init__(self, device, event_callback=None):
        """Initialize the W800RF32 receiver."""
        self.device = device
        self.event_callback = event_callback
        self._serial = None
        self._running = False
        self._thread = None
        self.security_parser = SecuritySensorParser()
    
    def _process_packet(self, data):
        """Process a 4-byte packet."""
        if len(data) != 4:
            return None
        
        # Try parsing as security sensor first
        security_event = self.security_parser.parse(data)
        if security_event:
            _LOGGER.debug("Security event: %s", security_event)
            return security_event
        
        # Fall back to standard X10 parsing
        return self._parse_standard_x10(data)
    
    def _parse_standard_x10(self, data):
        """Parse standard X10 packet."""
        byte0, byte1, byte2, byte3 = data
        
        # Validate packet (byte1 should be inverse of byte0, byte3 inverse of byte2)
        if byte0 != (byte1 ^ 0xFF) or byte2 != (byte3 ^ 0xFF):
            return None
        
        # Extract house code (A-P from upper nibble of byte0)
        house_code = chr(65 + ((byte0 & 0xF0) >> 4))
        
        # Extract unit (1-16 from lower nibble of byte0)
        unit = (byte0 & 0x0F)
        
        # Determine command from byte2
        # Standard X10 command structure
        if byte2 & 0x20:  # Function code
            if byte2 & 0x10:  # Bright
                command = 'bright'
            else:  # Dim
                command = 'dim'
            unit = None  # Dim/bright don't have unit
        else:
            # Unit code command
            if byte2 & 0x08:  # On
                command = 'on'
            else:  # Off
                command = 'off'
            unit = unit + 1  # Make 1-indexed
        
        result = {
            'device_type': 'x10',
            'house_code': house_code,
            'command': command
        }
        
        if unit is not None:
            result['unit'] = unit
        
        _LOGGER.debug("Standard X10 event: %s", result)
        return result
    
    def _read_loop(self):
        """Main read loop."""
        while self._running:
            try:
                data = self._serial.read(4)
                if len(data) == 4:
                    # LOG EVERY PACKET IN HEX
                    _LOGGER.debug("RAW PACKET: %s", data.hex())
                    event = self._process_packet(data)
                    if event and self.event_callback:
                        self.event_callback(event)
            except serial.SerialException as err:
                _LOGGER.error("Serial error: %s", err)
                break
            except Exception as err:
                _LOGGER.error("Unexpected error: %s", err)
                break
    
    def connect(self):
        """Connect to the W800RF32 device."""
        try:
            self._serial = serial.Serial(
                port=self.device,
                baudrate=4800,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                xonxoff=False,
                timeout=1
            )
            self._running = True
            self._thread = threading.Thread(target=self._read_loop, daemon=True)
            self._thread.start()
            _LOGGER.info("Connected to W800RF32 on %s", self.device)
            return True
        except Exception as err:
            _LOGGER.error("Failed to connect to %s: %s", self.device, err)
            return False
    
    def disconnect(self):
        """Disconnect from device."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        if self._serial and self._serial.is_open:
            self._serial.close()
        _LOGGER.info("Disconnected from W800RF32")
