"""
converters/sdf.py — SDFormat (Gazebo) -> RRCF info-dict analyzer.

Pure ElementTree parse. Unlike URDF, SDF has native <sensor> tags and often
an explicit joint to "world" for fixed-base models, which makes free-base
detection more reliable than the URDF heuristic.
"""

import xml.etree.ElementTree as ET
from .common import classify_joint_name

NON_ACTUATED_TYPES = {"fixed"}
ROTATIONAL_TYPES = {"revolute", "revolute2", "universal", "ball", "screw", "gearbox"}


def _findall_recursive(root, tag):
    """SDF allows nested <model> elements; walk the whole tree for a tag."""
    return list(root.iter(tag))


def analyze(path):
    tree = ET.parse(str(path))
    root = tree.getroot()
    if root.tag != "sdf":
        raise ValueError(f"Not an SDF file (root tag is <{root.tag}>, expected <sdf>)")

    model_el = root.find("model")
    is_static = False
    if model_el is not None:
        static_el = model_el.find("static")
        is_static = static_el is not None and (static_el.text or "").strip().lower() == "true"

    joints = _findall_recursive(root, "joint")
    world_attached = any(
        (j.find("parent") is not None and (j.find("parent").text or "").strip() == "world")
        or (j.find("child") is not None and (j.find("child").text or "").strip() == "world")
        for j in joints
    )

    buckets = {"leg": [], "arm": [], "hand": [], "wheel": [], "other": []}
    actuators = []
    for j in joints:
        jtype = j.get("type", "fixed")
        parent = j.find("parent")
        if jtype in NON_ACTUATED_TYPES:
            continue
        if parent is not None and (parent.text or "").strip() == "world":
            continue  # mounting joint, not an operator DOF

        jname = j.get("name", f"joint_{len(actuators)}")
        axis_el = j.find("axis")
        limit_el = axis_el.find("limit") if axis_el is not None else None
        if limit_el is not None and "lower" in limit_el.attrib and "upper" in limit_el.attrib:
            lo, hi = float(limit_el.get("lower")), float(limit_el.get("upper"))
        elif limit_el is not None and limit_el.find("lower") is not None:
            lo = float(limit_el.find("lower").text)
            hi = float(limit_el.find("upper").text)
        elif jtype in ROTATIONAL_TYPES:
            lo, hi = -3.14159, 3.14159
        else:
            lo, hi = -1.0, 1.0

        bucket = classify_joint_name(jname)
        buckets[bucket].append(jname)
        actuators.append({"name": jname, "ctrlrange": (lo, hi), "bucket": bucket})

    has_freejoint = (not world_attached) and (not is_static)
    if not has_freejoint and len(buckets["leg"]) >= 2:
        has_freejoint = True  # convention fallback, matches urdf.py

    sensors = [s.get("name", "sensor") for s in _findall_recursive(root, "sensor")]

    return {
        "has_freejoint": has_freejoint,
        "buckets": buckets,
        "actuators": actuators,
        "sensors": sensors,
        "nu": len(actuators),
        "njnt": len(joints),
    }
