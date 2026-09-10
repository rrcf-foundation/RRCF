# RRCA — RRCF Robot Control Agent

RRCA is the generic device-side runtime between an RRCF controller and a robot, simulator, or cloud robot endpoint. It loads the robot's `.rrcf` declaration, validates RRCF commands, selects the relevant morphology module, loads an endpoint Adapter, and routes normalized command and telemetry messages.

RRCA is part of the portable RRCF architecture. It is not tied to a particular dashboard, fleet product, robot vendor, transport, or simulator.

## Terminology

- **Adopter** — a vendor, integrator, simulator provider, platform, or project that implements RRCF.
- **Adapter** — endpoint-specific bridge code mapping RRCA's normalized controls, skills, and telemetry to a vendor SDK, ROS stack, simulator API, serial protocol, or cloud API.
- **`.rrcf.adptr`** — the portable package containing one Adapter and its manifest. It supplements the target SDK or API; it does not replace it.
- **RRCA** — the generic runtime that loads `.rrcf` and `.rrcf.adptr` artifacts and mediates between controllers and endpoints.
- **RRCF Registry** — the Foundation-governed catalog through which RRCA discovers compatible Adapter releases.

Do not use *adopter* and *adapter* interchangeably. An Adopter may publish one or more Adapters.

## Runtime architecture

```text
RRCF controller / dashboard / VLA
                 |
                 | RRCF command and telemetry envelopes
                 v
+------------------------------------------------+
| RRCA — RRCF Robot Control Agent                |
|  declaration validator                         |
|  category module loader                        |
|  command envelope and bounds validator         |
|  Adapter discovery, verification, lifecycle    |
|  telemetry normalization and routing           |
|  watchdog and safe-state coordination          |
+------------------------+-----------------------+
                         | RRCA Adapter contract
                         v
+------------------------------------------------+
| Endpoint Adapter (.rrcf.adptr)                 |
|  target mapping                                |
|  vendor SDK / ROS / simulator / serial calls   |
|  endpoint telemetry mapping                    |
|  endpoint-specific calibration or tuning       |
+------------------------+-----------------------+
                         |
                         v
              Robot, simulator, or cloud API
```

The controller remains endpoint-neutral. Endpoint-specific work is performed once in the Adapter for a model, SDK family, or simulator integration—not repeatedly in every controller.

## RRCA core responsibilities

An RRCA implementation MUST:

1. Load a standalone or embedded RRCF declaration and reject malformed or unsupported required fields.
2. Select and validate the declared morphology category module.
3. Resolve a compatible Adapter by explicit deployment configuration or Registry lookup.
4. Verify the Adapter manifest, package digest, and compatibility before executing package code.
5. Initialize the Adapter with the declaration and deployment configuration.
6. Validate command type, normalized ranges, declared skill IDs, freshness, and safety envelope before dispatch.
7. Route Adapter telemetry using the field IDs and units declared by `.rrcf`.
8. Coordinate watchdog and target-defined safe-state behavior with the Adapter.
9. Report explicit ready, degraded, rejected, fault, and disconnected states.
10. Keep credentials and unit-specific secrets outside public `.rrcf` declarations and Registry entries.

An RRCA implementation MUST NOT assume that all categories use mobile-base `Twist` semantics. Category modules define their mandatory control and telemetry vocabulary.

## Adapter responsibilities

An Adapter MUST:

1. Declare compatible RRCF, RRCA, endpoint SDK/API, model, platform, and category versions in its manifest, plus endpoint firmware compatibility when applicable.
2. Map declared RRCF controls and skills to the target endpoint.
3. Normalize target telemetry into declared RRCF fields and units.
4. Reject unsupported required capabilities instead of silently ignoring them.
5. Implement or invoke the endpoint's safe-state behavior.
6. Report detected capabilities and any declaration mismatch during initialization.
7. Own endpoint-specific calibration, homing, tuning, or model-drive configuration.

RRCF does not standardize an external calibration record. Calibration may be handled by vendor firmware, a vendor SDK, an Adapter-private file, or a deterministic simulator setup. RRCA only requires the Adapter to report whether initialization and conformance succeeded.

## Category modules

RRCA has one stable core contract. Morphology-specific behavior is supplied by installable category modules, for example:

```text
rrca-mobile       = RRCA core + wheeled/vehicle module
rrca-manipulator  = RRCA core + manipulator module
rrca-legged       = RRCA core + legged/humanoid module
rrca-aerial       = RRCA core + aerial module
```

These may be distributed as small purpose-built runtime images, but they share the same RRCA lifecycle and Adapter package contract. This keeps deployments small without creating incompatible per-category agents.

## Adapter lifecycle

```text
resolve -> verify -> probe -> initialize -> activate -> execute/read -> safe-state -> shutdown
```

Minimum lifecycle behavior:

- **probe** — detect SDK/API availability, model identity, and target version without actuation.
- **initialize** — load endpoint-private configuration and compare detected capabilities with `.rrcf`.
- **activate** — declare the endpoint ready for commands.
- **execute** — accept one validated control or skill command and return accepted/rejected status.
- **read** — emit timestamped telemetry and health.
- **safe-state** — request the endpoint-specific safe response for watchdog, operator stop, or fault.
- **shutdown** — stop command acceptance and release endpoint resources.

The first RRCA Adapter package contract is specified by [`registry/schema/adapter-package-manifest.schema.json`](../registry/schema/adapter-package-manifest.schema.json). External publication records use the separate [`registry/schema/adapter-manifest.schema.json`](../registry/schema/adapter-manifest.schema.json) Registry entry contract. A language-neutral RPC/ABI specification may be added as implementations mature.

## Simulated targets

A simulator is an endpoint, so it uses the same Adapter boundary. An Isaac Sim, MuJoCo, Gazebo, or Genesis Adapter MUST validate at model load time that required controls, target joints/actuators, units, bounds, telemetry sources, update rates, and safe-state behavior can be satisfied.

Any simulator gains, drive modes, damping, or model overlays remain Adapter-private configuration. If a model cannot satisfy the declaration, the Adapter reports non-conformance or a reduced optional capability set; it must not silently claim complete conformance.

## Provisioning and identity

A deployment may provision RRCA with robot identity, API credentials, certificates, Registry trust roots, and an Adapter selection. These are deployment artifacts and MUST NOT be embedded in a public `.rrcf` declaration or public Registry entry.
