"""Tests for the RRCF conformance layers.

The point of these tests is not coverage for its own sake. Each one pins a
claim the standard makes, so that a claim cannot quietly stop being true:

- the shipped examples are what we say they are (conformant / not);
- every category in the profiles is actually enforced by the schema;
- the generated schema cannot drift from the profiles;
- the self-description contract rejects under-described fields;
- category-awareness is real (a fixed arm is not held to mobile-base rules);
- layer 1 passing does not imply layer 2 passing — the gap between
  "declared" and "published" is the whole reason layer 2 exists.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

CONFORMANCE_DIR = Path(__file__).resolve().parents[1]
EXAMPLES = CONFORMANCE_DIR / "examples"

sys.path.insert(0, str(CONFORMANCE_DIR))

from rrcf_conformance import (  # noqa: E402
    check_session_data,
    lint_declaration,
    lint_file,
    load_session,
    project_file,
    project_string,
)
from rrcf_conformance.lint import load_profiles, load_schema  # noqa: E402


def codes(findings) -> set[str]:
    return {f.code for f in findings}


def errors(findings) -> list:
    return [f for f in findings if f.level == "error"]


# --------------------------------------------------------------------------
# Shipped examples
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["unitree-go2-z1.rrcf", "ur5-manipulator.rrcf"])
def test_valid_examples_lint_clean(name):
    report = lint_file(EXAMPLES / name)
    assert report.ok, report.render()
    assert report.warnings == [], report.render()


def test_invalid_example_is_rejected():
    report = lint_file(EXAMPLES / "invalid-aerial.rrcf")
    assert not report.ok

    found = codes(report.findings)
    assert "schema" in found
    assert "duplicate-field" in found
    assert "warn-outside-range" in found
    assert "rate-too-low" in found
    assert "limit-exceeds-capability" in found

    # Every planted defect must be named, not just counted.
    blob = report.render()
    for expected in ["'health'", "'altitude'", "'rssi'", "'vz'", "watchdog"]:
        assert expected in blob, f"{expected} not reported in:\n{blob}"


def test_conformant_session_passes():
    from rrcf_conformance import check_session_files

    report = check_session_files(
        EXAMPLES / "unitree-go2-z1.rrcf", EXAMPLES / "go2-session.jsonl"
    )
    assert report.ok, report.render()
    assert report.warnings == [], report.render()


def test_noncompliant_session_is_rejected():
    from rrcf_conformance import check_session_files

    report = check_session_files(
        EXAMPLES / "unitree-go2-z1.rrcf", EXAMPLES / "go2-session-noncompliant.jsonl"
    )
    assert not report.ok
    found = codes(report.findings)
    for expected in {
        "declared-not-published",
        "rate-shortfall",
        "value-out-of-range",
        "value-not-declared",
        "type-mismatch",
        "twist-missing",
        "axis-not-normalized",
        "watchdog-gap",
        "undeclared-field",
    }:
        assert expected in found, f"{expected} missing from {sorted(found)}"


# --------------------------------------------------------------------------
# The declared-vs-published gap: the reason layer 2 exists
# --------------------------------------------------------------------------


def test_declaration_can_pass_layer1_and_fail_layer2():
    """A vendor can declare estop_state and never publish it.

    Layer 1 has no way to know. If this test ever fails because layer 1
    started catching it, that would mean layer 1 gained runtime knowledge it
    cannot legitimately have.
    """
    declaration_path = EXAMPLES / "unitree-go2-z1.rrcf"
    assert lint_file(declaration_path).ok

    declaration = project_file(declaration_path)
    session = load_session(EXAMPLES / "go2-session-noncompliant.jsonl")
    findings = check_session_data(declaration, session)

    not_published = [f for f in findings if f.code == "declared-not-published"]
    assert any("estop_state" in f.where for f in not_published)


# --------------------------------------------------------------------------
# Profiles <-> schema integrity
# --------------------------------------------------------------------------


def test_generated_schema_is_current():
    """CI gate: the checked-in schema must match the profiles."""
    result = subprocess.run(
        [sys.executable, str(CONFORMANCE_DIR / "tools" / "gen_schema.py"), "--check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_every_category_is_enforced_or_explicitly_open():
    """No category may be silently unenforced."""
    profiles = load_profiles()
    schema = load_schema()
    titles = {clause.get("title", "") for clause in schema["allOf"]}

    for name, entry in profiles["categories"].items():
        has_requirements = bool(entry["telemetry"]) or bool(entry["locomotionAxes"])
        enforced = f"category profile: {name}" in titles
        assert enforced == has_requirements, (
            f"category '{name}': has_requirements={has_requirements} but "
            f"enforced={enforced}"
        )


def test_universal_fields_are_enforced_for_every_category():
    profiles = load_profiles()
    universal = [f["id"] for f in profiles["universal"]["telemetry"]]
    schema = load_schema()
    titles = {clause.get("title", "") for clause in schema["allOf"]}
    for field_id in universal:
        assert f"universal telemetry: {field_id}" in titles


@pytest.mark.parametrize("category", sorted(load_profiles()["categories"]))
def test_category_mandatory_fields_are_actually_required(category):
    """Drop each mandatory field in turn; the schema must object."""
    profiles = load_profiles()
    entry = profiles["categories"][category]
    mandatory = profiles["universal"]["telemetry"] + entry["telemetry"]

    baseline = _synthesize(category, profiles)
    assert errors(lint_declaration(baseline, profiles)) == [], (
        f"synthesized baseline for '{category}' should be conformant: "
        f"{lint_declaration(baseline, profiles)}"
    )

    for spec in mandatory:
        stripped = json.loads(json.dumps(baseline))
        stripped["telemetry"] = [
            f for f in stripped["telemetry"] if f["id"] != spec["id"]
        ]
        found = errors(lint_declaration(stripped, profiles))
        assert found, (
            f"removing mandatory field '{spec['id']}' from category "
            f"'{category}' produced no error"
        )


def test_manipulator_is_not_held_to_mobile_base_rules():
    """Category-awareness must be real, not decorative."""
    profiles = load_profiles()
    manipulator = profiles["categories"]["manipulator"]

    assert manipulator["locomotionAxes"] == []
    assert manipulator["requiresTwist"] is False
    assert "battery" not in {f["id"] for f in manipulator["telemetry"]}

    # And the shipped example proves it end to end.
    assert lint_file(EXAMPLES / "ur5-manipulator.rrcf").ok


# --------------------------------------------------------------------------
# Self-description contract
# --------------------------------------------------------------------------


def _synthesize(category: str, profiles: dict) -> dict:
    """Build a minimal conformant declaration for a category."""
    fields = []
    for spec in profiles["universal"]["telemetry"] + profiles["categories"][category][
        "telemetry"
    ]:
        field = {"id": spec["id"], "type": spec["type"]}
        if spec["type"] in ("number", "integer", "vector3"):
            field["unit"] = spec.get("unit", "1")
            field["min"] = 0
            field["max"] = 1000
        if spec["type"] == "enum":
            field["values"] = spec.get("values", ["a", "b"])
        fields.append(field)

    axes = profiles["categories"][category]["locomotionAxes"]
    declaration = {
        "version": profiles["rrcfVersion"],
        "primary": {"category": category},
        "telemetry": fields,
        "safety": {
            "estop": {"required": True, "topic": "/rrcf/x/estop"},
            "watchdog": {"timeout_ms": 500, "action": "halt"},
        },
        "transport": {
            "endpoints": [
                {"role": "operator_cmd", "protocol": "rrcf_mqtt", "topic": "/rrcf/x/cmd"},
                {
                    "role": "telemetry",
                    "protocol": "mqtt",
                    "topic": "/rrcf/x/state",
                    "frequency_hz": 10,
                },
            ]
        },
    }
    if axes:
        declaration["primary"]["locomotion"] = {"axes": list(axes)}
    return declaration


@pytest.mark.parametrize(
    "drop,expected_substring",
    [("unit", "unit"), ("min", "min"), ("max", "max")],
)
def test_numeric_field_must_self_describe(drop, expected_substring):
    profiles = load_profiles()
    declaration = _synthesize("wheeled", profiles)
    for field in declaration["telemetry"]:
        if field["id"] == "speed":
            field.pop(drop)
    found = errors(lint_declaration(declaration, profiles))
    assert any(expected_substring in f.message for f in found), found


def test_enum_field_must_enumerate_its_values():
    profiles = load_profiles()
    declaration = _synthesize("full_humanoid", profiles)
    for field in declaration["telemetry"]:
        if field["id"] == "balance":
            field.pop("values")
    found = errors(lint_declaration(declaration, profiles))
    assert any("values" in f.message for f in found), found


def test_inverted_range_is_rejected():
    profiles = load_profiles()
    declaration = _synthesize("wheeled", profiles)
    for field in declaration["telemetry"]:
        if field["id"] == "speed":
            field["min"], field["max"] = 10, 2
    found = errors(lint_declaration(declaration, profiles))
    assert "bad-range" in {f.code for f in found}


def test_unreachable_warning_threshold_is_rejected():
    profiles = load_profiles()
    declaration = _synthesize("wheeled", profiles)
    for field in declaration["telemetry"]:
        if field["id"] == "battery":
            field["warn_below"] = -50
    found = errors(lint_declaration(declaration, profiles))
    assert "warn-outside-range" in {f.code for f in found}


def test_telemetry_endpoint_is_mandatory():
    """You cannot safely command what you cannot observe."""
    profiles = load_profiles()
    declaration = _synthesize("wheeled", profiles)
    declaration["transport"]["endpoints"] = [
        e for e in declaration["transport"]["endpoints"] if e["role"] != "telemetry"
    ]
    found = errors(lint_declaration(declaration, profiles))
    assert found, "a declaration with no telemetry endpoint was accepted"


def test_command_endpoint_is_mandatory():
    profiles = load_profiles()
    declaration = _synthesize("wheeled", profiles)
    declaration["transport"]["endpoints"] = [
        e for e in declaration["transport"]["endpoints"] if e["role"] != "operator_cmd"
    ]
    found = errors(lint_declaration(declaration, profiles))
    assert found, "a declaration with no command endpoint was accepted"


def test_field_without_any_rate_is_rejected():
    profiles = load_profiles()
    declaration = _synthesize("wheeled", profiles)
    for endpoint in declaration["transport"]["endpoints"]:
        endpoint.pop("frequency_hz", None)
    found = errors(lint_declaration(declaration, profiles))
    assert "no-rate" in {f.code for f in found}


# --------------------------------------------------------------------------
# Projection
# --------------------------------------------------------------------------


def test_projection_coerces_types():
    declaration = project_file(EXAMPLES / "unitree-go2-z1.rrcf")
    battery = next(f for f in declaration["telemetry"] if f["id"] == "battery")
    assert battery["min"] == 0 and battery["max"] == 100
    assert isinstance(battery["warn_below"], int)
    assert declaration["primary"]["locomotion"]["axes"] == ["vx", "vy", "wz"]
    assert declaration["safety"]["estop"]["required"] is True
    assert declaration["safety"]["watchdog"]["timeout_ms"] == 500
    health = next(f for f in declaration["telemetry"] if f["id"] == "health")
    assert "disconnected" in health["values"]


def test_projection_finds_embedded_rrcf_block():
    """A declaration may be embedded in a physical description file."""
    host = """<?xml version="1.0"?>
    <robot name="demo">
      <link name="base"/>
      <rrcf version="1.0">
        <primary category="wheeled"><locomotion axes="vx wz"/></primary>
      </rrcf>
    </robot>"""
    declaration = project_string(host)
    assert declaration["primary"]["category"] == "wheeled"
    assert declaration["primary"]["locomotion"]["axes"] == ["vx", "wz"]


def test_projection_rejects_non_rrcf_document():
    from rrcf_conformance import ProjectionError

    with pytest.raises(ProjectionError):
        project_string("<robot><link name='base'/></robot>")


# --------------------------------------------------------------------------
# CLI contract
# --------------------------------------------------------------------------


def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "rrcf_conformance", *args],
        cwd=CONFORMANCE_DIR,
        capture_output=True,
        text=True,
    )


def test_cli_exit_codes():
    assert _cli("lint", "examples/unitree-go2-z1.rrcf").returncode == 0
    assert _cli("lint", "examples/invalid-aerial.rrcf").returncode == 1
    assert (
        _cli(
            "check-session",
            "examples/unitree-go2-z1.rrcf",
            "examples/go2-session.jsonl",
        ).returncode
        == 0
    )
    assert (
        _cli(
            "check-session",
            "examples/unitree-go2-z1.rrcf",
            "examples/go2-session-noncompliant.jsonl",
        ).returncode
        == 1
    )


def test_cli_json_output_is_parseable_in_either_flag_position():
    for args in (
        ("--json", "lint", "examples/invalid-aerial.rrcf"),
        ("lint", "examples/invalid-aerial.rrcf", "--json"),
    ):
        result = _cli(*args)
        payload = json.loads(result.stdout)
        assert payload[0]["ok"] is False
        assert payload[0]["findings"]


def test_cli_lint_accepts_a_directory():
    result = _cli("lint", "examples")
    # examples/ holds both conformant and deliberately invalid declarations.
    assert result.returncode == 1
    assert "unitree-go2-z1.rrcf" in result.stdout
    assert "invalid-aerial.rrcf" in result.stdout


def test_cli_profiles_lists_every_category():
    result = _cli("profiles")
    assert result.returncode == 0
    for category in load_profiles()["categories"]:
        assert category in result.stdout
