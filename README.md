# Industrial IoT Pipeline — Tank Level Control

An end-to-end industrial IoT system: a simulated PLC process is read over
**Modbus TCP**, transformed into JSON by a **data connector**, regulated by a
**closed-loop control microservice** (PID or hysteresis, Strategy pattern),
and persisted to **SQL and time-series storage** — all wired through a
**message bus** and deployable with **Docker Compose**.

```
                          ┌─────────────────────────────────────────────┐
                          │                message bus                  │
                          │   (in-memory demo / RabbitMQ deployment)    │
                          └─────────────────────────────────────────────┘
                              ▲ readings          │ readings   ▲ commands
                              │                   ▼            │
┌──────────────┐  Modbus  ┌───────────┐      ┌─────────┐   ┌─────────┐
│ PLC simulator│◄────TCP──►│ Connector │      │ Storage │   │ Control │
│ (tank process│  :5020    │ raw regs → │      │ SQLite/ │   │ PID /   │
│  physics)    │           │ JSON       │      │ InfluxDB│   │ Hyster. │
└──────────────┘           └───────────┘      └─────────┘   └─────────┘
```

The simulator speaks standard Modbus TCP, so it can be replaced by an
**OpenPLC runtime, a Codesys soft PLC, or real Siemens/Schneider hardware**
without changing a line of application code.

## Quick start (no Docker needed)

```bash
pip install -r requirements.txt
python main.py                # PID control, live console HMI
python main.py --hysteresis   # classic bang-bang control
python -m pytest tests/ -v    # unit tests
```

Example output — the PID converging the tank to the 50 % setpoint:

```
control strategy: PIDControl
level  53.4% |##########################          | pump  33.2%  T 25.4°C
level  55.5% |###########################         | pump  51.1%  T 25.3°C
level  52.4% |##########################          | pump  80.5%  T 25.9°C
level  50.8% |#########################           | pump  80.8%  T 26.3°C
--- last 5 rows persisted in SQLite ---
```

## Full microservices deployment

```bash
docker compose --profile python-control up --build
```

Runs each service in its own container: PLC sim, connector, control,
storage (InfluxDB time-series + PostgreSQL relational), RabbitMQ broker,
and Grafana (http://localhost:3000) as the HMI dashboard.

## Real PLC path: OpenPLC Runtime

The `control` service above is a Python stand-in. `plc_sim/openplc_program/tank_control.st`
is the same control loop written as real **IEC 61131-3 Structured Text**,
meant to run on an actual [OpenPLC Runtime](https://openplc.org) instead —
this is the difference between "simulating a PLC in Python" and "writing
PLC software," which is literally the job description this project targets.

```bash
docker compose --profile openplc up --build
```

Then, one-time setup through the OpenPLC web UI at http://localhost:8080
(user/pass `openplc`/`openplc` — this part is GUI-driven, not scriptable):

1. **Programs** → upload `plc_sim/openplc_program/tank_control.st` → compile.
2. **Slave Devices** → *Add new device* → Generic Modbus TCP, IP `plc-sim`,
   port `5020`. This makes OpenPLC a **Modbus master** polling the plant
   simulator, exactly like a real PLC talking to a remote I/O module.
3. **Start PLC.**

OpenPLC now runs the ST program against the live simulated tank, including
a hard-coded **emergency-stop interlock at 95% level** — a safety behavior
that only exists in this version, not in the Python control service, because
it belongs in deterministic PLC scan-cycle logic rather than an application
service that can lag or crash.

OpenPLC re-exposes its own I/O as a Modbus TCP server on port `502` for
supervisory/SCADA systems to read — point the Python `connector` at
`MODBUS_HOST=openplc`, `MODBUS_PORT=502` to feed this pipeline's storage
and dashboard from the real-PLC path instead of the Python one.

## Design decisions (SOLID)

| Principle | Where |
|---|---|
| **S**ingle Responsibility | Connector only acquires/transforms; Control only decides; Storage only persists |
| **O**pen/Closed | New control algorithms are new `ControlAlgorithm` strategies — the service never changes |
| **L**iskov Substitution | `PIDControl` and `HysteresisControl` are fully interchangeable |
| **I**nterface Segregation | `ReadingRepository` exposes only `save`/`recent`, no generic CRUD |
| **D**ependency Inversion | Services depend on `MessageBus` / `ReadingRepository` abstractions; concrete broker/DB injected at the edge |

Patterns used: **Strategy** (control algorithms), **Repository** (storage
backends), **Pub/Sub** (service decoupling), **Dependency Injection**
throughout.

## Register map (the "device contract")

| Address | Type | Meaning | Scaling |
|---|---|---|---|
| HR0 | holding reg | tank level | raw/10 → % |
| HR1 | holding reg | inlet flow | raw/10 → L/min |
| HR2 | holding reg | temperature | raw/10 → °C |
| HR3 | holding reg | pump speed setpoint (written back) | raw/10 → % |
| C0 | coil | inlet valve open | bool |
| C1 | coil | high-level alarm (>90 %) | bool |

## Roadmap

- [ ] OPC-UA connector variant (`asyncua`) alongside Modbus
- [x] Real PLC path: OpenPLC Runtime executing `tank_control.st` (see above)
- [ ] Kafka bus implementation next to RabbitMQ
- [ ] Web HMI (FastAPI + WebSocket) replacing the console view
- [ ] OTA-style config: control setpoints editable from PostgreSQL
- [ ] Architecture decision records (`docs/decisions/`) documenting why
      Modbus, why PI over fuzzy/MPC, why a message bus
