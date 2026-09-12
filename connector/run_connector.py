"""Container entry point: Modbus connector over RabbitMQ."""
import logging, os
from common.message_bus import RabbitMQBus
from connector.modbus_connector import ModbusConnector

logging.basicConfig(level=logging.INFO)
bus = RabbitMQBus(os.environ["AMQP_URL"])
ModbusConnector(bus, host=os.environ.get("MODBUS_HOST", "plc-sim")).run_forever()
