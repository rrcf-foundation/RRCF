"""RRCF conformance tooling.

Two mechanically checkable enforcement layers:

- ``lint``    — layer 1, declaration-time. Does the .rrcf declare everything
                its category makes mandatory, and does every declared field
                satisfy the self-description contract?
- ``runtime`` — layer 2, operation-time. Does the robot actually publish what
                it declared, at the declared rate, within the declared range?

Layer 3 — certification and the right to use the "RRCF Compliant" mark — is a
governance mechanism, not a library. See conformance/README.md.
"""

from .lint import Finding, Report, lint_declaration, lint_file
from .projection import ProjectionError, project_file, project_string
from .runtime import Session, check_session_data, check_session_files, load_session

__all__ = [
    "Finding",
    "ProjectionError",
    "Report",
    "Session",
    "check_session_data",
    "check_session_files",
    "lint_declaration",
    "lint_file",
    "load_session",
    "project_file",
    "project_string",
]

__version__ = "0.1.0"
