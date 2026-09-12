"""Unit tests — run with:  python -m pytest tests/ -v"""

from common.message_bus import InMemoryBus
from common.models import SensorReading
from connector.modbus_connector import ModbusConnector
from control.algorithms import HysteresisControl, PIDControl


def make_reading(level: float) -> SensorReading:
    return SensorReading(source="test", level_pct=level, inflow_lpm=60.0,
                         temperature_c=25.0, pump_speed_pct=0.0,
                         valve_open=True, alarm_high_level=False)


def test_transform_scales_registers_to_engineering_units():
    connector = ModbusConnector.__new__(ModbusConnector)  # skip network init
    connector._source = "test"
    reading = connector.transform(
        registers=[503, 612, 253, 450],   # raw x10 values
        coils=[True, False],
    )
    assert reading.level_pct == 50.3
    assert reading.inflow_lpm == 61.2
    assert reading.temperature_c == 25.3
    assert reading.pump_speed_pct == 45.0
    assert reading.valve_open is True
    assert reading.alarm_high_level is False


def test_reading_json_roundtrip():
    r = make_reading(42.0)
    assert SensorReading.from_json(r.to_json()) == r


def test_hysteresis_switches_only_outside_deadband():
    ctrl = HysteresisControl(low=45, high=55, pump_on=80, pump_off=10)
    assert ctrl.compute(make_reading(60)) == 80   # above high -> pump hard
    assert ctrl.compute(make_reading(50)) == 80   # inside deadband -> hold
    assert ctrl.compute(make_reading(40)) == 10   # below low -> pump off


def test_pid_pumps_more_when_level_is_high():
    ctrl = PIDControl(setpoint=50.0)
    low = ctrl.compute(make_reading(40))
    ctrl2 = PIDControl(setpoint=50.0)
    high = ctrl2.compute(make_reading(60))
    assert high > low


def test_pid_output_is_clamped():
    ctrl = PIDControl(setpoint=50.0, kp=1000)
    assert ctrl.compute(make_reading(100)) == 100.0
    ctrl2 = PIDControl(setpoint=50.0, kp=1000)
    assert ctrl2.compute(make_reading(0)) == 0.0


def test_inmemory_bus_delivers_to_subscriber():
    import time
    bus = InMemoryBus()
    got: list[str] = []
    bus.subscribe("t", got.append)
    bus.publish("t", "hello")
    time.sleep(0.2)
    assert got == ["hello"]
