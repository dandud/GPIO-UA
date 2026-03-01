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

from i2c_drivers import create_driver, DRIVER_REGISTRY


class MockInputDevice:
    def __init__(self, gpio):
        self.gpio = gpio
        self.is_active = False
        
    def read(self):
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
        self.devices = {}       # tag -> device instance (GPIO devices)
        self.directions = {}    # tag -> "input" | "output"
        self.i2c_drivers = {}   # tag -> I2C driver instance
        self.sensor_configs = []
        
    def setup_sensors(self, sensors_config):
        """Initialize hardware connections based on configuration."""
        self.devices.clear()
        self.directions.clear()
        self.i2c_drivers.clear()
        self.sensor_configs = sensors_config

        for sensor in sensors_config:
            tag = sensor.get("tag_name")
            sensor_type = sensor.get("type", "gpio")
            
            if sensor_type == "i2c":
                self._setup_i2c(sensor, tag)
            else:
                self._setup_gpio(sensor, tag)

    def _setup_gpio(self, sensor, tag):
        """Initialize a GPIO device."""
        gpio = sensor.get("gpio")
        direction = sensor.get("direction", "input")
        self.directions[tag] = direction

        try:
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
        except Exception as e:
            logger.error(f"Failed to initialize {tag} on GPIO {gpio}: {e}")
            if direction == "output":
                self.devices[tag] = MockOutputDevice(gpio)
            else:
                self.devices[tag] = MockInputDevice(gpio)

    def _setup_i2c(self, sensor, tag):
        """Initialize an I2C sensor driver."""
        driver_name = sensor.get("driver", "")
        address = sensor.get("address", "0x76")
        channel = sensor.get("channel", 0)

        if driver_name not in DRIVER_REGISTRY:
            logger.error(f"Unknown I2C driver '{driver_name}' for tag {tag}")
            return

        try:
            driver = create_driver(driver_name, address, channel=channel)
            self.i2c_drivers[tag] = driver
            logger.info(f"Initialized I2C driver {driver_name} at {address} for tag {tag}")
        except Exception as e:
            logger.error(f"Failed to initialize I2C {driver_name} for {tag}: {e}")

    def read_all(self):
        """Read all configured sensors and return dict of {tag: value}"""
        results = {}

        # Read GPIO devices
        for tag, device in self.devices.items():
            if self.directions.get(tag) == "output":
                if GPIO_AVAILABLE and isinstance(device, DigitalOutputDevice):
                    results[tag] = bool(device.value)
                else:
                    results[tag] = device.is_active
            else:
                if GPIO_AVAILABLE and isinstance(device, DigitalInputDevice):
                    results[tag] = device.is_active
                else:
                    results[tag] = device.read()

        # Read I2C drivers (multi-field)
        for tag, driver in self.i2c_drivers.items():
            try:
                readings = driver.read()
                for field, value in readings.items():
                    results[f"{tag}.{field}"] = value
            except Exception as e:
                logger.error(f"Error reading I2C sensor {tag}: {e}")

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

    def get_i2c_fields(self, tag):
        """Get the field definitions for an I2C sensor tag."""
        driver = self.i2c_drivers.get(tag)
        if driver:
            return driver.FIELDS
        return []


hardware_bridge = HardwareBridge()
