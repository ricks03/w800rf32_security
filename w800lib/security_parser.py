"""
Security sensor parser for W800RF32
"""
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
        
        address = ((data[0] & 0x0F) << 4) | (data[1] & 0x0F)
        low_battery = bool(data[2] & 0x01)
        min_delay = not bool(data[1] & 0x10)
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
