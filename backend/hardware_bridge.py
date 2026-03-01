import logging
import random

logger = logging.getLogger(__name__)

# Try importing hardware libraries, use mocks if on Windows/unavailable
try:
    from gpiozero import DigitalInputDevice, DigitalOutputDevice
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    logger.warning("gpiozero not available, using mock hardware")

class MockInputDevice:
    def __init__(self, gpio):
        self.gpio = gpio
        self.is_active = False
        
    def read(self):
        # random toggle for testing
        if random.random() > 0.8:
            self.is_active = not self.is_active
        return self.is_active

class MockOutputDevice:
    def __init__(self, gpio):
        self.gpio = gpio
        self.is_active = False

    def on(self):
        self.is_active = True

    def off(self):
        self.is_active = False

    @property
    def value(self):
        return 1 if self.is_active else 0

class HardwareBridge:
    def __init__(self):
        self.devices = {}       # tag -> device instance
        self.directions = {}    # tag -> "input" | "output"
        
    def setup_sensors(self, sensors_config):
        """Initialize hardware connections based on configuration."""
        self.devices.clear()
        self.directions.clear()
        for sensor in sensors_config:
            gpio = sensor.get("gpio")
            tag = sensor.get("tag_name")
            sensor_type = sensor.get("type", "gpio")
            direction = sensor.get("direction", "input")
            
            self.directions[tag] = direction
            
            if sensor_type == "gpio":
                if GPIO_AVAILABLE:
                    if direction == "output":
                        self.devices[tag] = DigitalOutputDevice(gpio)
                    else:
                        self.devices[tag] = DigitalInputDevice(gpio)
                else:
                    if direction == "output":
                        self.devices[tag] = MockOutputDevice(gpio)
                    else:
                        self.devices[tag] = MockInputDevice(gpio)
            else:
                # I2C/SPI — mock for now
                self.devices[tag] = MockInputDevice(gpio)

    def read_all(self):
        """Read all configured sensors and return dict of {tag: value}"""
        results = {}
        for tag, device in self.devices.items():
            if self.directions.get(tag) == "output":
                # Read back the current output state
                if GPIO_AVAILABLE and isinstance(device, DigitalOutputDevice):
                    results[tag] = bool(device.value)
                else:
                    results[tag] = device.is_active
            else:
                if GPIO_AVAILABLE and isinstance(device, DigitalInputDevice):
                    results[tag] = device.is_active
                else:
                    results[tag] = device.read()
        return results

    def write(self, tag, value):
        """Write a value to an output pin. Returns True on success."""
        if self.directions.get(tag) != "output":
            logger.warning(f"Cannot write to input tag: {tag}")
            return False
        device = self.devices.get(tag)
        if device is None:
            return False
        if value:
            device.on()
        else:
            device.off()
        logger.info(f"Set output {tag} = {value}")
        return True

hardware_bridge = HardwareBridge()
