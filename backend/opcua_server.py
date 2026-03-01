import asyncio
import logging
from asyncua import Server
from hardware_bridge import hardware_bridge
from websocket_manager import ws_manager

logger = logging.getLogger(__name__)

class OpcUaServerWrapper:
    def __init__(self):
        self.server = Server()
        self.task = None
        self.is_running = False
        self.nodes = {}
        self.directions = {}  # tag -> "input" | "output"

    async def init_server(self, config):
        await self.server.init()
        self.server.set_endpoint("opc.tcp://0.0.0.0:4840/freeopcua/server/")
        self.server.set_server_name("GPIO-UA Edge Node")
        
        uri = "http://gpio-ua.local"
        idx = await self.server.register_namespace(uri)
        
        objects = self.server.nodes.objects
        self.device_obj = await objects.add_object(idx, "Sensors")
        
        self.nodes.clear()
        self.directions.clear()
        sensors = config.get("sensors", [])
        hardware_bridge.setup_sensors(sensors)
        
        for sensor in sensors:
            tag = sensor.get("tag_name")
            sensor_type = sensor.get("type", "gpio")
            direction = sensor.get("direction", "input")
            
            if sensor_type == "i2c":
                # I2C sensors create multiple sub-tags (e.g., tag.temperature, tag.humidity)
                fields = hardware_bridge.get_i2c_fields(tag)
                for field_name, unit in fields:
                    sub_tag = f"{tag}.{field_name}"
                    node = await self.device_obj.add_variable(idx, sub_tag, 0.0)
                    # I2C tags are read-only
                    self.nodes[sub_tag] = node
                    self.directions[sub_tag] = "input"
            else:
                # GPIO sensor — single boolean tag
                node = await self.device_obj.add_variable(idx, tag, False)
                if direction == "output":
                    await node.set_writable()
                self.nodes[tag] = node
                self.directions[tag] = direction

    async def run(self):
        self.is_running = True
        logger.info("Starting OPC UA Server...")
        async with self.server:
            while self.is_running:
                values = hardware_bridge.read_all()
                for tag, value in values.items():
                    if tag in self.nodes:
                        direction = self.directions.get(tag, "input")
                        if direction == "output":
                            # For outputs, check if an OPC UA client wrote a new value
                            opcua_val = await self.nodes[tag].read_value()
                            if bool(opcua_val) != bool(value):
                                hardware_bridge.write(tag, bool(opcua_val))
                        # Always update the OPC UA node and UI with current state
                        await self.nodes[tag].write_value(value)
                        await ws_manager.broadcast_tag_update(tag, value, "Good")
                await asyncio.sleep(0.5)

    async def start(self, config):
        if self.is_running:
            await self.stop()
        await self.init_server(config)
        self.task = asyncio.create_task(self.run())

    async def stop(self):
        self.is_running = False
        if self.task:
            await self.task
            self.task = None

opcua_instance = OpcUaServerWrapper()
