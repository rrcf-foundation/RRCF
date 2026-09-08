"""Unit tests for rrcf_parser.py — no ROS 2 install required to run these:

    python3 -m pytest test/test_rrcf_parser.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rrcf_ros2_bridge.rrcf_parser import parse_rrcf_string  # noqa: E402

SAMPLE_RRCF = """<?xml version="1.0" encoding="UTF-8"?>
<rrcf version="1.0" xmlns="https://rrcf.io/schema/1.0">
  <meta>
    <name>Test Go2</name>
    <vendor>Unitree Robotics</vendor>
  </meta>
  <primary category="legged">
    <locomotion axes="vx vy wz" max_vx="1.5" max_vy="0.5" max_wz="2.0"/>
  </primary>
  <skills>
    <skill id="sit" label="Sit" standard="true" cmd='{"mode":"sit"}'/>
    <skill id="stand" label="Stand" standard="true" cmd='{"mode":"stand"}'/>
  </skills>
  <telemetry>
    <field id="battery" unit="%" warn_below="20"/>
    <field id="temp" unit="C" warn_above="55"/>
  </telemetry>
  <safety>
    <estop required="true" topic="/rrcf/go2/estop" qos="2"/>
    <watchdog timeout_ms="500" action="halt"/>
    <speed_limit max_vx="1.5" max_wz="2.0"/>
  </safety>
  <transport>
    <endpoint role="operator_cmd" protocol="rrcf_mqtt" topic="/rrcf/go2/cmd" broker="${MQTT_BROKER}"/>
    <endpoint role="telemetry" protocol="mqtt" topic="/rrcf/go2/state" frequency_hz="10"/>
  </transport>
  <extensions/>
</rrcf>
"""


def test_parses_meta_and_category():
    profile = parse_rrcf_string(SAMPLE_RRCF)
    assert profile.name == "Test Go2"
    assert profile.vendor == "Unitree Robotics"
    assert profile.category == "legged"
    assert profile.slug == "test_go2"


def test_speed_limit_overrides_locomotion_max():
    profile = parse_rrcf_string(SAMPLE_RRCF)
    # <speed_limit> declares max_vx/max_wz explicitly — must win over
    # <locomotion>'s values even though both happen to agree here.
    assert profile.safety.max_vx == 1.5
    assert profile.safety.max_wz == 2.0
    # max_vy has no <speed_limit> override — falls back to <locomotion>.
    assert profile.safety.max_vy == 0.5


def test_safety_fields():
    profile = parse_rrcf_string(SAMPLE_RRCF)
    assert profile.safety.estop_required is True
    assert profile.safety.estop_topic == "/rrcf/go2/estop"
    assert profile.safety.estop_qos == 2
    assert profile.safety.watchdog_timeout_ms == 500


def test_skills_and_telemetry_fields():
    profile = parse_rrcf_string(SAMPLE_RRCF)
    assert profile.skills == ["sit", "stand"]
    assert profile.telemetry_fields == ["battery", "temp"]


def test_endpoints():
    profile = parse_rrcf_string(SAMPLE_RRCF)
    operator_ep = profile.endpoint("operator_cmd")
    telemetry_ep = profile.endpoint("telemetry")
    assert operator_ep is not None
    assert operator_ep.topic == "/rrcf/go2/cmd"
    assert operator_ep.broker == "${MQTT_BROKER}"
    assert telemetry_ep is not None
    assert telemetry_ep.frequency_hz == 10.0


def test_missing_rrcf_element_raises():
    import pytest

    with pytest.raises(ValueError):
        parse_rrcf_string("<robot><joint name='x'/></robot>")


def test_defaults_when_blocks_absent():
    minimal = """<?xml version="1.0"?>
    <rrcf version="1.0"><meta><name>Bare Bot</name></meta></rrcf>"""
    profile = parse_rrcf_string(minimal)
    assert profile.name == "Bare Bot"
    assert profile.category == "custom"
    assert profile.safety.watchdog_timeout_ms == 500
    assert profile.endpoints == []
    assert profile.skills == []
