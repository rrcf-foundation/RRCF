# RRCF Conformance

How "mandatory" becomes something other than a word in a document.

RRCF's spec prose says a robot MUST publish an e-stop state, MUST declare a
watchdog, MUST publish telemetry on every declared field. Prose alone is
unenforceable — until this directory existed, every one of those requirements
was checkable only by a human reading a PDF and choosing to care.

Enforcement has three layers. They check different things, and none of them
substitutes for the others.

| Layer | What it checks | When | Artifact |
|---|---|---|---|
| 1. Declaration | The `.rrcf` declares everything its category requires, and every declared field self-describes | Authoring, PR review, CI | [`schema/`](schema/), [`profiles/`](profiles/), `rrcf-conformance lint` |
| 2. Runtime | The robot actually publishes what it declared, at the declared rate, inside the declared range | Bring-up, integration test, certification | `rrcf-conformance check-session` |
| 3. Certification | The right to claim RRCF compliance in the market | Foundation review | Trademark + conformance suite (not yet operational) |

---

## The self-description contract

One rule underpins all three layers:

> A generic controller, dashboard, or VLA MUST be able to render and interpret
> every declared telemetry field using only the declaration — no per-robot
> code, no out-of-band documentation, no vendor lookup table. A field that
> cannot be rendered from its own declaration is non-conformant, even if the
> field is present on the wire.

This is why a field carries its own type, unit, and range:

```xml
<field id="battery" type="number" unit="%" min="0" max="100"
       warn_below="20" label="Battery" widget="gauge"/>
```

A controller that has never heard of this robot can now draw a battery gauge,
scale it correctly, and turn it amber at 20% — because everything it needs is
in the declaration. The moment a consumer has to know that *this* vendor's
`soc` means battery percent, the operator layer has stopped being portable and
RRCF has no reason to exist.

Required attributes by field type:

| Type | Required | Notes |
|---|---|---|
| `number`, `integer` | `unit`, `min`, `max` | `unit="1"` for dimensionless ratios, `"%"` for percentages |
| `vector3` | `unit`, `min`, `max` | range applies to each component |
| `enum` | `values` | must enumerate every value the field can emit |
| `boolean`, `string` | — | |

Optional on any field: `label`, `widget`, `warn_below`, `warn_above`,
`frequency_hz`, `description`.

Note the asymmetry between this and mandatory fields. The category profile
decides **whether a field must exist**. The self-description contract decides
**how it must be described once it does**. They are independent clauses, and a
declaration has to satisfy both — a vendor cannot skip the contract by
declaring only mandatory fields, and cannot skip the profile by
self-describing optional ones beautifully.

---

## Layer 1 — declaration-time

[`profiles/category-profiles.json`](profiles/category-profiles.json) is the
source of truth for which fields each of the twelve morphology categories
makes mandatory.
[`schema/rrcf-declaration.schema.json`](schema/rrcf-declaration.schema.json)
is **generated** from it, so the two cannot disagree. CI runs
`gen_schema.py --check` and fails if the checked-in schema has drifted.

The schema is JSON Schema 2020-12 and expresses per-category requirements with
conditional `if`/`then`, so any JSON Schema implementation in any language can
enforce them without reimplementing RRCF logic:

```json
{
  "if":   { "properties": { "primary": { "properties": { "category": { "const": "aerial" }}}}},
  "then": { "properties": { "telemetry": { "contains": {
              "properties": { "id":   { "const": "altitude" },
                              "type": { "const": "number" },
                              "unit": { "const": "m" }}}}}}
}
```

A `.rrcf` file is XML, and JSON Schema cannot validate XML. So the schema
targets the *canonical JSON projection* of a declaration, produced by
[`rrcf_conformance/projection.py`](rrcf_conformance/projection.py). The
projection renames nothing and infers nothing — if it helpfully filled in a
missing unit, the linter would be validating the projector's opinions instead
of what the vendor actually declared.

The linter adds the checks JSON Schema structurally cannot express, because
they compare properties to each other:

- `min` < `max`
- `warn_below` / `warn_above` inside `[min, max]` (otherwise the warning can never fire)
- field and skill ID uniqueness
- every field has a publish rate, from the field or its endpoint, at or above 1 Hz
- `safety/speed_limit` never exceeds declared locomotion capability

**What layer 1 proves:** the declaration is complete and internally consistent.

**What it does not prove:** that the robot publishes any of it.

### Categories are genuinely different

The profiles are not a universal field list with a morphology label attached.
A fixed manipulator declares no locomotion axes, owes no `twist` on the wire,
and is not required to report `battery` — it is bolted to a bench and mains
powered. An aerial vehicle must declare `altitude`, `rssi`, and a `vz` axis.

This resolves a contradiction the spec previously carried: the README and the
website both required a `Twist` sub-object on *every* command message, while
[`architecture/rrca.md`](../architecture/rrca.md) required RRCA to assume the
opposite. `twist` is now required exactly when a category declares locomotion
axes, which is checkable, and checked at layer 2.

What no category is exempt from is the universal set — `estop_state` and
`health` — plus a declared e-stop and watchdog. Safety does not get a
morphology exemption, and `custom` does not get one either.

---

## Layer 2 — runtime

Layer 1 cannot tell the difference between a robot that publishes
`estop_state` and one that merely promises to. A vendor can declare the field
and never emit it, declare 10 Hz and ship 2 Hz, or declare `battery` in
percent and emit volts. All three pass layer 1. All three are caught here.

Input is a recorded session as JSON Lines — one wire message per line, exactly
as transmitted. Any MQTT or WebSocket tap can produce one, as can an MCAP
export; nothing RRCF-specific is needed to capture it.

```bash
rrcf-conformance check-session robot.rrcf session.jsonl
```

Checks:

- every declared field actually appears (`declared-not-published`)
- observed rate meets the declared rate, 10% jitter tolerance (`rate-shortfall`)
- values stay inside declared `min`/`max` (`value-out-of-range`)
- enum values appear in the declared `values` set (`value-not-declared`)
- emitted types match declared types (`type-mismatch`)
- fields published but never declared (`undeclared-field`) — unreadable to a generic consumer
- `twist` present on commands for categories that require it (`twist-missing`)
- `lx`/`ly`/`rx`/`ry` normalized to `[-1, 1]` (`axis-not-normalized`)
- command gaps exceeding the declared watchdog timeout (`watchdog-gap`)

**What layer 2 proves:** the declaration and the robot agree, for the behavior
exercised by the capture.

**What it does not prove:** that the e-stop is wired in hardware independently
of the network link (spec §13). No wire capture can establish that — it needs
physical inspection, which is a certification activity.

---

## Layer 3 — certification

Layers 1 and 2 are opt-in. Nothing technical stops a vendor shipping a broken
declaration and never running either one. There is no way to fix that in
software, and pretending otherwise would be dishonest.

The enforcement mechanism for that gap is the same one USB-IF and the Wi-Fi
Alliance use: a product may not carry the compliance mark without passing the
conformance suite. That makes "mandatory" mean something in the market, where
it matters, by making the claim itself controlled.

This layer is **not operational yet**. It requires a registered trademark, a
published certification policy, and a Foundation process for administering
layers 1 and 2 as an audited suite. Until it exists, RRCF conformance is
self-asserted, and the Registry marks entries `experimental` unless they
publish conformance evidence — see
[`registry/README.md`](../registry/README.md).

---

## Usage

```bash
pip install -r conformance/requirements.txt

# Layer 1 — a file, several files, or a directory tree
python -m rrcf_conformance lint robot.rrcf
python -m rrcf_conformance lint examples/

# Layer 2
python -m rrcf_conformance check-session robot.rrcf session.jsonl

# What does my category actually require?
python -m rrcf_conformance profiles --category aerial

# Machine-readable output for CI
python -m rrcf_conformance --json lint robot.rrcf
```

Installing as a command:

```bash
pip install -e conformance   # provides `rrcf-conformance`
```

Editable install matters: `profiles/` and `schema/` live at stable, citable
repo paths rather than inside the Python package, because the specification
and website link to those URLs. Set `RRCF_CONFORMANCE_DIR` to override.

Exit codes: `0` pass, `1` conformance failure, `2` usage error. Warnings do
not fail a run.

### In CI

[`.github/workflows/conformance.yml`](../.github/workflows/conformance.yml)
runs on every pull request: schema-is-generated check, the test suite, lint on
every declaration in the repo, a negative-fixture check that the invalid
example is *still* rejected, and manifest validation for Registry entries.

---

## Layout

```text
conformance/
├── profiles/category-profiles.json      source of truth — mandatory fields per category
├── schema/rrcf-declaration.schema.json  GENERATED — do not hand-edit
├── tools/gen_schema.py                  generator; --check is the CI drift gate
├── rrcf_conformance/
│   ├── projection.py                    XML .rrcf -> canonical JSON
│   ├── lint.py                          layer 1
│   ├── runtime.py                       layer 2
│   └── cli.py                           rrcf-conformance
├── examples/
│   ├── unitree-go2-z1.rrcf              conformant legged
│   ├── ur5-manipulator.rrcf             conformant manipulator (no twist, no battery)
│   ├── invalid-aerial.rrcf              11 planted defects, all caught
│   ├── go2-session.jsonl                conformant capture
│   └── go2-session-noncompliant.jsonl   9 planted runtime defects
└── tests/test_conformance.py
```

## Adding or changing a requirement

1. Edit `profiles/category-profiles.json`.
2. Run `python conformance/tools/gen_schema.py`.
3. Run `python -m pytest conformance/tests -q`.

A new mandatory field is a **breaking change** for existing declarations. It
belongs in a minor or major RRCF version with a migration note, not a patch —
see [Versioning & governance](../README.md#versioning--governance).

## Status

`profilesVersion` 1.0, targeting RRCF-1.0. The category profiles are a draft
proposal: the specific mandatory field sets need review by implementers before
ratification, and the process for that is the same one used for category
proposals — proposal, 60-day review, three independent implementations,
ratification.

The mechanism is what is being asserted here, not the final field lists.
