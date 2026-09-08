"""
rrcf_parser.py — parses a .rrcf file into a plain dict.

No ROS, no MQTT — this module has zero framework dependencies on purpose,
so it can be unit-tested standalone and reused by a non-ROS bridge later
(e.g. a plain asyncio/websockets bridge) without dragging rclpy along.

Only the fields the reference bridge actually needs are extracted. This is
not a full RRCF-1.0 schema validator — see RRCF spec section 7 for the
complete file structure.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SafetyConfig:
    estop_required: bool = True
    estop_topic: str = "/rrcf/estop"
    estop_qos: int = 2
    watchdog_timeout_ms: int = 500
    watchdog_action: str = "halt"
    max_vx: float = 1.0
    max_vy: float = 1.0
    max_wz: float = 1.0


@dataclass
class TransportEndpoint:
    role: str
    protocol: str
    topic: str = ""
    broker: str = ""
    port: int = 0
    frequency_hz: float = 0.0


@dataclass
class RrcfProfile:
    name: str
    vendor: str
    category: str
    slug: str
    safety: SafetyConfig
    endpoints: list[TransportEndpoint] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    telemetry_fields: list[str] = field(default_factory=list)
    source_path: str = ""

    def endpoint(self, role: str) -> TransportEndpoint | None:
        for ep in self.endpoints:
            if ep.role == role:
                return ep
        return None


def _slugify(name: str) -> str:
    return re.sub(r"\s+", "_", name.strip().lower())


def _to_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes")


def parse_rrcf_file(path: str) -> RrcfProfile:
    """Parse a .rrcf (or a physical description file with an embedded
    <rrcf> block) and return an RrcfProfile. Raises ValueError if no
    <rrcf> element is found, or FileNotFoundError if the path is bad."""
    text = Path(path).read_text(encoding="utf-8")
    return parse_rrcf_string(text, source_path=path)


def parse_rrcf_string(xml_text: str, source_path: str = "") -> RrcfProfile:
    root = ET.fromstring(xml_text)

    # A .rrcf file has <rrcf> as the root. An embedded block (inside a URDF,
    # for instance) has <rrcf> as a descendant instead — handle both.
    rrcf_el = root if root.tag.split("}")[-1] == "rrcf" else root.find(".//rrcf")
    if rrcf_el is None:
        # also try namespaced lookup
        for el in root.iter():
            if el.tag.split("}")[-1] == "rrcf":
                rrcf_el = el
                break
    if rrcf_el is None:
        raise ValueError(f"No <rrcf> element found in {source_path or '(string input)'}")

    def find(tag):
        for el in rrcf_el.iter():
            if el.tag.split("}")[-1] == tag:
                return el
        return None

    def findall(tag):
        return [el for el in rrcf_el.iter() if el.tag.split("}")[-1] == tag]

    meta_el = find("meta")
    name_el = meta_el.find("./{*}name") if meta_el is not None else None
    vendor_el = meta_el.find("./{*}vendor") if meta_el is not None else None
    name = (name_el.text if name_el is not None and name_el.text else "unnamed_robot").strip()
    vendor = (vendor_el.text if vendor_el is not None and vendor_el.text else "unknown").strip()

    primary_el = find("primary")
    category = primary_el.get("category", "custom") if primary_el is not None else "custom"

    loco_el = find("locomotion")
    max_vx = float(loco_el.get("max_vx", 1.0)) if loco_el is not None else 1.0
    max_vy = float(loco_el.get("max_vy", 1.0)) if loco_el is not None else 1.0
    max_wz = float(loco_el.get("max_wz", 1.0)) if loco_el is not None else 1.0

    estop_el = find("estop")
    watchdog_el = find("watchdog")
    speed_limit_el = find("speed_limit")
    if speed_limit_el is not None:
        # <speed_limit> overrides <locomotion> maxima if both are present —
        # it's the value the safety block actually enforces (spec section 7).
        max_vx = float(speed_limit_el.get("max_vx", max_vx))
        max_wz = float(speed_limit_el.get("max_wz", max_wz))

    safety = SafetyConfig(
        estop_required=_to_bool(estop_el.get("required") if estop_el is not None else None, True),
        estop_topic=(estop_el.get("topic") if estop_el is not None else None) or "/rrcf/estop",
        estop_qos=int(estop_el.get("qos", 2)) if estop_el is not None else 2,
        watchdog_timeout_ms=int(watchdog_el.get("timeout_ms", 500)) if watchdog_el is not None else 500,
        watchdog_action=(watchdog_el.get("action") if watchdog_el is not None else None) or "halt",
        max_vx=max_vx,
        max_vy=max_vy,
        max_wz=max_wz,
    )

    endpoints = []
    for ep_el in findall("endpoint"):
        endpoints.append(
            TransportEndpoint(
                role=ep_el.get("role", ""),
                protocol=ep_el.get("protocol", ""),
                topic=ep_el.get("topic", ""),
                broker=ep_el.get("broker", ""),
                port=int(ep_el.get("port", 0)) if ep_el.get("port") else 0,
                frequency_hz=float(ep_el.get("frequency_hz", 0)) if ep_el.get("frequency_hz") else 0.0,
            )
        )

    skills = [s.get("id", "") for s in findall("skill") if s.get("id")]

    # <hud> also uses <field> elements (for the HUD strip) — scope telemetry
    # fields specifically to the <telemetry> block so HUD fields like "mode"
    # and "estop" don't leak into the telemetry-republish payload.
    telemetry_el = find("telemetry")
    telemetry_fields = []
    if telemetry_el is not None:
        telemetry_fields = [
            f.get("id", "")
            for f in telemetry_el.iter()
            if f.tag.split("}")[-1] == "field" and f.get("id")
        ]

    return RrcfProfile(
        name=name,
        vendor=vendor,
        category=category,
        slug=_slugify(name),
        safety=safety,
        endpoints=endpoints,
        skills=skills,
        telemetry_fields=telemetry_fields,
        source_path=source_path,
    )
