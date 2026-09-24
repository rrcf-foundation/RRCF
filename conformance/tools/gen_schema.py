#!/usr/bin/env python3
"""Generate the RRCF declaration JSON Schema from category-profiles.json.

The profiles file is the source of truth for per-category mandatory fields.
This script projects it into a standard JSON Schema (2020-12) so that any
JSON Schema implementation, in any language, can enforce the same rules
without reimplementing RRCF-specific logic.

Usage:
    python conformance/tools/gen_schema.py            # write the schema
    python conformance/tools/gen_schema.py --check    # verify it is current

--check is what CI runs: it fails if the checked-in schema has drifted from
the profiles, so the two can never disagree silently.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILES_PATH = REPO_ROOT / "conformance" / "profiles" / "category-profiles.json"
SCHEMA_PATH = REPO_ROOT / "conformance" / "schema" / "rrcf-declaration.schema.json"

SCHEMA_ID = "https://rrcf-foundation.github.io/schema/rrcf-declaration.schema.json"


def field_matcher(spec: dict) -> dict:
    """A `contains` subschema asserting one mandatory telemetry field exists.

    Only the attributes the profile actually pins down are constrained, so a
    vendor stays free to choose range, warn thresholds, label, and widget.
    """
    props: dict = {"id": {"const": spec["id"]}, "type": {"const": spec["type"]}}
    required = ["id", "type"]

    if "unit" in spec:
        props["unit"] = {"const": spec["unit"]}
        required.append("unit")

    if spec["type"] == "enum" and "values" in spec:
        # A standardized value set: the declaration must cover every state.
        props["values"] = {
            "type": "array",
            "allOf": [{"contains": {"const": v}} for v in spec["values"]],
        }
        required.append("values")

    return {"type": "object", "properties": props, "required": required}


def telemetry_field_def(profiles: dict) -> dict:
    """The self-description contract, as a type-conditional schema."""
    contract = profiles["selfDescriptionContract"]
    by_type = contract["requiredAttributes"]["byType"]

    conditionals = []
    for type_name, required_attrs in by_type.items():
        if not required_attrs:
            continue
        conditionals.append(
            {
                "if": {"properties": {"type": {"const": type_name}}, "required": ["type"]},
                "then": {"required": required_attrs},
            }
        )

    return {
        "type": "object",
        "title": "Self-describing telemetry field",
        "description": contract["statement"],
        "properties": {
            "id": {
                "type": "string",
                "pattern": "^[a-z][a-z0-9_]*$",
                "description": "Stable field identifier, unique within the declaration.",
            },
            "type": {"enum": profiles["fieldTypes"]},
            "unit": {
                "type": "string",
                "minLength": 1,
                "description": "Unit symbol. '1' for dimensionless ratios, '%' for percentages.",
            },
            "min": {"type": "number"},
            "max": {"type": "number"},
            "values": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "description": "Every value an enum field can emit.",
            },
            "label": {"type": "string"},
            "widget": {"enum": profiles["widgets"]},
            "warn_below": {"type": "number"},
            "warn_above": {"type": "number"},
            "frequency_hz": {"type": "number", "exclusiveMinimum": 0},
            "description": {"type": "string"},
        },
        "required": contract["requiredAttributes"]["always"],
        "allOf": conditionals,
        "$comment": (
            "min < max, warn thresholds inside [min, max], and field-ID uniqueness "
            "are asserted by the linter — JSON Schema cannot express cross-property "
            "comparisons. See conformance/rrcf_conformance/lint.py."
        ),
    }


def build_schema(profiles: dict) -> dict:
    universal = profiles["universal"]
    categories = profiles["categories"]

    all_of: list[dict] = []

    # Universal mandatory telemetry, required of every category.
    for spec in universal["telemetry"]:
        all_of.append(
            {
                "title": f"universal telemetry: {spec['id']}",
                "properties": {"telemetry": {"contains": field_matcher(spec)}},
                "required": ["telemetry"],
            }
        )

    # Per-category mandatory telemetry and locomotion axes.
    for cat_id, cat in sorted(categories.items()):
        clauses: list[dict] = []

        for spec in cat["telemetry"]:
            clauses.append({"properties": {"telemetry": {"contains": field_matcher(spec)}}})

        axes = cat.get("locomotionAxes") or []
        if axes:
            clauses.append(
                {
                    "properties": {
                        "primary": {
                            "properties": {
                                "locomotion": {
                                    "type": "object",
                                    "properties": {
                                        "axes": {
                                            "type": "array",
                                            "allOf": [
                                                {"contains": {"const": axis}} for axis in axes
                                            ],
                                        }
                                    },
                                    "required": ["axes"],
                                }
                            },
                            "required": ["locomotion"],
                        }
                    }
                }
            )

        if not clauses:
            continue

        then_clause = clauses[0] if len(clauses) == 1 else {"allOf": clauses}
        then_clause = dict(then_clause)
        then_clause["required"] = ["telemetry"]

        all_of.append(
            {
                "title": f"category profile: {cat_id}",
                "if": {
                    "properties": {
                        "primary": {
                            "type": "object",
                            "properties": {"category": {"const": cat_id}},
                            "required": ["category"],
                        }
                    },
                    "required": ["primary"],
                },
                "then": then_clause,
            }
        )

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID,
        "title": "RRCF declaration (canonical JSON projection)",
        "description": (
            "GENERATED FILE — do not edit by hand. Regenerate with "
            "`python conformance/tools/gen_schema.py` after editing "
            "conformance/profiles/category-profiles.json.\n\n"
            "Validates the canonical JSON projection of a .rrcf declaration, "
            "produced by conformance/rrcf_conformance/projection.py. A .rrcf file "
            "is XML; this schema deliberately targets the projection so that the "
            "same rules can be checked by any JSON Schema implementation."
        ),
        "x-rrcf-profiles-version": profiles["profilesVersion"],
        "x-rrcf-version": profiles["rrcfVersion"],
        "type": "object",
        "required": ["version", "primary", "telemetry", "safety", "transport"],
        "additionalProperties": True,
        "properties": {
            "version": {"const": profiles["rrcfVersion"]},
            "meta": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "vendor": {"type": "string"},
                    "model": {"type": "string"},
                    "physical_ref": {
                        "type": "object",
                        "properties": {
                            "format": {"enum": ["urdf", "mjcf", "sdf", "usd", "xacro"]},
                            "path": {"type": "string"},
                        },
                    },
                },
            },
            "primary": {
                "type": "object",
                "required": ["category"],
                "properties": {
                    "category": {"enum": sorted(categories)},
                    "locomotion": {
                        "type": "object",
                        "properties": {
                            "axes": {"type": "array", "items": {"type": "string"}},
                            "limits": {
                                "type": "object",
                                "additionalProperties": {"type": "number"},
                            },
                        },
                    },
                    "modes": {"type": "array", "items": {"type": "string"}},
                },
            },
            "skills": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["id"],
                    "properties": {
                        "id": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
                        "label": {"type": "string"},
                        "standard": {"type": "boolean"},
                        "cmd": {"type": "string"},
                    },
                },
            },
            "telemetry": {
                "type": "array",
                "items": {"$ref": "#/$defs/telemetryField"},
                "minItems": len(universal["telemetry"]),
            },
            "safety": {
                "type": "object",
                "required": universal["safety"]["requiredElements"],
                "properties": {
                    "estop": {
                        "type": "object",
                        "required": ["required", "topic"],
                        "properties": {
                            "required": {"const": True},
                            "topic": {"type": "string", "minLength": 1},
                            "qos": {"type": "integer", "minimum": 0, "maximum": 2},
                        },
                    },
                    "watchdog": {
                        "type": "object",
                        "required": ["timeout_ms", "action"],
                        "properties": {
                            "timeout_ms": {"type": "integer", "exclusiveMinimum": 0},
                            "action": {"enum": ["halt", "safe_state", "land", "surface", "hold"]},
                        },
                    },
                    "speed_limit": {
                        "type": "object",
                        "additionalProperties": {"type": "number"},
                    },
                },
            },
            "transport": {
                "type": "object",
                "required": ["endpoints"],
                "properties": {
                    "endpoints": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "required": ["role", "protocol"],
                            "properties": {
                                "role": {
                                    "enum": ["operator_cmd", "telemetry", "estop", "video"]
                                },
                                "protocol": {"type": "string", "minLength": 1},
                                "topic": {"type": "string"},
                                "broker": {"type": "string"},
                                "frequency_hz": {"type": "number", "exclusiveMinimum": 0},
                            },
                        },
                        "allOf": [
                            {
                                "contains": {
                                    "type": "object",
                                    "properties": {"role": {"const": "operator_cmd"}},
                                    "required": ["role"],
                                },
                                "$comment": "A declaration with no command endpoint is not controllable.",
                            },
                            {
                                "contains": {
                                    "type": "object",
                                    "properties": {"role": {"const": "telemetry"}},
                                    "required": ["role"],
                                },
                                "$comment": (
                                    "A declaration with no telemetry endpoint is not "
                                    "safely commandable: an operator cannot be asked to "
                                    "command a robot whose current state they cannot see."
                                ),
                            },
                        ],
                    }
                },
            },
        },
        "$defs": {"telemetryField": telemetry_field_def(profiles)},
        "allOf": all_of,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if the checked-in schema differs from the generated one",
    )
    args = parser.parse_args()

    profiles = json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
    schema = build_schema(profiles)
    rendered = json.dumps(schema, indent=2, ensure_ascii=False) + "\n"

    if args.check:
        if not SCHEMA_PATH.exists():
            print(f"FAIL {SCHEMA_PATH.relative_to(REPO_ROOT)} is missing", file=sys.stderr)
            return 1
        current = SCHEMA_PATH.read_text(encoding="utf-8")
        if current != rendered:
            print(
                "FAIL generated schema is out of date.\n"
                "     Run: python conformance/tools/gen_schema.py",
                file=sys.stderr,
            )
            return 1
        print("OK   schema matches conformance/profiles/category-profiles.json")
        return 0

    SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA_PATH.write_text(rendered, encoding="utf-8")
    print(f"wrote {SCHEMA_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
