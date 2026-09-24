# rrcf_ros2_bridge

A minimal ROS 2 node that makes an existing ROS 2 robot **RRCF-transport
compliant** without touching its control stack. Point it at your robot's
`.rrcf` file and its existing `/cmd_vel`, e-stop, and telemetry topics — it
does the rest: MQTT ↔ ROS 2 translation, safety-limit clamping, the
mandatory watchdog, and estop propagation.

This is the "quick path" referenced in the
[RRCF adoption guide](../../rrcf-adoption-guide.md): most ROS 2 robots
already publish `geometry_msgs/Twist` on `/cmd_vel` and have *some* e-stop
mechanism. This bridge sits alongside that stack rather than replacing it,
so a robot can become RRCF-compliant in an afternoon instead of a rewrite.

## What it does

```
                     MQTT (rrcf_mqtt)                 ROS 2
                  ┌──────────────────┐          ┌──────────────────┐
  Web UI /        │  operator_cmd    │  bridge  │  /cmd_vel         │  robot's
  fleet console /  ───────────────▶  │ ───────▶ │  (Twist)          │  own
  VLA model        │  (RRCF JSON)     │  node    │                   │  stack
                    │                  │          │  /rrcf/estop      │
                    │  telemetry       │ ◀─────── │  (existing topics)│
                    ◀──────────────────  publish  │                   │
                     └──────────────────┘          └──────────────────┘
```

- **Loads your `.rrcf` file** at startup — category, `max_vx/vy/wz` speed
  limits, e-stop topic/QoS, watchdog timeout, and the declared MQTT
  transport endpoints all come from the declaration, not hardcoded config.
- **Subscribes to the declared `operator_cmd` MQTT topic.** Every valid RRCF
  wire-format message is converted to a `geometry_msgs/Twist` and published
  on `/cmd_vel` (or whatever topic you map it to).
- **Enforces the RRCF-1.0 conformance MUSTs for robots** (spec §11.1):
  - `estop:true` → halts immediately: zero `Twist`, publish `True` on the
    e-stop topic, latch until cleared.
  - Watchdog: if no valid command arrives within the declared
    `timeout_ms`, the bridge halts the robot itself — it doesn't wait for
    the robot's own firmware watchdog as the only line of defense.
  - Speed-limit clamping: `lx/ly/rx/ry` are clamped to `[-1.0, 1.0]` and
    scaled by the declared `max_vx/max_vy/max_wz` before hitting `/cmd_vel`,
    regardless of what the operator sent.
  - Telemetry republish at the declared `frequency_hz`, sourced from
    whatever ROS topics you map in `telemetry_map`.
- **Dispatches skills** as `std_msgs/String` on `/rrcf/<slug>/skill` by
  default, so a simple ROS 2 subscriber (or an existing behavior-tree /
  state-machine node) can act on `skill:<id>` without the bridge needing to
  know what each skill actually does.

## What it does not do

This is a reference bridge, not a certified implementation. It does not:
- Implement a hardware-independent e-stop (spec §13 requires this in
  hardware — the bridge's watchdog is a software safety net on top of that,
  not a replacement for it).
- Provide TLS/auth out of the box — wire up MQTTS (port 8883) and broker
  credentials via the launch args before using this outside a trusted
  network (see [Configuration](#configuration)).
- Know your skill semantics — it dispatches skill IDs, your robot's own
  code decides what `heel_stretch` means.

## Install

```bash
# from your ROS 2 workspace src/
cp -r rrcf_ros2_bridge ~/ros2_ws/src/
cd ~/ros2_ws
rosdep install --from-paths src/rrcf_ros2_bridge --ignore-src -r -y
pip install paho-mqtt --break-system-packages   # if not already present
colcon build --packages-select rrcf_ros2_bridge
source install/setup.bash
```

Tested against ROS 2 Humble/Jazzy + `rclpy`. No other RRCF-specific ROS
dependencies — it's a single node plus a small XML parser module.

## Run

```bash
ros2 launch rrcf_ros2_bridge rrcf_bridge.launch.py \
  rrcf_file:=/path/to/your_robot.rrcf \
  cmd_vel_topic:=/cmd_vel \
  estop_topic:=/rrcf/estop
```

Or run the node directly with parameters:

```bash
ros2 run rrcf_ros2_bridge bridge_node --ros-args \
  -p rrcf_file:=/path/to/your_robot.rrcf \
  -p cmd_vel_topic:=/cmd_vel \
  -p estop_topic:=/rrcf/estop \
  -p mqtt_broker_override:=localhost \
  -p mqtt_port:=1883
```

## Configuration

Most values come straight from the `.rrcf` file's `<safety>` and
`<transport>` blocks. A handful of ROS-side parameters map RRCF's abstract
declarations onto your specific topics:

| Parameter | Default | Purpose |
|---|---|---|
| `rrcf_file` | *(required)* | Path to the robot's `.rrcf` file |
| `cmd_vel_topic` | `/cmd_vel` | Where translated `Twist` commands are published |
| `estop_topic` | value of `<estop topic>` in the `.rrcf` | ROS `std_msgs/Bool` topic the robot's own stack watches for e-stop |
| `skill_topic_prefix` | `/rrcf/<slug>/skill` | Where dispatched skill IDs (`std_msgs/String`) are published |
| `telemetry_map` | `{}` | YAML map of RRCF telemetry field id → ROS topic (see below) |
| `mqtt_broker_override` | value of `${MQTT_BROKER}` in the `.rrcf`, or `localhost` | MQTT broker host, since `.rrcf` files use an env-var placeholder |
| `mqtt_port` | `1883` | Use `8883` + TLS for anything outside a trusted network |

Telemetry mapping example (`telemetry_map.yaml`):

```yaml
battery: /battery_state          # sensor_msgs/BatteryState, .percentage read
temp:    /diagnostics/cpu_temp   # std_msgs/Float32
speed:   /odom                   # nav_msgs/Odometry, linear speed magnitude
```

Unmapped fields declared in `<telemetry>` are published as `null` so
consumers can still see the field exists but isn't wired up yet — that's
your cue to either map it or fix the `.rrcf` to stop declaring it.

## Files

```
rrcf_ros2_bridge/
├── package.xml
├── setup.py / setup.cfg
├── resource/rrcf_ros2_bridge
├── rrcf_ros2_bridge/
│   ├── __init__.py
│   ├── rrcf_parser.py     parses a .rrcf file into a plain dict — no ROS/MQTT deps, unit-testable standalone
│   └── bridge_node.py     the rclpy node: MQTT client, watchdog timer, Twist translation, telemetry loop
├── launch/rrcf_bridge.launch.py
└── test/test_rrcf_parser.py
```

## Extending

- **Skill → ROS service/action dispatch**: `bridge_node.py`'s
  `_on_skill()` is the single place to change if you want skill IDs to call
  a ROS 2 service or action instead of publishing a topic — it's a five-line
  function.
- **Custom controls**: `<custom_controls>` sliders/toggles aren't wired to
  anything by default (there's no universal ROS mapping for "the 3rd
  operator-defined slider"). Add a `custom_controls_map` parameter the same
  shape as `telemetry_map` if your robot needs it.
- **Non-MQTT transport**: if your `.rrcf` declares a `websocket` endpoint
  instead of `rrcf_mqtt`, swap the `paho-mqtt` client in `bridge_node.py`
  for a `websockets` client — the parsing, clamping, and watchdog logic
  underneath is transport-agnostic.
