#!/usr/bin/env python3
"""
bridge_node.py — rclpy node that makes an existing ROS 2 robot RRCF-transport
compliant. See package README.md for the full picture; this file focuses on
the wiring: MQTT in, Twist/estop/skill out on ROS 2, telemetry back out to
MQTT, plus the watchdog and speed-limit clamping RRCF-1.0 requires (spec
section 11.1).

This node deliberately does NOT re-implement your robot's control stack. It
sits next to it: subscribe to whatever ROS 2 already publishes, translate
what arrives over the RRCF transport into the topics your stack already
listens to.
"""

import json
import threading
import time
from pathlib import Path

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_msgs.msg import Bool, String

try:
    import paho.mqtt.client as mqtt
except ImportError:  # pragma: no cover - exercised only when paho is missing
    mqtt = None

from .rrcf_parser import parse_rrcf_file


def clamp(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


class RrcfBridgeNode(Node):
    def __init__(self):
        super().__init__("rrcf_bridge_node")

        self.declare_parameter("rrcf_file", "")
        self.declare_parameter("cmd_vel_topic", "/cmd_vel")
        self.declare_parameter("estop_topic", "")
        self.declare_parameter("skill_topic_prefix", "")
        self.declare_parameter("mqtt_broker_override", "")
        self.declare_parameter("mqtt_port", 1883)

        rrcf_path = self.get_parameter("rrcf_file").get_parameter_value().string_value
        if not rrcf_path:
            raise RuntimeError(
                "rrcf_file parameter is required, e.g. "
                "--ros-args -p rrcf_file:=/path/to/robot.rrcf"
            )
        if not Path(rrcf_path).exists():
            raise RuntimeError(f"rrcf_file not found: {rrcf_path}")

        self.profile = parse_rrcf_file(rrcf_path)
        self.get_logger().info(
            f"Loaded RRCF profile '{self.profile.name}' "
            f"(vendor={self.profile.vendor}, category={self.profile.category}, "
            f"skills={self.profile.skills})"
        )

        cmd_vel_topic = self.get_parameter("cmd_vel_topic").get_parameter_value().string_value
        estop_topic_param = self.get_parameter("estop_topic").get_parameter_value().string_value
        skill_prefix_param = self.get_parameter("skill_topic_prefix").get_parameter_value().string_value

        self.estop_topic = estop_topic_param or self.profile.safety.estop_topic
        self.skill_topic = skill_prefix_param or f"/rrcf/{self.profile.slug}/skill"

        # ROS 2 publishers — into the robot's existing stack
        self.twist_pub = self.create_publisher(Twist, cmd_vel_topic, 10)
        self.estop_pub = self.create_publisher(Bool, self.estop_topic, 10)
        self.skill_pub = self.create_publisher(String, self.skill_topic, 10)

        # Watchdog state — RRCF-1.0 section 11.1: robot MUST halt if no valid
        # command arrives within the declared timeout.
        self._last_cmd_monotonic = time.monotonic()
        self._estop_latched = False
        watchdog_period_s = max(0.05, self.profile.safety.watchdog_timeout_ms / 1000.0 / 2)
        self.create_timer(watchdog_period_s, self._check_watchdog)

        # MQTT client — subscribes to the declared operator_cmd endpoint,
        # publishes telemetry on the declared telemetry endpoint.
        self._mqtt_lock = threading.Lock()
        self._setup_mqtt()

        self.get_logger().info(
            f"rrcf_ros2_bridge ready — estop_topic={self.estop_topic} "
            f"cmd_vel_topic={cmd_vel_topic} skill_topic={self.skill_topic} "
            f"watchdog_timeout_ms={self.profile.safety.watchdog_timeout_ms}"
        )

    # ------------------------------------------------------------------
    # MQTT wiring
    # ------------------------------------------------------------------
    def _setup_mqtt(self):
        if mqtt is None:
            self.get_logger().error(
                "paho-mqtt is not installed — bridge will run watchdog/estop "
                "logic only, with no command input. Install with: "
                "pip install paho-mqtt --break-system-packages"
            )
            return

        operator_ep = self.profile.endpoint("operator_cmd")
        telemetry_ep = self.profile.endpoint("telemetry")
        if operator_ep is None:
            self.get_logger().warning(
                "No <endpoint role=\"operator_cmd\"> declared in the .rrcf file "
                "— nothing to subscribe to. Add one under <transport> in the "
                "spec's rrcf_mqtt protocol shape."
            )
            return

        broker_override = self.get_parameter("mqtt_broker_override").get_parameter_value().string_value
        broker = broker_override or self._resolve_broker(operator_ep.broker) or "localhost"
        port = self.get_parameter("mqtt_port").get_parameter_value().integer_value or 1883

        self._operator_topic = operator_ep.topic or f"/rrcf/{self.profile.slug}/cmd"
        self._telemetry_topic = (telemetry_ep.topic if telemetry_ep else None) or f"/rrcf/{self.profile.slug}/state"
        self._telemetry_hz = (telemetry_ep.frequency_hz if telemetry_ep else 0) or 1.0

        self.mqtt_client = mqtt.Client()
        self.mqtt_client.on_connect = self._on_mqtt_connect
        self.mqtt_client.on_message = self._on_mqtt_message
        try:
            self.mqtt_client.connect(broker, port, keepalive=30)
        except Exception as exc:  # pragma: no cover - network dependent
            self.get_logger().error(f"MQTT connect to {broker}:{port} failed: {exc}")
            return
        self.mqtt_client.loop_start()

        self.create_timer(1.0 / self._telemetry_hz, self._publish_telemetry)

    @staticmethod
    def _resolve_broker(broker_field: str) -> str:
        """.rrcf files typically declare broker="${MQTT_BROKER}" — an env-var
        placeholder, not a real address. Strip the placeholder syntax so a
        blank/unset value falls through to the mqtt_broker_override param or
        the localhost default, rather than trying to connect to the literal
        string "${MQTT_BROKER}"."""
        if not broker_field or broker_field.startswith("${"):
            return ""
        return broker_field

    def _on_mqtt_connect(self, client, userdata, flags, rc):
        if rc == 0:
            client.subscribe(self._operator_topic, qos=self.profile.safety.estop_qos)
            self.get_logger().info(f"MQTT connected, subscribed to {self._operator_topic}")
        else:
            self.get_logger().error(f"MQTT connect failed, rc={rc}")

    def _on_mqtt_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self.get_logger().warning(f"Dropped malformed RRCF message: {exc}")
            return
        self._handle_command(payload)

    # ------------------------------------------------------------------
    # Command handling — the core translation + safety enforcement
    # ------------------------------------------------------------------
    def _handle_command(self, cmd: dict):
        with self._mqtt_lock:
            self._last_cmd_monotonic = time.monotonic()

        # RRCF-1.0 section 11.2: estop MUST be present in every controller
        # message; section 11.1: robot MUST halt immediately on estop:true,
        # no exceptions — checked first, before any other processing.
        if cmd.get("estop") is True:
            self._trigger_estop()
            return
        if self._estop_latched:
            # Latched until a controller explicitly clears it (estop:false)
            # rather than auto-clearing on the next non-estop message — a
            # stray command shouldn't silently un-halt the robot.
            if cmd.get("estop") is False:
                self._clear_estop()
            else:
                return

        skill = cmd.get("skill")
        if skill:
            self._on_skill(skill)
            # A skill command and a stick command are mutually exclusive in
            # the wire format (spec section 8) — don't also publish a Twist.
            return

        lx = clamp(float(cmd.get("lx", 0.0)))
        ly = clamp(float(cmd.get("ly", 0.0)))
        rx = clamp(float(cmd.get("rx", 0.0)))

        twist = Twist()
        twist.linear.x = lx * self.profile.safety.max_vx
        twist.linear.y = ly * self.profile.safety.max_vy
        twist.angular.z = rx * self.profile.safety.max_wz
        self.twist_pub.publish(twist)

    def _on_skill(self, skill_id: str):
        """Dispatch a declared skill. Default behavior: publish the skill id
        as a String on skill_topic for a downstream node/state-machine to
        act on. Override this method (or subclass RrcfBridgeNode) to call a
        ROS 2 service/action instead — see README.md 'Extending'."""
        if skill_id not in self.profile.skills:
            self.get_logger().warning(
                f"Skill '{skill_id}' not declared in this robot's .rrcf — "
                f"dispatching anyway, but check the <skills> block."
            )
        msg = String()
        msg.data = skill_id
        self.skill_pub.publish(msg)

    def _trigger_estop(self):
        self._estop_latched = True
        self.twist_pub.publish(Twist())  # zero velocity — belt and suspenders
        self.estop_pub.publish(Bool(data=True))
        self.get_logger().warning("ESTOP engaged")

    def _clear_estop(self):
        self._estop_latched = False
        self.estop_pub.publish(Bool(data=False))
        self.get_logger().info("ESTOP cleared")

    # ------------------------------------------------------------------
    # Watchdog — RRCF-1.0 section 11.1
    # ------------------------------------------------------------------
    def _check_watchdog(self):
        with self._mqtt_lock:
            elapsed_ms = (time.monotonic() - self._last_cmd_monotonic) * 1000.0
        if elapsed_ms > self.profile.safety.watchdog_timeout_ms and not self._estop_latched:
            self.get_logger().warning(
                f"Watchdog timeout ({elapsed_ms:.0f}ms > "
                f"{self.profile.safety.watchdog_timeout_ms}ms) — halting."
            )
            self.twist_pub.publish(Twist())
            if self.profile.safety.watchdog_action == "halt":
                # A watchdog-triggered halt is not the same state as an
                # operator estop — don't latch it, just keep zeroing Twist
                # until a fresh command arrives.
                pass

    # ------------------------------------------------------------------
    # Telemetry republish — RRCF-1.0 section 11.1: publish at >= 1 Hz
    # ------------------------------------------------------------------
    def _publish_telemetry(self):
        if mqtt is None or not hasattr(self, "mqtt_client"):
            return
        payload = {
            "rrcf": "1.0",
            "category": self.profile.category,
            "estop": self._estop_latched,
            "ts": int(time.time() * 1000),
            # Declared fields with no ROS mapping wired (see telemetry_map in
            # README) are reported as null rather than omitted, so a
            # consumer can tell "declared but unmapped" apart from "not
            # declared at all".
            **{f: None for f in self.profile.telemetry_fields},
        }
        self.mqtt_client.publish(self._telemetry_topic, json.dumps(payload), qos=0)


def main(args=None):
    rclpy.init(args=args)
    node = RrcfBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if hasattr(node, "mqtt_client"):
            node.mqtt_client.loop_stop()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
