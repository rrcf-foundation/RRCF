# RRCF Adoption Guide

Two questions people run into almost immediately with RRCF: *do I even need
this for my use case*, and *if I'm a robot/model provider, should I be
publishing one*. This doc answers both.

## Terminology used in this guide

- **Adopter** — the vendor, integrator, simulator provider, platform, or project adopting RRCF.
- **Adapter** — endpoint-specific bridge code translating between RRCA and a vendor SDK, ROS stack, simulator API, serial protocol, or cloud robot API.
- **`.rrcf.adptr`** — the ZIP-compatible package containing an Adapter and its manifest. It accompanies the SDK or API; it is not the SDK itself.
- **RRCA** — the RRCF Robot Control Agent, the generic runtime that loads a robot declaration and compatible Adapter.
- **Registry** — the Foundation-governed catalog of Adapter compatibility and distribution metadata.

An Adopter may publish several Adapters. The words are intentionally distinct.

---

## 1. When you need a physical file, RRCF, or both

| Use case | Physical file (URDF/MJCF/SDF) | RRCF |
|---|:---:|:---:|
| RL policy training, motion planning, collision checking | required | — |
| Digital-twin visualization or rendering with no human operator | required | — |
| Synthetic data generation for computer vision | required | — |
| Physics-based validation of a mechanical design | required | — |
| Remote fleet dashboard commanding a robot's onboard controller (physics runs elsewhere — onboard, or a separate sim process not co-located with the UI) | — | required |
| VLA agent issuing skill-level commands over MQTT/websocket | — | required |
| Cross-fleet capability browsing — comparing HUD/skills/telemetry across robots, nothing rendered | — | required |
| Operator training on control semantics before touching a real or simulated robot | — | required |
| Sim viewer (MuJoCo/Gazebo web) rendering physics *and* exposing an operator control panel in the same session | required | required |
| Teleoperation UI with a local physics preview alongside operator controls | required | required |
| Checking that RRCF-declared DOF ranges are physically consistent with real joint limits | required | required |
| Auto-generating or regenerating an RRCF draft from a physical file (converters, codegen) | required | required (output) |
| CI check that flags drift between an RRCF and the physical file it references | required | required |

**The dividing line:** if the consumer is a physics engine, planner, or
renderer that only cares about geometry and dynamics, it never touches
RRCF. If the consumer is a human operator interface or an agent issuing
high-level commands, and the physics is happening somewhere else entirely
(real hardware, or a separate process), it never needs to load the physical
file. You only need both loaded in the same process when something is doing
physics rendering *and* exposing operator controls on top of it at the same
time — or when a tool's whole job is reconciling the two files against each
other (conversion, validation, CI drift-checking) rather than using either
one for its primary purpose.

---

## 2. Should you publish an RRCF for your robot?

The Swagger/OpenAPI analogy is the right one: a physical description file is
like your service's internal implementation, and an RRCF is like the public
API contract — it lets any compliant client build a working integration
without reverse-engineering how the thing actually works underneath.

### Who should publish one, and why

| Who | Why publish RRCF | What "publishing" looks like |
|---|---|---|
| Commercial robot vendor | Every third-party fleet console, teleop UI, or VLA integrator would otherwise have to reverse-engineer your control surface per-customer. One RRCF replaces N bespoke integration docs. | Ship it as part of the product's developer/integration docs, versioned with firmware/API releases — not just with mechanical revisions. |
| Open-source / research reference robot maintainer (e.g. a model-library entry) | Makes the model controllable out of the box for anyone building operator tooling against it, not just usable in sim. Near-zero marginal cost via a converter. | Auto-generate a draft alongside the physical file, commit both to the same repo. |
| Simulation platform / model library provider | Breadth: more of your catalog becomes "control-ready," not just "physics-ready." | Batch-run a converter across the catalog; flag `custom`-category / low-confidence results for manual review before publishing. |
| Fleet-management or teleop SaaS aggregating third-party robots | You may not own or have redistribution rights to the OEM's physical file, but you still need to declare your own product's control surface. | Hand-author RRCF per supported robot; `physical_ref` can point at the OEM's file without your needing to host or redistribute it. |
| Systems integrator deploying a single robot internally | No external integrators, but a hand-authored RRCF is still a lightweight source of truth for your own ops dashboard, and de-risks the next person who joins the team and has to build tooling against it. | Keep it in the internal deployment repo; no public distribution needed. |

### When to publish both openly vs. RRCF-only

This is the part that doesn't have a Swagger equivalent, because Swagger
specs don't usually have an IP-sensitive backend implementation attached —
but a URDF/MJCF often does (exact link lengths, mass/inertia, gear ratios,
full mesh geometry).

| Scenario | Physical file | RRCF | Why |
|---|:---:|:---:|:---:|
| Open-source reference platform, research/teaching robot | public, full | public | No mechanical IP to protect; the goal is ecosystem adoption and reproducible sim-to-real research. |
| Commercial vendor protecting mechanical design | private, or a public collision-geometry-only stub | public | Integrators need the control surface (joint names, ranges, skills, safety contract) — not your actual mass properties, link dimensions, or full mesh, which is what a competitor would actually want. |
| Vendor whose physical model feeds a proprietary training/sim pipeline | private | public | The dynamics-accurate model is a training-data asset you don't want handed to competitors for free; the control contract is what customers are actually paying to integrate against. |
| Fleet-SaaS aggregating other vendors' robots | not owned/hosted by you | public (yours, hand-authored) | You're describing *your* integration surface, not redistributing someone else's IP. |
| Internal single-deployment robot | private (internal repo) | private (internal repo) | No external audience for either. |

**The practical takeaway:** RRCF is designed to be useful on exactly the
information an integrator actually needs — actuator names, ranges, skills,
safety contract, telemetry schema — none of which requires disclosing mass
properties, precise geometry, or full mesh data. That's what makes
"private URDF, public RRCF" a coherent, common pattern rather than an edge
case: you can hand-author the control-surface declaration directly from
your API docs without ever exporting the underlying physical file.

### An open question for the spec

`physical_ref` currently expects a resolvable `path`. For the "private
physical file" pattern above, that path may not be something an external
consumer can ever fetch — worth deciding whether `physical_ref` should
support a non-dereferenceable mode (e.g. an internal identifier with no
guarantee of public resolution, or simply omitting `path` and keeping only
`format`) so vendors aren't forced to either expose the file or leave the
reference field semantically dishonest.

---

## 3. Which artifacts should an Adopter publish?

A complete endpoint integration has separate design-time and runtime artifacts:

| Artifact | Purpose | Typical publisher | Public? |
|---|---|---|---|
| `robot.rrcf` | Declares model identity, controls, skills, telemetry, limits, and transports | Robot/model vendor | Usually public |
| `vendor.robot.rrcf.adptr` | Maps the declaration to the vendor SDK/API or simulator | Vendor or integrator | Public, private, or Registry-linked |
| Vendor SDK/API | Performs actual endpoint communication and vendor control behavior | Vendor | According to vendor license |
| Deployment configuration | Selects unit identity, credentials, endpoints, and Adapter | Robot owner/operator | Private |
| Physical file | Geometry, kinematics, and dynamics for simulation/planning | Vendor/model provider | Public or private |

The `.rrcf` XML declaration and `.rrcf.adptr` package are intentionally different. The declaration is portable data consumed by controllers and RRCA. The package is executable Adapter code installed alongside its declared vendor SDK/API dependency.

Recommended vendor publication flow:

1. Publish and version `robot.rrcf` with the model's firmware/API compatibility.
2. Implement one Adapter for the model or SDK family.
3. Package it as `<publisher>.<vendor>.<model>.<version>.rrcf.adptr`.
4. Declare SDK/API, model, applicable endpoint firmware, category, RRCF, RRCA, operating-system, architecture, and capability compatibility in `rrcf-adapter.json`.
5. Test declaration-to-endpoint control, telemetry, skills, mismatch handling, watchdog, and safe-state behavior.
6. Submit the Adapter to the Foundation Registry with package digest, license, provenance, and conformance evidence.
7. Keep unit credentials and unit-specific calibration outside all public artifacts.

Once that Adapter is available, controller and UI providers consume the model's `.rrcf` declaration without writing their own vendor SDK integration.

### Calibration and tuning

RRCF does not define a standardized calibration record. Calibration ownership stays with the endpoint implementation:

- vendor firmware may load factory calibration;
- a vendor SDK may run homing or load its own persisted file;
- an Adapter may manage a private calibration or tuning file;
- a simulator Adapter may derive or load deterministic gains and drive settings.

RRCA validates that Adapter initialization succeeds, but it does not parse or modify calibration data. Public Registry entries describe calibration ownership only so an operator knows what prerequisite exists.

---

## 4. Publishing through the RRCF Adapter Registry

The [RRCF Adapter Registry](registry/README.md) is the Foundation-governed index used to discover compatible Adapters. It is git-backed: additions, version changes, deprecations, and revocations are submitted as reviewed pull requests.

A Registry record declares:

- stable reverse-DNS Adapter ID;
- publisher, vendor, and supported models;
- RRCF compatibility, plus RRCA compatibility for installable packages;
- morphology categories;
- target SDK/API or simulator and its compatible versions;
- supported platforms and capabilities;
- calibration ownership metadata;
- source or `.rrcf.adptr` distribution;
- package SHA-256 and signature metadata when required by the Registry or deployment trust profile for installable releases;
- license, status, and conformance evidence.

Registry entries never contain device credentials, unit secrets, or private calibration files. Proprietary Adopters may use a private Registry implementing the same schemas.

### Registry status levels

- **experimental** — useful for evaluation; compatibility or behavior may change.
- **verified** — reviewed with published conformance evidence.
- **deprecated** — maintained only for migration.
- **revoked** — must not be installed or activated.

The current ROS 2 bridge is listed as an experimental source reference. A source reference is discoverable documentation, not an RRCA-installable package. Installable production entries distribute immutable `.rrcf.adptr` bytes with a published digest.
