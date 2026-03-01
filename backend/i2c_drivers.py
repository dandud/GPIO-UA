"""
I2C Sensor Driver Registry
Provides driver classes for common I2C sensors with mock fallbacks.
"""
import logging
import random
import struct

logger = logging.getLogger(__name__)

# Try importing smbus2 for real I2C access
try:
    import smbus2
    I2C_AVAILABLE = True
except ImportError:
    I2C_AVAILABLE = False
    logger.warning("smbus2 not available, using mock I2C drivers")


class BaseI2CDriver:
    """Base class for I2C sensor drivers."""
    NAME = "generic"
    FIELDS = []  # List of (field_name, unit) tuples, e.g. [("temperature", "°C")]

    def __init__(self, address, bus=1, **kwargs):
        self.address = address
        self.bus_num = bus

    def read(self):
        """Returns dict of {field_name: float_value}"""
        raise NotImplementedError


# ============================================
#  BME280 — Temperature / Humidity / Pressure
# ============================================

class BME280Driver(BaseI2CDriver):
    """
    Bosch BME280 sensor driver via smbus2.
    Default address: 0x76 (alt: 0x77)
    Returns temperature (°C), humidity (%), pressure (hPa)
    """
    NAME = "BME280"
    FIELDS = [("temperature", "°C"), ("humidity", "%"), ("pressure", "hPa")]

    def __init__(self, address=0x76, bus=1, **kwargs):
        super().__init__(address, bus, **kwargs)
        self.bus = smbus2.SMBus(bus)
        self.cal = {}
        self._load_calibration()
        self._configure()

    def _load_calibration(self):
        """Read calibration data from BME280 registers."""
        cal = self.bus.read_i2c_block_data(self.address, 0x88, 26)
        self.cal['T1'] = cal[0] | (cal[1] << 8)
        self.cal['T2'] = self._signed16(cal[2] | (cal[3] << 8))
        self.cal['T3'] = self._signed16(cal[4] | (cal[5] << 8))
        self.cal['P1'] = cal[6] | (cal[7] << 8)
        self.cal['P2'] = self._signed16(cal[8] | (cal[9] << 8))
        self.cal['P3'] = self._signed16(cal[10] | (cal[11] << 8))
        self.cal['P4'] = self._signed16(cal[12] | (cal[13] << 8))
        self.cal['P5'] = self._signed16(cal[14] | (cal[15] << 8))
        self.cal['P6'] = self._signed16(cal[16] | (cal[17] << 8))
        self.cal['P7'] = self._signed16(cal[18] | (cal[19] << 8))
        self.cal['P8'] = self._signed16(cal[20] | (cal[21] << 8))
        self.cal['P9'] = self._signed16(cal[22] | (cal[23] << 8))
        self.cal['H1'] = cal[25]

        cal2 = self.bus.read_i2c_block_data(self.address, 0xE1, 7)
        self.cal['H2'] = self._signed16(cal2[0] | (cal2[1] << 8))
        self.cal['H3'] = cal2[2]
        self.cal['H4'] = (cal2[3] << 4) | (cal2[4] & 0x0F)
        self.cal['H5'] = (cal2[5] << 4) | ((cal2[4] >> 4) & 0x0F)
        self.cal['H6'] = struct.unpack('b', bytes([cal2[6]]))[0]

    def _configure(self):
        """Set normal mode, oversampling x1 for all."""
        self.bus.write_byte_data(self.address, 0xF2, 0x01)  # Humidity oversampling x1
        self.bus.write_byte_data(self.address, 0xF4, 0x27)  # Temp+Press oversampling x1, normal mode

    @staticmethod
    def _signed16(val):
        return val - 65536 if val >= 32768 else val

    def read(self):
        """Read compensated temperature, humidity, pressure."""
        data = self.bus.read_i2c_block_data(self.address, 0xF7, 8)
        pres_raw = (data[0] << 12) | (data[1] << 4) | (data[2] >> 4)
        temp_raw = (data[3] << 12) | (data[4] << 4) | (data[5] >> 4)
        hum_raw = (data[6] << 8) | data[7]

        # Temperature compensation
        var1 = (((temp_raw >> 3) - (self.cal['T1'] << 1)) * self.cal['T2']) >> 11
        var2 = (((((temp_raw >> 4) - self.cal['T1']) * ((temp_raw >> 4) - self.cal['T1'])) >> 12) * self.cal['T3']) >> 14
        t_fine = var1 + var2
        temperature = round((t_fine * 5 + 128) >> 8, 1) / 100.0

        # Pressure compensation
        var1p = t_fine - 128000
        var2p = var1p * var1p * self.cal['P6']
        var2p += (var1p * self.cal['P5']) << 17
        var2p += self.cal['P4'] << 35
        var1p = ((var1p * var1p * self.cal['P3']) >> 8) + ((var1p * self.cal['P2']) << 12)
        var1p = ((1 << 47) + var1p) * self.cal['P1'] >> 33
        if var1p == 0:
            pressure = 0
        else:
            p = 1048576 - pres_raw
            p = (((p << 31) - var2p) * 3125) // var1p
            var1p = (self.cal['P9'] * (p >> 13) * (p >> 13)) >> 25
            var2p = (self.cal['P8'] * p) >> 19
            pressure = round(((p + var1p + var2p) >> 8) + (self.cal['P7'] << 4), 1) / 25600.0

        # Humidity compensation
        h = t_fine - 76800
        if h == 0:
            humidity = 0
        else:
            h = (((hum_raw << 14) - (self.cal['H4'] << 20) - (self.cal['H5'] * h)) + 16384) >> 15
            h = h * (((((((h * self.cal['H6']) >> 10) * (((h * self.cal['H3']) >> 11) + 32768)) >> 10) + 2097152) * self.cal['H2'] + 8192) >> 14)
            h -= ((((h >> 15) * (h >> 15)) >> 7) * self.cal['H1']) >> 4
            h = max(0, min(h, 419430400))
            humidity = round((h >> 12) / 1024.0, 1)

        return {
            "temperature": round(temperature, 1),
            "humidity": round(humidity, 1),
            "pressure": round(pressure, 1)
        }


# ===============================
#  ADS1115 — 16-bit ADC (4 ch)
# ===============================

class ADS1115Driver(BaseI2CDriver):
    """
    TI ADS1115 16-bit ADC driver via smbus2.
    Default address: 0x48
    Reads a single analog channel (0-3), returns voltage (0-3.3V)
    """
    NAME = "ADS1115"
    FIELDS = [("voltage", "V")]

    # Gain settings (full-scale range)
    GAIN_MAP = {
        6.144: 0x0000,
        4.096: 0x0200,
        2.048: 0x0400,  # default
        1.024: 0x0600,
        0.512: 0x0800,
        0.256: 0x0A00,
    }

    def __init__(self, address=0x48, bus=1, channel=0, **kwargs):
        super().__init__(address, bus, **kwargs)
        self.bus = smbus2.SMBus(bus)
        self.channel = min(max(int(channel), 0), 3)
        self.gain = 4.096  # ±4.096V range

    def read(self):
        """Start a single-shot conversion and read the result."""
        mux = (0x04 + self.channel) << 12  # Single-ended input
        config = 0x8000 | mux | self.GAIN_MAP[self.gain] | 0x0100 | 0x0003
        # Write config to start conversion
        config_bytes = [(config >> 8) & 0xFF, config & 0xFF]
        self.bus.write_i2c_block_data(self.address, 0x01, config_bytes)

        import time
        time.sleep(0.01)  # Wait for conversion

        # Read result
        result = self.bus.read_i2c_block_data(self.address, 0x00, 2)
        raw = (result[0] << 8) | result[1]
        if raw > 0x7FFF:
            raw -= 0x10000
        voltage = round(raw * self.gain / 32768.0, 3)

        return {"voltage": voltage}


# ====================
#  Mock I2C Drivers
# ====================

class MockBME280Driver(BaseI2CDriver):
    """Mock BME280 for development without hardware."""
    NAME = "BME280"
    FIELDS = BME280Driver.FIELDS

    def __init__(self, address=0x76, **kwargs):
        super().__init__(address, **kwargs)
        self._temp = 22.0
        self._hum = 45.0
        self._pres = 1013.0

    def read(self):
        # Drift values slightly for realism
        self._temp += random.uniform(-0.3, 0.3)
        self._hum += random.uniform(-0.5, 0.5)
        self._pres += random.uniform(-0.2, 0.2)
        self._temp = max(15, min(35, self._temp))
        self._hum = max(20, min(80, self._hum))
        self._pres = max(990, min(1030, self._pres))
        return {
            "temperature": round(self._temp, 1),
            "humidity": round(self._hum, 1),
            "pressure": round(self._pres, 1)
        }


class MockADS1115Driver(BaseI2CDriver):
    """Mock ADS1115 for development without hardware."""
    NAME = "ADS1115"
    FIELDS = ADS1115Driver.FIELDS

    def __init__(self, address=0x48, channel=0, **kwargs):
        super().__init__(address, **kwargs)
        self.channel = channel
        self._voltage = 1.65

    def read(self):
        self._voltage += random.uniform(-0.05, 0.05)
        self._voltage = max(0, min(3.3, self._voltage))
        return {"voltage": round(self._voltage, 3)}


# ===================
#  Driver Registry
# ===================

DRIVER_REGISTRY = {
    "BME280": {"real": BME280Driver, "mock": MockBME280Driver, "default_address": "0x76",
               "description": "Temperature / Humidity / Pressure"},
    "ADS1115": {"real": ADS1115Driver, "mock": MockADS1115Driver, "default_address": "0x48",
                "description": "16-bit ADC (4 channels)"},
}


def get_driver_info():
    """Return driver registry info for the frontend."""
    return {name: {
        "default_address": info["default_address"],
        "description": info["description"],
        "fields": info["real"].FIELDS
    } for name, info in DRIVER_REGISTRY.items()}


def create_driver(driver_name, address, **kwargs):
    """Create an I2C driver instance (real or mock depending on availability)."""
    entry = DRIVER_REGISTRY.get(driver_name)
    if not entry:
        raise ValueError(f"Unknown I2C driver: {driver_name}")

    addr_int = int(address, 16) if isinstance(address, str) else address

    if I2C_AVAILABLE:
        try:
            return entry["real"](address=addr_int, **kwargs)
        except Exception as e:
            logger.error(f"Failed to init real {driver_name} at {hex(addr_int)}: {e}, falling back to mock")
            return entry["mock"](address=addr_int, **kwargs)
    else:
        return entry["mock"](address=addr_int, **kwargs)
