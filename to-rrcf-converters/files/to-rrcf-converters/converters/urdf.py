"""
converters/urdf.py — URDF -> RRCF info-dict analyzer.

Pure ElementTree parse, no ROS/urdfdom install required. Does NOT process
xacro macros — if you have a .xacro file, run it through `xacro` first
(e.g. `xacro robot.xacro > robot.urdf`) before converting.

URDF-specific caveats baked into the heuristics below:
  - URDF has no native concept of a "free-floating base" the way MJCF does.
    We treat an explicit <joint type="floating"> as a floating base, and
    otherwise fall back to "2+ leg-named actuated joints => assume floating
    base by convention" (most legged-robot URDF packages model the base as
    implicitly free). This is a heuristic — verify <primary category> by hand
    for anything mobile.
  - Actuator list comes from <transmission><actuator> blocks if present
    (ROS-control convention); otherwise every non-fixed joint is treated as
    one actuator, which is the common case for plain (non-ROS-control) URDFs.
  - "Sensors" are pulled from Gazebo-extension <gazebo><sensor> blocks if
    present; plain URDF has no native sensor tag, so this is often empty.
"""

import xml.etree.ElementTree as ET
from .common import classify_joint_name

NON_ACTUATED_TYPES = {"fixed"}
BASE_FREEDOM_TYPES = {"floating", "planar"}


def analyze(path):
    tree = ET.parse(str(path))
    root = tree.getroot()
    if root.tag != "robot":
        raise ValueError(f"Not a URDF file (root tag is <{root.tag}>, expected <robot>)")

    joints = root.findall("joint")

    has_freejoint = any(j.get("type") in BASE_FREEDOM_TYPES for j in joints)

    # Prefer explicit <transmission> actuator declarations (ROS-control convention).
    trans_actuator_for_joint = {}
    for trans in root.findall("transmission"):
        joint_el = trans.find("joint")
        act_el = trans.find("actuator")
        if joint_el is not None and act_el is not None:
            jname = joint_el.get("name")
            aname = act_el.get("name") or jname
            trans_actuator_for_joint[jname] = aname

    buckets = {"leg": [], "arm": [], "hand": [], "wheel": [], "other": []}
    actuators = []
    for j in joints:
        jtype = j.get("type", "fixed")
        if jtype in NON_ACTUATED_TYPES or jtype in BASE_FREEDOM_TYPES:
            continue  # not an operator-controllable DOF
        jname = j.get("name", f"joint_{len(actuators)}")
        aname = trans_actuator_for_joint.get(jname, jname)

        limit_el = j.find("limit")
        if limit_el is not None and "lower" in limit_el.attrib and "upper" in limit_el.attrib:
            lo, hi = float(limit_el.get("lower")), float(limit_el.get("upper"))
        elif jtype == "continuous":
            lo, hi = -3.14159, 3.14159  # unbounded rotation — full-turn placeholder
        else:
            lo, hi = -1.0, 1.0  # no <limit> declared — conservative placeholder

        bucket = classify_joint_name(jname)
        buckets[bucket].append(aname)
        actuators.append({"name": aname, "ctrlrange": (lo, hi), "bucket": bucket})

    if not has_freejoint and len(buckets["leg"]) >= 2:
        has_freejoint = True  # convention fallback — see module docstring

    # Gazebo-extension sensors, if present.
    sensors = []
    for gz in root.findall("gazebo"):
        for s in gz.findall("sensor"):
            sensors.append(s.get("name", "sensor"))

    return {
        "has_freejoint": has_freejoint,
        "buckets": buckets,
        "actuators": actuators,
        "sensors": sensors,
        "nu": len(actuators),
        "njnt": len(joints),
    }
