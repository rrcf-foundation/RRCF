"""Command line entry point for RRCF conformance checking.

    rrcf-conformance lint robot.rrcf [more.rrcf ...]
    rrcf-conformance check-session robot.rrcf session.jsonl
    rrcf-conformance profiles [--category legged]

Exit codes: 0 = pass, 1 = conformance failure, 2 = usage or input error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .lint import Report, load_profiles, lint_file
from .runtime import check_session_files

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2


def _emit(reports: list[Report], as_json: bool, quiet: bool) -> int:
    if as_json:
        payload = [
            {
                "target": r.target,
                "ok": r.ok,
                "findings": [
                    {
                        "level": f.level,
                        "code": f.code,
                        "where": f.where,
                        "message": f.message,
                    }
                    for f in r.findings
                ],
            }
            for r in reports
        ]
        print(json.dumps(payload, indent=2))
    else:
        for report in reports:
            if quiet and report.ok:
                continue
            print(report.render())

        failed = sum(1 for r in reports if not r.ok)
        errors = sum(len(r.errors) for r in reports)
        warnings = sum(len(r.warnings) for r in reports)
        print(
            f"\n{len(reports)} checked · {len(reports) - failed} passed · "
            f"{failed} failed · {errors} error(s) · {warnings} warning(s)"
        )

    return EXIT_FAIL if any(not r.ok for r in reports) else EXIT_OK


def _flag(args: argparse.Namespace, name: str) -> bool:
    """Read a shared flag that uses default=SUPPRESS."""
    return bool(getattr(args, name, False))


def _expand(paths: list[str]) -> list[Path]:
    resolved: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            resolved.extend(sorted(path.rglob("*.rrcf")))
        else:
            resolved.append(path)
    return resolved


def _cmd_lint(args: argparse.Namespace) -> int:
    targets = _expand(args.declarations)
    if not targets:
        print("no .rrcf files found", file=sys.stderr)
        return EXIT_USAGE
    return _emit([lint_file(p) for p in targets], _flag(args, "json"), _flag(args, "quiet"))


def _cmd_check_session(args: argparse.Namespace) -> int:
    report = check_session_files(args.declaration, args.session)
    return _emit([report], _flag(args, "json"), _flag(args, "quiet"))


def _cmd_profiles(args: argparse.Namespace) -> int:
    profiles = load_profiles()

    if _flag(args, "json"):
        if args.category:
            entry = profiles["categories"].get(args.category)
            if entry is None:
                print(f"unknown category: {args.category}", file=sys.stderr)
                return EXIT_USAGE
            print(json.dumps(entry, indent=2))
        else:
            print(json.dumps(profiles, indent=2))
        return EXIT_OK

    universal = [f["id"] for f in profiles["universal"]["telemetry"]]
    names = [args.category] if args.category else sorted(profiles["categories"])

    print(f"RRCF category profiles {profiles['profilesVersion']} "
          f"(RRCF {profiles['rrcfVersion']})")
    print(f"\nMandatory for every category: {', '.join(universal)}")
    print(f"Minimum telemetry rate: {profiles['universal']['minTelemetryHz']} Hz\n")

    for name in names:
        entry = profiles["categories"].get(name)
        if entry is None:
            print(f"unknown category: {name}", file=sys.stderr)
            return EXIT_USAGE
        fields = ", ".join(
            f"{f['id']} [{f['type']}{', ' + f['unit'] if f.get('unit') else ''}]"
            for f in entry["telemetry"]
        ) or "— universal set only"
        axes = " ".join(entry["locomotionAxes"]) or "— none"
        print(f"{name}")
        print(f"  axes      {axes}")
        print(f"  twist     {'required' if entry['requiresTwist'] else 'not required'}")
        print(f"  telemetry {fields}")
        print()

    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    # Shared flags live on a parent parser so they work either before or after
    # the subcommand — `lint --json x.rrcf` and `--json lint x.rrcf` both parse.
    # default=SUPPRESS matters: without it the subparser re-applies its own
    # False default over a flag already set before the subcommand, so
    # `--json lint x.rrcf` would silently lose the flag.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="emit machine-readable output",
    )
    common.add_argument(
        "--quiet",
        action="store_true",
        default=argparse.SUPPRESS,
        help="only report targets that failed",
    )

    parser = argparse.ArgumentParser(
        prog="rrcf-conformance",
        parents=[common],
        description="Check RRCF declarations and recorded sessions for conformance.",
    )
    # Deliberately NOT parser.set_defaults(json=False): set_defaults mutates the
    # shared parent Action, which would restore the False default on the
    # subparser and undo SUPPRESS. Read these with _flag() instead.
    sub = parser.add_subparsers(dest="command", required=True)

    lint = sub.add_parser(
        "lint",
        parents=[common],
        help="layer 1: validate declarations (structure, category profile, self-description)",
    )
    lint.add_argument("declarations", nargs="+", help=".rrcf files or directories")
    lint.set_defaults(func=_cmd_lint)

    session = sub.add_parser(
        "check-session",
        parents=[common],
        help="layer 2: verify a recorded session against its declaration",
    )
    session.add_argument("declaration", help="the .rrcf file")
    session.add_argument("session", help="JSON Lines capture of wire messages")
    session.set_defaults(func=_cmd_check_session)

    profiles = sub.add_parser(
        "profiles", parents=[common], help="show the mandatory field matrix per category"
    )
    profiles.add_argument("--category", help="limit output to one category")
    profiles.set_defaults(func=_cmd_profiles)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
