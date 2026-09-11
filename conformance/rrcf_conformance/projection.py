"""Project an XML `.rrcf` declaration into its canonical JSON form.

A `.rrcf` declaration is XML, and may be standalone or embedded inside a URDF
or other physical description file. JSON Schema cannot validate XML, so every
conformance check runs against this canonical projection instead. The
projection is deliberately boring: it renames nothing and infers nothing, it
only reshapes XML into JSON and coerces attribute strings into the types the
schema expects.

Keeping the projection dumb matters. If it "helpfully" filled in a missing
unit or guessed a field type, the linter would be validating the projector's
opinions instead of what the vendor actually declared.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

# Attributes that carry numbers wherever they appear.
_NUMERIC_ATTRS = {
    "min",
    "max",
    "warn_below",
    "warn_above",
    "frequency_hz",
    "timeout_ms",
    "qos",
    "dof",
    "rate_hz",
}
_BOOLEAN_ATTRS = {"required", "standard", "cartesian", "pitch", "roll", "height"}
# Space-separated lists.
_LIST_ATTRS = {"axes", "values"}


class ProjectionError(ValueError):
    """The input is not a usable RRCF declaration."""


def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _coerce(name: str, raw: str) -> Any:
    if name in _LIST_ATTRS:
        return raw.split()
    if name in _BOOLEAN_ATTRS:
        low = raw.strip().lower()
        if low in ("true", "1"):
            return True
        if low in ("false", "0"):
            return False
        return raw
    if name in _NUMERIC_ATTRS or name.startswith("max_") or name.startswith("min_"):
        return _number(raw)
    return raw


def _number(raw: str) -> Any:
    text = raw.strip()
    if not text:
        return raw
    try:
        if re.fullmatch(r"[+-]?\d+", text):
            return int(text)
        return float(text)
    except ValueError:
        return raw


def _attrs(el: ET.Element) -> dict[str, Any]:
    return {_strip_ns(k): _coerce(_strip_ns(k), v) for k, v in el.attrib.items()}


def _words(el: ET.Element | None) -> list[str]:
    if el is None or not (el.text or "").strip():
        return []
    return el.text.split()


def _find(parent: ET.Element, name: str) -> ET.Element | None:
    for child in parent:
        if _strip_ns(child.tag) == name:
            return child
    return None


def _find_all(parent: ET.Element, name: str) -> list[ET.Element]:
    return [c for c in parent if _strip_ns(c.tag) == name]


def _find_rrcf_element(root: ET.Element) -> ET.Element:
    """Locate the <rrcf> element, standalone or embedded in a host document."""
    if _strip_ns(root.tag) == "rrcf":
        return root
    for el in root.iter():
        if _strip_ns(el.tag) == "rrcf":
            return el
    raise ProjectionError(
        "no <rrcf> element found — expected a standalone .rrcf file or an "
        "<rrcf> block embedded in a physical description file"
    )


def project_element(rrcf: ET.Element) -> dict[str, Any]:
    """Project an already-located <rrcf> element."""
    out: dict[str, Any] = {}

    version = rrcf.attrib.get("version")
    if version is not None:
        out["version"] = version

    meta_el = _find(rrcf, "meta")
    if meta_el is not None:
        meta: dict[str, Any] = {}
        for child in meta_el:
            name = _strip_ns(child.tag)
            if name == "physical_ref":
                meta["physical_ref"] = _attrs(child)
            elif (child.text or "").strip():
                meta[name] = child.text.strip()
        out["meta"] = meta

    primary_el = _find(rrcf, "primary")
    if primary_el is not None:
        primary: dict[str, Any] = _attrs(primary_el)

        loco_el = _find(primary_el, "locomotion")
        if loco_el is not None:
            loco_attrs = _attrs(loco_el)
            axes = loco_attrs.pop("axes", [])
            limits = {k: v for k, v in loco_attrs.items() if k.startswith("max_")}
            locomotion: dict[str, Any] = {"axes": axes}
            if limits:
                locomotion["limits"] = limits
            primary["locomotion"] = locomotion

        modes_el = _find(primary_el, "modes")
        if modes_el is not None:
            primary["modes"] = _words(modes_el)

        body_pose_el = _find(primary_el, "body_pose")
        if body_pose_el is not None:
            primary["body_pose"] = _attrs(body_pose_el)

        out["primary"] = primary

    attachments_el = _find(rrcf, "attachments")
    if attachments_el is not None:
        attachments = []
        for attach in _find_all(attachments_el, "attach"):
            entry = _attrs(attach)
            modes_el = _find(attach, "modes")
            if modes_el is not None:
                entry["modes"] = _words(modes_el)
            ee_el = _find(attach, "ee_control")
            if ee_el is not None:
                entry["ee_control"] = _attrs(ee_el)
            attachments.append(entry)
        out["attachments"] = attachments

    skills_el = _find(rrcf, "skills")
    if skills_el is not None:
        out["skills"] = [_attrs(s) for s in _find_all(skills_el, "skill")]

    telemetry_el = _find(rrcf, "telemetry")
    if telemetry_el is not None:
        out["telemetry"] = [_attrs(f) for f in _find_all(telemetry_el, "field")]

    safety_el = _find(rrcf, "safety")
    if safety_el is not None:
        out["safety"] = {_strip_ns(c.tag): _attrs(c) for c in safety_el}

    transport_el = _find(rrcf, "transport")
    if transport_el is not None:
        out["transport"] = {
            "endpoints": [_attrs(e) for e in _find_all(transport_el, "endpoint")]
        }

    return out


def project_string(text: str) -> dict[str, Any]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ProjectionError(f"malformed XML: {exc}") from exc
    return project_element(_find_rrcf_element(root))


def project_file(path: str | Path) -> dict[str, Any]:
    return project_string(Path(path).read_text(encoding="utf-8"))
