import logging
import random

logger = logging.getLogger(__name__)

# Try importing hardware libraries, use mocks if on Windows/unavailable
try:
    from gpiozero import DigitalInputDevice
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    logger.warning("gpiozero not available, using mock hardware")

class MockDevice:
    def __init__(self, pin):
        self.pin = pin
        self.is_active = False
        
    def read(self):
        # random toggle for testing
        if random.random() > 0.8:
            self.is_active = not self.is_active
        return self.is_active

class HardwareBridge:
    def __init__(self):
        self.devices = {}
        
    def setup_sensors(self, sensors_config):
        """Initialize hardware connections based on configuration."""
        self.devices.clear()
        for sensor in sensors_config:
            pin = sensor.get("pin")
            tag = sensor.get("tag_name")
            sensor_type = sensor.get("type", "gpio") # gpio, i2c, spi
            
            if sensor_type == "gpio":
                if GPIO_AVAILABLE:
                    # In real app, be careful about multiple setup on same pin
                    self.devices[tag] = DigitalInputDevice(pin)
                else:
                    self.devices[tag] = MockDevice(pin)
            else:
                # Add I2C/SPI mock later
                self.devices[tag] = MockDevice(pin)

    def read_all(self):
        """Read all configured sensors and return dict of {tag: value}"""
        results = {}
        for tag, device in self.devices.items():
            if GPIO_AVAILABLE and isinstance(device, DigitalInputDevice):
                results[tag] = device.is_active
            else:
                results[tag] = device.read()
        return results

hardware_bridge = HardwareBridge()
