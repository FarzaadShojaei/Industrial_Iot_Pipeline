FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir pymodbus==3.6.9 pika influxdb-client
COPY . .
CMD ["python", "main.py"]
