# Robot Failure Lab 02: a two-second scan blackout

Question: when laser scans disappear briefly during navigation, does the robot
stop, resume and finish the task? This is a different experiment from Lab 01's
continuous 500 ms scan delay. It does not resolve Lab 01's timing uncertainty.

## Run

Use Ubuntu 24.04/WSL with ROS 2 Jazzy, Gazebo, Nav2's minimal TurtleBot3 simulator,
nav2_simple_commander, PyYAML, matplotlib, NumPy and Pillow. Inspect the retained
packages.txt for the actual tested versions. Run from this folder:

```bash
source /opt/ros/jazzy/setup.bash
python3 -m unittest -v test_core
python3 run.py /tmp/rfl02-check --repeats 1 --domain 188
python3 report.py /tmp/rfl02-check
# After the check passes, use a NEW directory for the planned six-trial series:
python3 run.py /tmp/rfl02-series --repeats 3 --domain 188
python3 report.py /tmp/rfl02-series
```

The output directory must not already exist. Do not run another workload on ROS
domain 188 at the same time. The runner stops only process groups it creates.
Startup errors are recorded separately and stop the batch. Evidence contains
source snapshots (including the upstream launch with its license), protocol,
versions, map, parameters, and per-trial logs/CSVs. The snapshot's *.py files can
be used to repeat the run with the same dependencies. This is not a portable
preinstalled environment. Upstream assets retain their licenses.

## Fixed protocol

- Fresh simulator/Nav2 per trial, original sandbox/start/goal. Three normal and
  three blackout trials, order N/B, B/N, N/B. The one-pair check is excluded.
- A trigger occurs after >=3 simulated seconds of the task and >=0.3 seconds of
  observed translation >=0.05 m/s with fresh odometry. Both arms use this rule.
- For the following two simulated seconds, blackout drops newly arriving scans
  at the relay. The control forwards them. No delayed queue or replay follows.
- AMCL, both costmaps and collision monitor consume the relay; the live ROS
  graph is checked. Odometry/IMU and map remain available.
- Collision monitor source_timeout=1.0 s in the inspected defaults, unchanged.
  No extra forced stop or resume command is injected.
- Measure task success/failure/90 s timeout, stop and resumption latencies,
  recovery count, odometry, output velocity commands and actual scan delivery.
- If the task ends early, observe passively through at least four seconds after
  the window. Keep the failure and its original termination time. Do not send
  a replacement goal or classify task aborts as invalid sensor injections.
- Stop: speed <=0.01 m/s and |yaw rate| <=0.03 rad/s for >=0.3 s. Resume: speed
  >=0.05 m/s for >=0.3 s after the window, when a stop was measured. Large gaps
  (>0.15 s) cannot establish sustained motion or stopping.
- Gazebo seeds 101/102/103 matched within pairs through a narrowly patched
  installed launch copy. AMCL randomness/scheduling remain uncontrolled; this
  is exploratory, not a deterministic or statistically powered comparison.

The report validates each dropped/forwarded scan against its interval, upstream
scan continuity, prompt resumption, telemetry continuity and recomputed metrics.
Plots show all runs and the predeclared first pair. Stopping or finishing in a
static simulator is not proof of collision safety with a newly appearing obstacle.
No physical test, Vektor integration, public upload or product advantage is implied.
