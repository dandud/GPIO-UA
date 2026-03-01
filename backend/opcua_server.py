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

    async def init_server(self, config):
        await self.server.init()
        # Set endpoint
        # TODO: Allow network interface configuration
        self.server.set_endpoint("opc.tcp://0.0.0.0:4840/freeopcua/server/")
        self.server.set_server_name("GPIO-UA Edge Node")
        
        # Setup address space
        uri = "http://gpio-ua.local"
        idx = await self.server.register_namespace(uri)
        
        objects = self.server.nodes.objects
        self.device_obj = await objects.add_object(idx, "Sensors")
        
        # Build nodes from config
        self.nodes.clear()
        sensors = config.get("sensors", [])
        hardware_bridge.setup_sensors(sensors)
        
        for sensor in sensors:
            tag = sensor.get("tag_name")
            # Default to boolean for now
            node = await self.device_obj.add_variable(idx, tag, False)
            await node.set_writable()
            self.nodes[tag] = node

    async def run(self):
        self.is_running = True
        logger.info("Starting OPC UA Server...")
        async with self.server:
            while self.is_running:
                # Read hardware
                values = hardware_bridge.read_all()
                for tag, value in values.items():
                    if tag in self.nodes:
                        await self.nodes[tag].write_value(value)
                        # Broadcast to UI
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
