# RRCF Adapter Registry

The RRCF Adapter Registry is the Foundation-governed catalog of endpoint Adapters that connect RRCA to robot SDKs, ROS stacks, simulators, serial devices, and cloud robot APIs.

The Registry is git-backed so every addition, update, deprecation, and revocation is reviewable and version controlled. Public Registry data never contains device credentials, unit secrets, or private calibration records.

## Registry layout

```text
registry/
├── index.json                              machine-readable catalog
├── schema/
│   ├── adapter-manifest.schema.json        Registry entry schema
│   └── adapter-package-manifest.schema.json in-package manifest schema
├── adapters/
│   └── org.rrcf.ros2.generic.json          bootstrap source reference
└── README.md
```

An installable `.rrcf.adptr` package contains its own `rrcf-adapter.json` identity manifest conforming to `adapter-package-manifest.schema.json`. Its external Registry entry conforms to `adapter-manifest.schema.json` and carries publication status, distribution URL, immutable package digest, and optional signature metadata. Identity and compatibility fields present in both records MUST match; the package does not embed its own archive digest.

## Discovery flow

1. RRCA loads the robot's `.rrcf` declaration and deployment identity.
2. Deployment configuration may select an Adapter ID directly.
3. Otherwise RRCA queries a configured Registry for installable entries compatible with category, vendor/model, RRCF version, RRCA version, target platform, endpoint SDK/API version, and endpoint firmware when applicable.
4. RRCA presents or applies deployment policy when multiple candidates match.
5. RRCA downloads only `distribution.type: "package"` entries, verifies the SHA-256 digest and signature policy, then loads the package.
6. The Adapter probes the endpoint and performs final runtime compatibility checks before activation.

Registry matching is not proof that a physical unit is safe or correctly configured. Runtime probe and conformance checks remain mandatory.

## Entry states

- `experimental` — early integration; interface or behavior may change.
- `verified` — Registry review and published conformance evidence completed.
- `deprecated` — supported only for migration; a replacement should be used.
- `revoked` — must not be installed or activated.

A source-reference entry may be `experimental`, but it is not installable until it publishes a `.rrcf.adptr` distribution with immutable digest metadata.

## Publishing an Adapter

An Adopter submits a pull request containing:

1. One entry under `registry/adapters/<adapter-id>.json`.
2. A manifest-valid Adapter identity and compatibility declaration.
3. Source/provenance and license information.
4. For packaged releases, a `.rrcf.adptr` URL and SHA-256 digest.
5. Conformance evidence or an explicit `experimental` status.
6. A security contact or publisher contact through the referenced publisher profile when publisher profiles are introduced.

The Adapter ID uses reverse-DNS form and is stable across releases, for example:

```text
com.vendor.sdk.robot-family
org.rrcf.ros2.generic
org.rrcf.sim.isaac
```

Package versions follow semantic versioning. A package update changes `adapterVersion`; compatibility metadata must not be silently broadened after publication.

## Review requirements

Registry reviewers check:

- schema validity;
- namespace and publisher authorization;
- model, SDK/API, RRCF, RRCA, category, and platform compatibility;
- HTTPS distribution and exact `.rrcf.adptr` naming for package entries;
- SHA-256 digest format and reproducibility evidence;
- license and source/provenance disclosure;
- no embedded credentials, secrets, or unit calibration data;
- conformance evidence appropriate to the requested status.

The Foundation may deprecate or revoke an entry for security, publisher request, incompatible behavior, or false compatibility claims. Git history remains the public audit trail.

## Private and mirrored registries

Organizations may operate private or mirrored registries using the same index and manifest schemas. RRCA implementations SHOULD allow an explicit Registry trust configuration rather than hard-coding one network location. Private registries are useful for proprietary Adapters and internal robot models.

## Package specification

See [`.rrcf.adptr` Adapter Package Format](../architecture/adapter-package.md) and [RRCA architecture](../architecture/rrca.md).
