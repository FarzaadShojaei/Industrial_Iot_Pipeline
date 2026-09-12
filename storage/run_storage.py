"""Container entry point: storage service over RabbitMQ -> InfluxDB."""
import logging, os, time
from common.message_bus import RabbitMQBus
from storage.repositories import InfluxRepository, StorageService

logging.basicConfig(level=logging.INFO)
bus = RabbitMQBus(os.environ["AMQP_URL"])
repo = InfluxRepository(url=os.environ["INFLUX_URL"], token=os.environ["INFLUX_TOKEN"],
                        org=os.environ["INFLUX_ORG"], bucket=os.environ["INFLUX_BUCKET"])
StorageService(bus, repo)
while True: time.sleep(60)
