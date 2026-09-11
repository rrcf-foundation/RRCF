"""Layer 1 — declaration-time conformance.

Validates that a `.rrcf` declaration is structurally valid, declares every
field its category makes mandatory, and satisfies the self-description
contract on every field it declares.

What this layer proves: the declaration is complete and internally consistent.

What it does NOT prove: that the robot actually publishes any of it. A vendor
can declare `estop_state` and never emit it, and this layer will pass. That
gap is the entire reason layer 2 (runtime.py) exists.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .projection import ProjectionError, project_file

def _conformance_dir() -> Path:
    """Locate the directory holding profiles/ and schema/.

    The profiles and schema live at stable, citable repo paths
    (conformance/profiles, conformance/schema) rather than inside the Python
    package, because the website and the spec link to those URLs. That means
    this tool expects a repo checkout — `pip install -e conformance` keeps the
    paths valid. RRCF_CONFORMANCE_DIR overrides for unusual layouts.
    """
    override = os.environ.get("RRCF_CONFORMANCE_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


CONFORMANCE_DIR = _conformance_dir()
SCHEMA_PATH = CONFORMANCE_DIR / "schema" / "rrcf-declaration.schema.json"
PROFILES_PATH = CONFORMANCE_DIR / "profiles" / "category-profiles.json"


@dataclass(frozen=True)
class Finding:
    level: str  # "error" | "warning"
    code: str
    message: str
    where: str = ""

    def render(self) -> str:
        location = f" [{self.where}]" if self.where else ""
        return f"{self.level.upper():7} {self.code}{location}: {self.message}"


@dataclass
class Report:
    target: str
    findings: list[Finding]

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def render(self) -> str:
        lines = [f"{'PASS' if self.ok else 'FAIL'}  {self.target}"]
        lines.extend("      " + f.render() for f in self.findings)
        return "\n".join(lines)


def load_profiles() -> dict[str, Any]:
    return json.loads(PROFILES_PATH.read_text(encoding="utf-8"))


def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _schema_findings(declaration: dict[str, Any]) -> list[Finding]:
    try:
        from jsonschema import Draft202012Validator
    except ModuleNotFoundError:
        return [
            Finding(
                "error",
                "no-validator",
                "jsonschema is not installed — run: pip install -r conformance/requirements.txt",
            )
        ]

    schema = load_schema()
    validator = Draft202012Validator(schema)
    findings = []
    for error in sorted(validator.iter_errors(declaration), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in error.absolute_path) or "<root>"
        message = _describe(error)
        clause = _clause_title(schema, error)
        if clause:
            message = f"{message} (profile clause: {clause})"
        findings.append(Finding("error", "schema", message, where))
    return findings


def _clause_title(schema: dict[str, Any], error: Any) -> str:
    """Nearest titled ancestor along the failing schema path.

    Without this a vendor sees "does not contain items matching the given
    schema" with no indication of which category profile clause rejected them.
    """
    node: Any = schema
    title = ""
    for step in error.absolute_schema_path:
        try:
            node = node[step]
        except (KeyError, IndexError, TypeError):
            break
        if isinstance(node, dict) and node.get("title"):
            title = str(node["title"])
    return title


def _describe(error: Any) -> str:
    """Turn opaque `contains` failures into the requirement that was missed."""
    if error.validator != "contains":
        return error.message

    schema = error.schema or {}

    # The generated schema annotates the non-obvious clauses with $comment
    # explaining *why* the requirement exists. Prefer that over anything
    # reconstructed, because it states the rationale, not just the rule.
    comment = schema.get("$comment")
    if isinstance(comment, str) and comment:
        return comment

    expected = schema.get("contains")
    if not isinstance(expected, dict):
        return error.message

    # Axis lists: {"contains": {"const": "vz"}}
    if "const" in expected:
        return (
            f"required value {expected['const']!r} is missing — declared: "
            f"{error.instance!r}"
        )

    # Telemetry fields: {"contains": {"properties": {"id": {"const": ...}, ...}}}
    props = expected.get("properties")
    if isinstance(props, dict):
        wanted = {
            name: spec["const"]
            for name, spec in props.items()
            if isinstance(spec, dict) and "const" in spec
        }
        if wanted:
            field_id = wanted.pop("id", None)
            detail = ", ".join(f"{k}={v!r}" for k, v in sorted(wanted.items()))
            declared = [
                f.get("id")
                for f in (error.instance or [])
                if isinstance(f, dict) and f.get("id")
            ]
            if field_id is None:
                return f"no entry satisfies {detail}"
            constraint = f" with {detail}" if detail else ""
            if field_id in declared:
                return (
                    f"telemetry field {field_id!r} is declared but does not match "
                    f"the profile{constraint}"
                )
            return (
                f"mandatory telemetry field {field_id!r}{constraint} is not declared "
                f"— declared fields: {declared}"
            )

        # Standardized enum value sets nest one level deeper.
        values = expected.get("allOf")
        if isinstance(values, list):
            missing = [
                v["const"]
                for v in values
                if isinstance(v, dict) and isinstance(v.get("contains"), dict)
                and "const" in v["contains"]
            ]
            if missing:
                return f"enum must enumerate {missing} — declared: {error.instance!r}"

    return error.message


def _self_description_findings(declaration: dict[str, Any]) -> Iterable[Finding]:
    """Cross-property rules JSON Schema cannot express."""
    fields = declaration.get("telemetry") or []

    seen: dict[str, int] = {}
    for index, field in enumerate(fields):
        if not isinstance(field, dict):
            continue
        field_id = field.get("id")
        where = f"telemetry/{field_id or index}"

        if isinstance(field_id, str):
            if field_id in seen:
                yield Finding(
                    "error",
                    "duplicate-field",
                    f"field id '{field_id}' is declared more than once "
                    f"(also at telemetry/{seen[field_id]}) — a consumer cannot tell "
                    "which declaration governs the value on the wire",
                    where,
                )
            else:
                seen[field_id] = index

        low, high = field.get("min"), field.get("max")
        numeric_range = isinstance(low, (int, float)) and isinstance(high, (int, float))
        if numeric_range and low >= high:
            yield Finding(
                "error",
                "bad-range",
                f"min ({low}) must be strictly less than max ({high})",
                where,
            )

        for attr in ("warn_below", "warn_above"):
            threshold = field.get(attr)
            if isinstance(threshold, (int, float)) and numeric_range:
                if not (low <= threshold <= high):
                    yield Finding(
                        "error",
                        "warn-outside-range",
                        f"{attr} ({threshold}) falls outside the declared range "
                        f"[{low}, {high}] — the warning could never fire",
                        where,
                    )

        # Converter output ships TODO placeholders on purpose — a physical
        # description file cannot know a sensor's unit or range. Say so plainly
        # rather than leaving a bare "'TODO' is not of type 'number'".
        placeholders = sorted(
            attr
            for attr, value in field.items()
            if isinstance(value, str) and value.strip().upper() in ("TODO", "FIXME", "TBD")
        )
        if placeholders:
            yield Finding(
                "error",
                "placeholder-not-filled",
                f"unfilled placeholder on {', '.join(placeholders)} — a generated "
                "draft is not a conformant declaration until the real unit and "
                "range are supplied",
                where,
            )

        unit = field.get("unit")
        if isinstance(unit, str) and unit.strip() == "" and "unit" in field:
            yield Finding(
                "error",
                "empty-unit",
                "unit is present but empty — use '1' for a dimensionless ratio, "
                "or omit the attribute only for boolean/string/enum fields",
                where,
            )


def _rate_findings(declaration: dict[str, Any], profiles: dict[str, Any]) -> Iterable[Finding]:
    minimum = profiles["universal"]["minTelemetryHz"]
    endpoints = (declaration.get("transport") or {}).get("endpoints") or []
    telemetry_endpoints = [
        e for e in endpoints if isinstance(e, dict) and e.get("role") == "telemetry"
    ]
    endpoint_rate = next(
        (
            e["frequency_hz"]
            for e in telemetry_endpoints
            if isinstance(e.get("frequency_hz"), (int, float))
        ),
        None,
    )

    for endpoint in telemetry_endpoints:
        rate = endpoint.get("frequency_hz")
        if isinstance(rate, (int, float)) and rate < minimum:
            yield Finding(
                "error",
                "rate-too-low",
                f"telemetry endpoint declares {rate} Hz, below the required minimum "
                f"of {minimum} Hz",
                f"transport/{endpoint.get('role')}",
            )

    for index, field in enumerate(declaration.get("telemetry") or []):
        if not isinstance(field, dict):
            continue
        where = f"telemetry/{field.get('id', index)}"
        rate = field.get("frequency_hz")
        if rate is None:
            if endpoint_rate is None:
                yield Finding(
                    "error",
                    "no-rate",
                    "no publish rate is established for this field: it declares no "
                    "frequency_hz and no telemetry endpoint declares one either",
                    where,
                )
            continue
        if isinstance(rate, (int, float)) and rate < minimum:
            yield Finding(
                "error",
                "rate-too-low",
                f"declares {rate} Hz, below the required minimum of {minimum} Hz",
                where,
            )


def _safety_findings(declaration: dict[str, Any]) -> Iterable[Finding]:
    safety = declaration.get("safety") or {}
    limits = ((declaration.get("primary") or {}).get("locomotion") or {}).get("limits") or {}
    speed_limit = safety.get("speed_limit") or {}

    for axis, ceiling in speed_limit.items():
        capability = limits.get(axis)
        if isinstance(ceiling, (int, float)) and isinstance(capability, (int, float)):
            if ceiling > capability:
                yield Finding(
                    "error",
                    "limit-exceeds-capability",
                    f"safety speed_limit {axis}={ceiling} exceeds the declared "
                    f"locomotion capability {axis}={capability} — a controller "
                    "clamping to the safety limit would still command beyond the "
                    "robot's declared envelope",
                    "safety/speed_limit",
                )

    for axis in limits:
        if speed_limit and axis not in speed_limit:
            yield Finding(
                "warning",
                "unbounded-axis",
                f"locomotion declares {axis} but safety/speed_limit does not bound it",
                "safety/speed_limit",
            )


def _skill_findings(declaration: dict[str, Any]) -> Iterable[Finding]:
    seen: set[str] = set()
    for index, skill in enumerate(declaration.get("skills") or []):
        if not isinstance(skill, dict):
            continue
        skill_id = skill.get("id")
        if not isinstance(skill_id, str):
            continue
        if skill_id in seen:
            yield Finding(
                "error",
                "duplicate-skill",
                f"skill id '{skill_id}' is declared more than once",
                f"skills/{skill_id}",
            )
        seen.add(skill_id)

        if not skill.get("label"):
            yield Finding(
                "warning",
                "unlabelled-skill",
                f"skill '{skill_id}' has no label — an operator UI has nothing to "
                "render but the raw ID",
                f"skills/{skill_id}",
            )


def lint_declaration(
    declaration: dict[str, Any], profiles: dict[str, Any] | None = None
) -> list[Finding]:
    profiles = profiles or load_profiles()
    findings = _schema_findings(declaration)
    findings.extend(_self_description_findings(declaration))
    findings.extend(_rate_findings(declaration, profiles))
    findings.extend(_safety_findings(declaration))
    findings.extend(_skill_findings(declaration))
    return findings


def lint_file(path: str | Path) -> Report:
    target = str(path)
    try:
        declaration = project_file(path)
    except ProjectionError as exc:
        return Report(target, [Finding("error", "projection", str(exc))])
    except OSError as exc:
        return Report(target, [Finding("error", "io", str(exc))])
    return Report(target, lint_declaration(declaration))
