#!/usr/bin/env python3
"""
convert_to_rrcf.py — auto-detects a robot description file's format and
generates an RRCF 1.0 (.rrcf) operator-interface draft from it.

SUPPORTED FORMATS (auto-detected by root XML tag, not just extension —
many of these are all commonly saved as plain .xml):
    MJCF   <mujoco ...>            — MuJoCo (needs `pip install mujoco`)
    URDF   <robot ...>             — ROS / most industrial arms, mobile bases
    SDF    <sdf ...>               — Gazebo / Gazebo-classic

NOT YET SUPPORTED (detected and reported, not silently ignored):
    USD    .usd / .usda            — NVIDIA Omniverse / Isaac Sim. Needs the
                                      `usd-core` package and a more involved
                                      prim-graph walk than the XML formats
                                      above; open an issue if you need this.
    xacro  .xacro                  — Not a robot description on its own; run
                                      `xacro file.xacro > file.urdf` first,
                                      then convert the resulting URDF.

USAGE
    python3 convert_to_rrcf.py go2.xml
    python3 convert_to_rrcf.py ur3.urdf --vendor "Universal Robots"
    python3 convert_to_rrcf.py model.sdf --category wheeled
    python3 convert_to_rrcf.py go2.xml --out go2.rrcf --name "Unitree Go2"

See converters/common.py for the shared RRCF-building logic and
converters/{mjcf,urdf,sdf}.py for the per-format analyzers. Each analyzer
reduces its input to the same info-dict shape — adding a new format means
writing one more analyze(path) function, not touching the builder.
"""

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from converters import common
from converters import mjcf as mjcf_converter
from converters import urdf as urdf_converter
from converters import sdf as sdf_converter

ROOT_TAG_TO_FORMAT = {
    "mujoco": "mjcf",
    "robot": "urdf",
    "sdf": "sdf",
}

ANALYZERS = {
    "mjcf": mjcf_converter.analyze,
    "urdf": urdf_converter.analyze,
    "sdf": sdf_converter.analyze,
}


def detect_format(path):
    suffix = path.suffix.lower()
    if suffix in (".usd", ".usda", ".usdc"):
        return "usd"
    if suffix == ".xacro":
        return "xacro"

    try:
        # Peek at just the root tag without fully parsing (cheap + safe for large files).
        for _, elem in ET.iterparse(str(path), events=("start",)):
            tag = elem.tag
            elem.clear()
            return ROOT_TAG_TO_FORMAT.get(tag, "unknown")
    except ET.ParseError as e:
        raise ValueError(f"Could not parse {path} as XML: {e}")
    return "unknown"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="Path to the robot description file (MJCF/URDF/SDF .xml, .urdf, or .sdf)")
    ap.add_argument("--format", choices=list(ANALYZERS.keys()),
                     help="Force the source format instead of auto-detecting from the root XML tag")
    ap.add_argument("--name", help="Robot name for <meta><name> (default: filename)")
    ap.add_argument("--vendor", default="Unknown — set with --vendor", help="Vendor name for <meta><vendor>")
    ap.add_argument("--category", choices=common.CATEGORY_CHOICES,
                     help="Force a morphology category instead of the heuristic guess")
    ap.add_argument("--out", help="Output .rrcf path (default: alongside input, same stem)")
    args = ap.parse_args()

    src_path = Path(args.source)
    if not src_path.exists():
        sys.exit(f"File not found: {src_path}")

    fmt = args.format or detect_format(src_path)

    if fmt == "usd":
        sys.exit(
            "USD (.usd/.usda) source detected — not yet supported by this converter.\n"
            "USD needs the usd-core package and a prim-graph walk rather than a flat "
            "XML parse. For now, export the robot to URDF or MJCF from your USD "
            "pipeline (e.g. Isaac Sim's URDF exporter) and convert that instead."
        )
    if fmt == "xacro":
        sys.exit(
            "xacro source detected — xacro is a macro/templating layer, not a robot "
            "description on its own.\nRun it through the xacro processor first:\n"
            f"    xacro {src_path} > {src_path.with_suffix('.urdf')}\n"
            "then convert the resulting .urdf file."
        )
    if fmt == "unknown":
        sys.exit(
            f"Could not identify the format of {src_path} from its root XML tag.\n"
            f"Supported: MJCF (<mujoco>), URDF (<robot>), SDF (<sdf>).\n"
            f"Pass --format explicitly if this is one of those with a nonstandard root."
        )

    analyze = ANALYZERS[fmt]
    info = analyze(src_path)
    category = common.guess_category(info)
    meta_name = args.name or src_path.stem

    root = common.build_rrcf(info, category, meta_name, args.vendor, src_path.name, fmt,
                              override=args.category)

    out_path = Path(args.out) if args.out else src_path.with_suffix(".rrcf")
    common.write_rrcf(root, out_path)

    used_cat = args.category or category
    print(f"Detected format: {fmt}")
    print(f"Wrote {out_path}")
    print(f"  actuators: {info['nu']}  |  category guess: {category}"
          + (f"  |  forced: {args.category}" if args.category else ""))
    print(f"  final category used: {used_cat}")
    if category == "custom" and not args.category:
        print("  NOTE: heuristic could not confidently classify this model — "
              "review <primary category> by hand.")


if __name__ == "__main__":
    main()
