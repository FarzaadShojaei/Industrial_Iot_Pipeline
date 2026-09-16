(*
    Tank Level Control — IEC 61131-3 Structured Text
    =================================================
    This is the program that actually runs INSIDE OpenPLC Runtime,
    replacing control/algorithms.py's PIDControl for the "real PLC" path.

    I/O wiring: after uploading and compiling this program in the OpenPLC
    web UI, go to "Hardware" and OpenPLC will list these AT-addressed
    variables so you can give them friendly names for the Slave Devices
    page (Slave Devices is where you tell OpenPLC to fetch %IW0.. from
    plc-sim over Modbus TCP, and push %QW0.. back to it).

        %IW0  level_pct_raw     -- from plant simulator HR0 (raw, /10 = %)
        %IW1  inflow_raw        -- HR1 (raw, /10 = L/min)
        %IW2  temperature_raw   -- HR2 (raw, /10 = degC)
        %IX0.0 alarm_in         -- plant's own high-level coil (C1)

        %QW0  pump_speed_raw    -- to plant simulator HR3 (raw = % * 10)
        %QX0.0 valve_cmd        -- to plant simulator C0
        %QX0.1 high_level_alarm -- PLC's OWN alarm output (independent safety layer)

    Control strategy: PI control on tank level, setpoint 50.0 %, plus a
    hard interlock that the Python simulation never had — this is the
    actual point of moving control onto a real PLC: safety-critical
    logic runs in a deterministic scan cycle here, not in a Python
    service that can crash, GC-pause, or lag behind the process.
*)

PROGRAM tank_control
VAR
    (* ---- I/O, address-mapped (AT) so OpenPLC can bind them to Modbus --- *)
    level_pct_raw     AT %IW0   : INT;
    inflow_raw        AT %IW1   : INT;
    temperature_raw   AT %IW2   : INT;
    alarm_in          AT %IX0.0 : BOOL;

    pump_speed_raw    AT %QW0   : INT;
    valve_cmd         AT %QX0.0 : BOOL;
    high_level_alarm  AT %QX0.1 : BOOL;

    (* ---- scaled process values (engineering units) ---- *)
    level_pct       : REAL;
    inflow_lpm      : REAL;
    temperature_c   : REAL;

    (* ---- setpoint & tuning (visible/editable from the OpenPLC
             "Monitoring" page without recompiling) ---- *)
    setpoint_pct    : REAL := 50.0;
    kp              : REAL := 4.0;
    ki              : REAL := 0.8;

    (* ---- PI internal state ---- *)
    error_pct       : REAL := 0.0;
    integral        : REAL := 0.0;
    scan_dt         : REAL := 0.1;   (* seconds, matches the task interval below *)

    (* ---- output (engineering units, before scaling back to raw) ---- *)
    pump_speed_pct  : REAL := 0.0;

    (* ---- safety interlock: NOT present anywhere in the Python code ---- *)
    HIGH_HIGH_LEVEL : REAL := 95.0;  (* emergency threshold, % *)
    RESET_LEVEL     : REAL := 90.0;  (* must drop below this to auto-reset *)
    emergency_stop  : BOOL := FALSE;
END_VAR

(* ---- 1. Read & scale raw registers into engineering units ---- *)
level_pct     := INT_TO_REAL(level_pct_raw)   / 10.0;
inflow_lpm    := INT_TO_REAL(inflow_raw)      / 10.0;
temperature_c := INT_TO_REAL(temperature_raw) / 10.0;

(* ---- 2. Safety interlock — evaluated every scan, overrides control ---- *)
IF level_pct >= HIGH_HIGH_LEVEL THEN
    emergency_stop := TRUE;
ELSIF emergency_stop AND level_pct < RESET_LEVEL THEN
    emergency_stop := FALSE;   (* hysteresis so it doesn't chatter at the edge *)
END_IF;

(* ---- 3. PI control (bypassed while in emergency stop) ---- *)
IF NOT emergency_stop THEN
    error_pct := level_pct - setpoint_pct;
    integral  := integral + (error_pct * scan_dt);

    (* anti-windup clamp *)
    IF integral > 100.0 THEN
        integral := 100.0;
    ELSIF integral < -100.0 THEN
        integral := -100.0;
    END_IF;

    pump_speed_pct := 50.0 + (kp * error_pct) + (ki * integral);

    IF pump_speed_pct > 100.0 THEN
        pump_speed_pct := 100.0;
    ELSIF pump_speed_pct < 0.0 THEN
        pump_speed_pct := 0.0;
    END_IF;
ELSE
    (* emergency: drain at full pump speed, force inlet valve shut *)
    pump_speed_pct := 100.0;
END_IF;

(* ---- 4. Write outputs back (scale engineering units -> raw x10 ints) ---- *)
pump_speed_raw   := REAL_TO_INT(pump_speed_pct * 10.0);
valve_cmd        := NOT emergency_stop;
high_level_alarm := emergency_stop;

END_PROGRAM


CONFIGURATION Config0
    RESOURCE Res0 ON PLC
        TASK task0(INTERVAL := T#100ms, PRIORITY := 0);
        PROGRAM instance0 WITH task0 : tank_control;
    END_RESOURCE
END_CONFIGURATION
