"""W800RF32 with security sensor support."""
import logging
import voluptuous as vol

from homeassistant.const import CONF_DEVICE, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.dispatcher import dispatcher_send
from homeassistant.helpers.typing import ConfigType

_LOGGER = logging.getLogger(__name__)

DOMAIN = "w800rf32_security"
DATA_W800 = "w800rf32_data"

# Dispatcher signal names
SIGNAL_STANDARD_EVENT = f"{DOMAIN}_standard"
SIGNAL_SECURITY_EVENT = f"{DOMAIN}_security"

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema({
            vol.Required(CONF_DEVICE): cv.string,
        })
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the W800RF32 Security component."""
    from .w800lib import W800rf32
    
    conf = config[DOMAIN]
    device = conf[CONF_DEVICE]
    
    def event_callback(event):
        """Handle events from W800RF32."""
        device_type = event.get('device_type')
        
        if device_type in ['ds10a', 'kr10a']:
            _LOGGER.debug("Security event received: %s", event)
            dispatcher_send(hass, SIGNAL_SECURITY_EVENT, event)
        elif device_type == 'x10':
            _LOGGER.debug("Standard X10 event received: %s", event)
            dispatcher_send(hass, SIGNAL_STANDARD_EVENT, event)
    
    # Create receiver instance
    w800 = W800rf32(device, event_callback=event_callback)
    
    # Connect in executor to avoid blocking
    connected = await hass.async_add_executor_job(w800.connect)
    
    if not connected:
        _LOGGER.error("Failed to connect to W800RF32 on %s", device)
        return False
    
    # Store instance
    hass.data[DATA_W800] = w800
    
    async def async_stop(event):
        """Cleanup on shutdown."""
        await hass.async_add_executor_job(w800.disconnect)
    
    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, async_stop)
    
    _LOGGER.info("W800RF32 Security component loaded on %s", device)
    return True
