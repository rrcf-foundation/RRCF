"""
converters/mjcf.py — MJCF -> RRCF info-dict analyzer.

Uses the real MuJoCo compiler (pip install mujoco) so <default> class
inheritance, <include> files, and tendon-driven actuators are all resolved
exactly the way the simulator sees them.
"""

from .common import classify_joint_name

try:
    import mujoco
except ImportError:
    mujoco = None


def available():
    return mujoco is not None


def name_or(model, objtype, i, fallback):
    n = mujoco.mj_id2name(model, objtype, i)
    return n if n else fallback


def analyze(path):
    if mujoco is None:
        raise RuntimeError(
            "MJCF support needs the mujoco python package.\n"
            "Install it with:  pip install mujoco --break-system-packages"
        )
    model = mujoco.MjModel.from_xml_path(str(path))

    has_freejoint = any(
        model.jnt_type[j] == mujoco.mjtJoint.mjJNT_FREE for j in range(model.njnt)
    )

    buckets = {"leg": [], "arm": [], "hand": [], "wheel": [], "other": []}
    actuators = []
    for a in range(model.nu):
        aname = name_or(model, mujoco.mjtObj.mjOBJ_ACTUATOR, a, f"act_{a}")
        lo, hi = model.actuator_ctrlrange[a]
        driven_joint = None
        if model.actuator_trntype[a] == mujoco.mjtTrn.mjTRN_JOINT:
            jid = model.actuator_trnid[a][0]
            driven_joint = name_or(model, mujoco.mjtObj.mjOBJ_JOINT, jid, aname)
        bucket = classify_joint_name(driven_joint or aname)
        buckets[bucket].append(aname)
        actuators.append({"name": aname, "ctrlrange": (float(lo), float(hi)), "bucket": bucket})

    sensors = [
        name_or(model, mujoco.mjtObj.mjOBJ_SENSOR, s, f"sensor_{s}")
        for s in range(model.nsensor)
    ]

    return {
        "has_freejoint": has_freejoint,
        "buckets": buckets,
        "actuators": actuators,
        "sensors": sensors,
        "nu": model.nu,
        "njnt": model.njnt,
    }
