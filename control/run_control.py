"""Container entry point: control service over RabbitMQ."""
import logging, os, time
from common.message_bus import RabbitMQBus
from control.algorithms import HysteresisControl, PIDControl
from control.control_service import ControlService

logging.basicConfig(level=logging.INFO)
bus = RabbitMQBus(os.environ["AMQP_URL"])
algo = PIDControl() if os.environ.get("ALGORITHM", "pid") == "pid" else HysteresisControl()
ControlService(bus, algo)
while True: time.sleep(60)
