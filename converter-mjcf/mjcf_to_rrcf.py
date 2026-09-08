#!/usr/bin/env python3
"""
mjcf_to_rrcf.py — Draft-generate an RRCF 1.0 (.rrcf) operator-interface file
from a MuJoCo MJCF model.

Requires the real MuJoCo compiler (pip install mujoco), so <default> class
inheritance, <include> files, and tendon-driven actuators are all resolved
exactly the way the simulator sees them. Use this version when you want the
most accurate output. For a zero-install, drag-and-drop version, use the
companion mjcf_to_rrcf.html (browser-only, parses raw XML — see caveats in
that file's header comment).

USAGE
    python3 mjcf_to_rrcf.py humanoid.xml
    python3 mjcf_to_rrcf.py car.xml --vendor "MuJoCo Playground" --category wheeled
    python3 mjcf_to_rrcf.py go2.xml --out go2.rrcf

WHAT THIS SCRIPT DOES
    1. Loads the MJCF through mujoco.MjModel so ctrlrange/jnt_range/names are
       fully resolved (defaults, includes, tendon actuators all correct).
    2. Classifies joints into locomotion DOFs vs. manipulation DOFs vs. other,
       using name/topology heuristics (freejoint presence, bilateral
       hip/knee/ankle naming, shoulder/elbow naming, wheel/steer naming).
    3. Guesses a primary RRCF morphology category (one of the 12 in RRCF-1.0
       Table in §6) from that classification.
    4. Emits an RRCF-structured draft: <meta>, <primary>, <attachments>,
       <hud>, <skills> (stubs), <input_modalities> (touch_web + gamepad axes
       for locomotion), <custom_controls> (up to 5 — the RRCF-1.0 cap),
       <telemetry> (from MJCF <sensor> elements if present), <safety>,
       <transport> (placeholder endpoints), <extensions/>.

WHAT THIS SCRIPT DOES NOT DO
    - It does not invent skills, safety limits, or transport credentials.
      Those fields are emitted as clearly-marked TODO stubs — RRCF §11.1/11.2
      conformance requires real values, not placeholders, before the file is
      used to drive an actual robot.
    - It does not resolve every actuator into an operator control. RRCF caps
      <custom_controls> at 5 by design (it's an operator-facing panel, not a
      raw joint-level teleop protocol) — high-DOF models will have unmapped
      actuators listed in a comment block for you to fold into <skills> or
      <attachments> by hand.
    - Category classification is a heuristic. Verify it — the spec requires
      exactly one primary category (RRCF §6), and getting it wrong changes
      which panel a compliant controller renders.
"""

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    import mujoco
except ImportError:
    sys.exit(
        "This script needs the mujoco python package.\n"
        "Install it with:  pip install mujoco --break-system-packages"
    )

RRCF_NS = "https://rrcf.io/schema/1.0"


def safe_comment(text):
    """XML comments may not contain '--' or end in '-'. Sanitize dynamic text
    (actuator/joint names, etc.) before embedding it in a Comment node."""
    return text.replace("--", "\u2013\u2013").rstrip("-")


MJ_JOINT_FREE = mujoco.mjtJoint.mjJNT_FREE
MJ_JOINT_HINGE = mujoco.mjtJoint.mjJNT_HINGE
MJ_JOINT_SLIDE = mujoco.mjtJoint.mjJNT_SLIDE
MJ_JOINT_BALL = mujoco.mjtJoint.mjJNT_BALL

LEG_WORDS = ("hip", "knee", "ankle", "thigh", "calf", "shin", "leg", "foot")
ARM_WORDS = ("shoulder", "elbow", "wrist", "forearm", "upperarm", "arm")
HAND_WORDS = ("finger", "thumb", "proximal", "distal", "gripper", "grip")
WHEEL_WORDS = ("wheel", "steer", "turn", "forward", "drive", "caster")


def name_or(model, objtype, i, fallback):
    n = mujoco.mj_id2name(model, objtype, i)
    return n if n else fallback


def classify_joint_name(name):
    n = name.lower()
    if any(w in n for w in LEG_WORDS):
        return "leg"
    if any(w in n for w in HAND_WORDS):
        return "hand"
    if any(w in n for w in ARM_WORDS):
        return "arm"
    if any(w in n for w in WHEEL_WORDS):
        return "wheel"
    return "other"


def analyze(model):
    """Walk the compiled model and bucket actuators by what they drive."""
    has_freejoint = any(model.jnt_type[j] == MJ_JOINT_FREE for j in range(model.njnt))

    buckets = {"leg": [], "arm": [], "hand": [], "wheel": [], "other": []}
    actuators = []
    for a in range(model.nu):
        aname = name_or(model, mujoco.mjtObj.mjOBJ_ACTUATOR, a, f"act_{a}")
        lo, hi = model.actuator_ctrlrange[a]
        # Try to find the joint this actuator drives (trntype 0 = joint transmission)
        driven_joint = None
        if model.actuator_trntype[a] == mujoco.mjtTrn.mjTRN_JOINT:
            jid = model.actuator_trnid[a][0]
            driven_joint = name_or(model, mujoco.mjtObj.mjOBJ_JOINT, jid, aname)
        bucket = classify_joint_name(driven_joint or aname)
        buckets[bucket].append(aname)
        actuators.append({"name": aname, "ctrlrange": (float(lo), float(hi)), "bucket": bucket})

    sensors = []
    for s in range(model.nsensor):
        sname = name_or(model, mujoco.mjtObj.mjOBJ_SENSOR, s, f"sensor_{s}")
        sensors.append(sname)

    return {
        "has_freejoint": has_freejoint,
        "buckets": buckets,
        "actuators": actuators,
        "sensors": sensors,
        "nu": model.nu,
        "njnt": model.njnt,
    }


def guess_category(info):
    """Best-effort mapping onto RRCF-1.0's 12 morphology categories (spec §6)."""
    has_legs = len(info["buckets"]["leg"]) >= 2
    has_arms = len(info["buckets"]["arm"]) >= 1
    has_wheels = len(info["buckets"]["wheel"]) >= 1

    if info["has_freejoint"] and has_legs and has_arms:
        return "full_humanoid"
    if info["has_freejoint"] and has_legs:
        return "legged"
    if has_legs and has_arms:
        return "loco_manip"
    if has_wheels:
        return "wheeled"
    if has_arms and not has_legs and not info["has_freejoint"]:
        return "manipulator"
    return "custom"  # flagged for manual review — nothing matched confidently


def build_rrcf(info, category, meta_name, vendor, mjcf_path, override=None):
    ET.register_namespace("", RRCF_NS)
    root = ET.Element("rrcf", version="1.0", xmlns=RRCF_NS)
    root.append(ET.Comment(safe_comment(
        f" AUTO-GENERATED DRAFT via mjcf_to_rrcf.py — verify before use. "
        f"{info['nu']} actuators / {info['njnt']} joints in source MJCF. "
        f"Category is a heuristic guess unless overridden via the category flag. "
    )))

    meta = ET.SubElement(root, "meta")
    ET.SubElement(meta, "name").text = meta_name
    ET.SubElement(meta, "vendor").text = vendor
    ET.SubElement(meta, "model").text = meta_name
    ET.SubElement(meta, "physical_ref", format="mjcf", path=str(mjcf_path))

    cat = override or category
    primary = ET.SubElement(root, "primary", category=cat)

    loco_actuators = info["buckets"]["leg"] + info["buckets"]["wheel"]
    arm_actuators = info["buckets"]["arm"]
    hand_actuators = info["buckets"]["hand"]
    other_actuators = info["buckets"]["other"]

    if cat in ("legged", "full_humanoid", "loco_manip", "wheeled", "wheeled_humanoid"):
        ET.SubElement(primary, "locomotion", axes="vx vy wz",
                      max_vx="1.0", max_vy="0.5", max_wz="1.5")
        modes = "stand walk" if "legged" in cat or "humanoid" in cat or "loco" in cat else "drive"
        ET.SubElement(primary, "modes").text = modes
        if "humanoid" in cat or "legged" in cat or "loco" in cat:
            ET.SubElement(primary, "body_pose", pitch="true", roll="true", height="true")
    elif cat == "manipulator":
        ET.SubElement(primary, "modes").text = "teach replay"

    attachments = ET.SubElement(root, "attachments")
    if arm_actuators and cat != "manipulator":
        attach = ET.SubElement(attachments, "attach", type="manipulator", id="arm_1",
                                mount="torso", dof=str(len(arm_actuators)))
        ET.SubElement(attach, "modes").text = "stow reach teach replay"
        ET.SubElement(attach, "ee_control", cartesian="true")
    if hand_actuators:
        mount = "arm_1/ee" if arm_actuators else "torso"
        ET.SubElement(attachments, "attach", type="gripper", id="grip_1",
                      mount=mount, fingers=str(max(1, len(hand_actuators))))
    if not len(attachments):
        root.remove(attachments)

    hud = ET.SubElement(root, "hud")
    ET.SubElement(hud, "field", id="mode", position="1", label="MODE")
    ET.SubElement(hud, "field", id="battery", position="2", label="BATT")
    ET.SubElement(hud, "field", id="estop", position="3", label="STOP", alert="true")

    skills = ET.SubElement(root, "skills")
    if cat in ("legged", "full_humanoid", "loco_manip", "wheeled_humanoid"):
        ET.SubElement(skills, "skill", id="stand", label="Stand", standard="true",
                      cmd='{"mode":"stand"}')
        ET.SubElement(skills, "skill", id="sit", label="Sit", standard="true",
                      cmd='{"mode":"sit"}')
    skills.append(ET.Comment(
        " TODO: declare vendor-specific skills here. Skills — not raw joint "
        "sliders — are RRCF's mechanism for exposing high-DOF behavior; see "
        "spec §9 (VLA Integration) for why. "
    ))

    modalities = ET.SubElement(root, "input_modalities")
    ET.SubElement(modalities, "modality", type="touch_web", enabled="true")
    if loco_actuators:
        gp = ET.SubElement(modalities, "modality", type="hid_gamepad",
                            enabled="true", standard="xinput")
        ET.SubElement(gp, "axis", hid="left_x", rrcf="lx")
        ET.SubElement(gp, "axis", hid="left_y", rrcf="ly", invert="true")
        ET.SubElement(gp, "button", hid="B", action="estop")

    slot_candidates = other_actuators + arm_actuators + hand_actuators
    exposed = slot_candidates[:5]
    unexposed = slot_candidates[5:]

    custom = ET.SubElement(root, "custom_controls", max="5")
    ctrl_by_name = {a["name"]: a for a in info["actuators"]}
    for name in exposed:
        a = ctrl_by_name.get(name)
        lo, hi = a["ctrlrange"] if a else (-1.0, 1.0)
        ET.SubElement(custom, "control", type="slider", id=name, label=name,
                      min=f"{lo:.3f}", max=f"{hi:.3f}")
    if not len(custom):
        root.remove(custom)
    if unexposed:
        custom.append(ET.Comment(safe_comment(
            f" {len(unexposed)} more actuator(s) not exposed (RRCF custom_controls "
            f"cap is 5): {', '.join(unexposed)}. Fold these into skills or a "
            f"dedicated attach block rather than raising the cap. "
        )))

    telemetry = ET.SubElement(root, "telemetry")
    if info["sensors"]:
        for sname in info["sensors"]:
            ET.SubElement(telemetry, "field", id=sname, unit="")
    else:
        ET.SubElement(telemetry, "field", id="battery", unit="%", warn_below="20")
        telemetry.append(ET.Comment(" No <sensor> elements found in MJCF — battery field is a placeholder. "))

    safety = ET.SubElement(root, "safety")
    ET.SubElement(safety, "estop", required="true",
                  topic=f"/rrcf/{meta_name.lower().replace(' ', '_')}/estop", qos="2")
    ET.SubElement(safety, "watchdog", timeout_ms="500", action="halt")
    if loco_actuators:
        ET.SubElement(safety, "speed_limit", max_vx="1.0", max_wz="1.5")

    transport = ET.SubElement(root, "transport")
    slug = meta_name.lower().replace(" ", "_")
    ET.SubElement(transport, "endpoint", role="operator_cmd", protocol="rrcf_mqtt",
                  topic=f"/rrcf/{slug}/cmd", broker="${MQTT_BROKER}")
    ET.SubElement(transport, "endpoint", role="telemetry", protocol="mqtt",
                  topic=f"/rrcf/{slug}/state", frequency_hz="10")
    ET.SubElement(transport, "endpoint", role="websocket", protocol="websocket", port="9090")
    transport.append(ET.Comment(" TODO: replace placeholder broker/topic values before deployment. "))

    ET.SubElement(root, "extensions")

    ET.indent(root, space="  ")
    return root


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mjcf", help="Path to the MJCF .xml file")
    ap.add_argument("--name", help="Robot name for <meta><name> (default: filename)")
    ap.add_argument("--vendor", default="Unknown — set with --vendor", help="Vendor name for <meta><vendor>")
    ap.add_argument("--category", choices=[
        "wheeled", "legged", "loco_manip", "wheeled_humanoid", "full_humanoid",
        "manipulator", "aerial", "marine_surface", "marine_sub",
        "industrial_vehicle", "agri_vehicle", "custom",
    ], help="Force a morphology category instead of the heuristic guess")
    ap.add_argument("--out", help="Output .rrcf path (default: alongside input, same stem)")
    args = ap.parse_args()

    mjcf_path = Path(args.mjcf)
    model = mujoco.MjModel.from_xml_path(str(mjcf_path))
    info = analyze(model)
    category = guess_category(info)
    meta_name = args.name or mjcf_path.stem

    root = build_rrcf(info, category, meta_name, args.vendor, mjcf_path.name, override=args.category)

    out_path = Path(args.out) if args.out else mjcf_path.with_suffix(".rrcf")
    xml_bytes = b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="utf-8")
    out_path.write_bytes(xml_bytes)

    used_cat = args.category or category
    print(f"Wrote {out_path}")
    print(f"  actuators: {info['nu']}  |  category guess: {category}"
          + (f"  |  forced: {args.category}" if args.category else ""))
    print(f"  final category used: {used_cat}")
    if category == "custom" and not args.category:
        print("  NOTE: heuristic could not confidently classify this model — "
              "review <primary category> by hand.")


if __name__ == "__main__":
    main()
