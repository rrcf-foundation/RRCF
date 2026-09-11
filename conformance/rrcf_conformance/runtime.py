"""Layer 2 — runtime conformance.

Layer 1 proves a declaration *says* the right things. This layer proves the
robot *does* them: that every declared field actually appears on the wire, at
or above its declared rate, carrying values inside its declared range.

This is the layer that catches "compliant on paper, not compliant in
practice" — a vendor declaring `estop_state` and never publishing it, or
declaring 10 Hz and shipping 2 Hz, or declaring `battery` in percent and
emitting volts.

Input is a recorded session as JSON Lines: one wire message per line, exactly
as transmitted. Command messages carry `"type": "cmd"`; telemetry messages
carry `"type": "state"`. A session can be produced by any MQTT/WebSocket tap
or exported from an MCAP recording — nothing RRCF-specific is required to
capture one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from typing import Any, Iterable

from .lint import Finding, Report, load_profiles
from .projection import ProjectionError, project_file

# A robot publishing slightly under its declared rate is a real finding, but
# scheduler jitter in a short capture should not fail an otherwise sound
# implementation. Allow a 10% shortfall.
RATE_TOLERANCE = 0.9

# Axes the wire format normalizes to [-1, 1].
NORMALIZED_AXES = ("lx", "ly", "rx", "ry")


class SessionError(ValueError):
    """The session capture could not be read."""


@dataclass
class Session:
    commands: list[dict[str, Any]] = dataclass_field(default_factory=list)
    states: list[dict[str, Any]] = dataclass_field(default_factory=list)
    malformed: list[tuple[int, str]] = dataclass_field(default_factory=list)

    @property
    def span_seconds(self) -> float | None:
        stamps = [
            m["ts"]
            for m in (*self.commands, *self.states)
            if isinstance(m.get("ts"), (int, float))
        ]
        if len(stamps) < 2:
            return None
        span = (max(stamps) - min(stamps)) / 1000.0
        return span if span > 0 else None


def load_session(path: str | Path) -> Session:
    session = Session()
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise SessionError(str(exc)) from exc

    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            message = json.loads(stripped)
        except json.JSONDecodeError as exc:
            session.malformed.append((lineno, str(exc)))
            continue
        if not isinstance(message, dict):
            session.malformed.append((lineno, "message is not a JSON object"))
            continue
        kind = message.get("type")
        if kind == "cmd":
            session.commands.append(message)
        elif kind in ("state", "telemetry"):
            session.states.append(message)
        else:
            session.malformed.append(
                (lineno, f"unknown message type {kind!r} — expected 'cmd' or 'state'")
            )
    return session


def _observed(message: dict[str, Any], field_id: str) -> tuple[bool, Any]:
    """Telemetry values may sit at the top level or under a `telemetry` object."""
    if field_id in message:
        return True, message[field_id]
    nested = message.get("telemetry")
    if isinstance(nested, dict) and field_id in nested:
        return True, nested[field_id]
    return False, None


def _is_vector3(value: Any) -> bool:
    if isinstance(value, (list, tuple)):
        return len(value) == 3 and all(isinstance(v, (int, float)) for v in value)
    if isinstance(value, dict):
        return all(isinstance(value.get(axis), (int, float)) for axis in ("x", "y", "z"))
    return False


def _vector_components(value: Any) -> list[float]:
    if isinstance(value, (list, tuple)):
        return [float(v) for v in value]
    return [float(value[axis]) for axis in ("x", "y", "z")]


def _check_field(
    spec: dict[str, Any], session: Session, declared_rate: float | None
) -> Iterable[Finding]:
    field_id = spec.get("id")
    if not isinstance(field_id, str):
        return
    where = f"telemetry/{field_id}"
    field_type = spec.get("type")

    hits = []
    for message in session.states:
        present, value = _observed(message, field_id)
        if present:
            hits.append(value)

    if not hits:
        yield Finding(
            "error",
            "declared-not-published",
            "declared in the .rrcf but never published in this session — the "
            "declaration promises a field the robot does not emit",
            where,
        )
        return

    missing = len(session.states) - len(hits)
    if missing:
        yield Finding(
            "warning",
            "intermittent-field",
            f"absent from {missing} of {len(session.states)} telemetry messages",
            where,
        )

    # Rate.
    span = session.span_seconds
    if declared_rate is not None:
        if span is None:
            yield Finding(
                "warning",
                "rate-unverifiable",
                "session is too short to measure rate — capture at least two "
                "timestamped messages spanning a non-zero interval",
                where,
            )
        else:
            observed_rate = len(hits) / span
            if observed_rate < declared_rate * RATE_TOLERANCE:
                yield Finding(
                    "error",
                    "rate-shortfall",
                    f"declares {declared_rate:g} Hz but published "
                    f"{observed_rate:.2f} Hz over {span:.2f}s "
                    f"({len(hits)} samples)",
                    where,
                )

    # Values against the declared self-description.
    low, high = spec.get("min"), spec.get("max")
    allowed = spec.get("values")

    for value in hits:
        if field_type in ("number", "integer"):
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                yield Finding(
                    "error",
                    "type-mismatch",
                    f"declared {field_type} but emitted {type(value).__name__} ({value!r})",
                    where,
                )
                break
            if isinstance(low, (int, float)) and isinstance(high, (int, float)):
                if not (low <= value <= high):
                    yield Finding(
                        "error",
                        "value-out-of-range",
                        f"emitted {value!r}, outside the declared range [{low}, {high}]",
                        where,
                    )
                    break
        elif field_type == "boolean":
            if not isinstance(value, bool):
                yield Finding(
                    "error",
                    "type-mismatch",
                    f"declared boolean but emitted {type(value).__name__} ({value!r})",
                    where,
                )
                break
        elif field_type == "enum":
            if not isinstance(value, str):
                yield Finding(
                    "error",
                    "type-mismatch",
                    f"declared enum but emitted {type(value).__name__} ({value!r})",
                    where,
                )
                break
            if isinstance(allowed, list) and value not in allowed:
                yield Finding(
                    "error",
                    "value-not-declared",
                    f"emitted '{value}', which is not in the declared value set "
                    f"{allowed} — a generic UI has no way to render it",
                    where,
                )
                break
        elif field_type == "vector3":
            if not _is_vector3(value):
                yield Finding(
                    "error",
                    "type-mismatch",
                    f"declared vector3 but emitted {value!r} — expected [x, y, z] "
                    "or {x, y, z} with numeric components",
                    where,
                )
                break
            if isinstance(low, (int, float)) and isinstance(high, (int, float)):
                out = [c for c in _vector_components(value) if not (low <= c <= high)]
                if out:
                    yield Finding(
                        "error",
                        "value-out-of-range",
                        f"component(s) {out} fall outside the declared range "
                        f"[{low}, {high}]",
                        where,
                    )
                    break


def _check_undeclared(declaration: dict[str, Any], session: Session) -> Iterable[Finding]:
    declared = {
        f.get("id")
        for f in (declaration.get("telemetry") or [])
        if isinstance(f, dict)
    }
    envelope = {"rrcf", "type", "ts", "category", "seq", "telemetry"}
    seen: set[str] = set()
    for message in session.states:
        for key, value in message.items():
            if key in envelope or key in declared:
                continue
            seen.add(key)
        nested = message.get("telemetry")
        if isinstance(nested, dict):
            seen.update(k for k in nested if k not in declared)

    for key in sorted(seen):
        yield Finding(
            "warning",
            "undeclared-field",
            f"published but not declared — a generic consumer cannot interpret it, "
            f"because there is no unit, type, or range to read",
            f"wire/{key}",
        )


def _check_commands(
    declaration: dict[str, Any], session: Session, profiles: dict[str, Any]
) -> Iterable[Finding]:
    if not session.commands:
        yield Finding(
            "warning",
            "no-commands",
            "session contains no command messages, so command-side rules "
            "(twist, normalization, watchdog cadence) were not exercised",
            "wire/cmd",
        )
        return

    category = (declaration.get("primary") or {}).get("category")
    profile = (profiles.get("categories") or {}).get(category) or {}
    required = list(profiles["universal"]["command"]["requiredFields"])
    requires_twist = bool(profile.get("requiresTwist"))

    missing_counts: dict[str, int] = {}
    twist_missing = 0
    bad_category = 0
    out_of_range: set[str] = set()

    for message in session.commands:
        for name in required:
            if name not in message:
                missing_counts[name] = missing_counts.get(name, 0) + 1
        if requires_twist and "twist" not in message:
            twist_missing += 1
        if category and message.get("category") not in (None, category):
            bad_category += 1
        for axis in NORMALIZED_AXES:
            value = message.get(axis)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if not (-1.0 <= value <= 1.0):
                    out_of_range.add(axis)

    total = len(session.commands)
    for name, count in sorted(missing_counts.items()):
        yield Finding(
            "error",
            "command-field-missing",
            f"'{name}' is required on every command message but is absent from "
            f"{count} of {total}",
            "wire/cmd",
        )

    if twist_missing:
        yield Finding(
            "error",
            "twist-missing",
            f"category '{category}' declares locomotion axes, so twist is required "
            f"on every command message — absent from {twist_missing} of {total}",
            "wire/cmd",
        )

    if bad_category:
        yield Finding(
            "error",
            "category-mismatch",
            f"{bad_category} of {total} command messages carry a category other "
            f"than the declared '{category}'",
            "wire/cmd",
        )

    for axis in sorted(out_of_range):
        yield Finding(
            "error",
            "axis-not-normalized",
            f"'{axis}' carries values outside [-1.0, 1.0]",
            "wire/cmd",
        )

    yield from _check_watchdog(declaration, session)


def _check_watchdog(declaration: dict[str, Any], session: Session) -> Iterable[Finding]:
    watchdog = (declaration.get("safety") or {}).get("watchdog") or {}
    timeout_ms = watchdog.get("timeout_ms")
    if not isinstance(timeout_ms, (int, float)):
        return

    stamps = sorted(
        m["ts"] for m in session.commands if isinstance(m.get("ts"), (int, float))
    )
    if len(stamps) < 2:
        return

    gaps = [b - a for a, b in zip(stamps, stamps[1:]) if b - a > timeout_ms]
    if gaps:
        yield Finding(
            "warning",
            "watchdog-gap",
            f"{len(gaps)} command gap(s) exceeded the declared watchdog timeout of "
            f"{timeout_ms:g} ms (largest {max(gaps):g} ms) — a conforming robot must "
            "have entered its safe state at each gap. Confirm the capture shows that, "
            "rather than continued motion",
            "safety/watchdog",
        )


def check_session_data(
    declaration: dict[str, Any], session: Session, profiles: dict[str, Any] | None = None
) -> list[Finding]:
    profiles = profiles or load_profiles()
    findings: list[Finding] = []

    for lineno, reason in session.malformed:
        findings.append(Finding("error", "malformed-message", reason, f"line {lineno}"))

    if not session.states:
        findings.append(
            Finding(
                "error",
                "no-telemetry",
                "session contains no telemetry messages, so nothing about the "
                "robot's published state could be verified",
                "wire/state",
            )
        )
        findings.extend(_check_commands(declaration, session, profiles))
        return findings

    endpoint_rate = next(
        (
            e.get("frequency_hz")
            for e in ((declaration.get("transport") or {}).get("endpoints") or [])
            if isinstance(e, dict)
            and e.get("role") == "telemetry"
            and isinstance(e.get("frequency_hz"), (int, float))
        ),
        None,
    )

    for spec in declaration.get("telemetry") or []:
        if not isinstance(spec, dict):
            continue
        declared_rate = spec.get("frequency_hz")
        if not isinstance(declared_rate, (int, float)):
            declared_rate = endpoint_rate
        findings.extend(_check_field(spec, session, declared_rate))

    findings.extend(_check_undeclared(declaration, session))
    findings.extend(_check_commands(declaration, session, profiles))
    return findings


def check_session_files(declaration_path: str | Path, session_path: str | Path) -> Report:
    target = f"{session_path} against {declaration_path}"
    try:
        declaration = project_file(declaration_path)
    except (ProjectionError, OSError) as exc:
        return Report(target, [Finding("error", "projection", str(exc))])
    try:
        session = load_session(session_path)
    except SessionError as exc:
        return Report(target, [Finding("error", "io", str(exc))])
    return Report(target, check_session_data(declaration, session))
