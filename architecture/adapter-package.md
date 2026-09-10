# `.rrcf.adptr` Adapter Package Format

A `.rrcf.adptr` file is a ZIP-compatible package containing the code and metadata needed to connect RRCA to one endpoint family. It is separate from the robot's XML `.rrcf` declaration and is installed in addition to any required vendor SDK.

## Naming

Recommended filename:

```text
<publisher>.<vendor>.<model-or-family>.<adapter-version>.rrcf.adptr
```

Example:

```text
com.example.acme.rover-x.1.2.0.rrcf.adptr
```

The filename is informational. RRCA uses the package manifest identity and Registry-published package digest as authoritative identifiers, and verifies a signature when required by the configured trust policy.

The in-package manifest MUST conform to [`registry/schema/adapter-package-manifest.schema.json`](../registry/schema/adapter-package-manifest.schema.json). It contains package identity and runtime compatibility only. Archive URL, package SHA-256, publication status, and conformance evidence belong to the external Registry entry, because an archive cannot contain its own final digest.

## Archive layout

```text
com.example.acme.rover-x.1.2.0.rrcf.adptr
├── rrcf-adapter.json       required manifest
├── payload/                Adapter executable/module and runtime files
├── LICENSE                 required license or license reference
├── README.md               recommended setup and SDK prerequisites
└── tests/                  optional self-test and conformance fixtures
```

The archive root MUST contain `rrcf-adapter.json`. Archives MUST use relative paths and MUST NOT contain entries that escape the extraction directory.

## Relationship to the vendor SDK

The package is a translation and lifecycle layer:

```text
RRCA -> .rrcf.adptr Adapter -> vendor SDK/API -> robot
```

A package may:

- declare an externally installed SDK dependency;
- include redistributable SDK runtime components when licensing permits;
- call a local ROS service, serial device, simulator API, or vendor cloud API;
- include Adapter-private configuration templates.

It does not replace the vendor SDK and does not grant credentials. SDK licenses, device credentials, and unit secrets remain deployment concerns.

## Calibration boundary

Calibration is not an RRCF package-level interchange format. If the endpoint requires calibration, the Adapter may load a vendor calibration file, invoke a firmware homing routine, derive deterministic simulator settings, or use another endpoint-specific mechanism. Such files may be bundled only when they are model-level and redistributable; unit-specific calibration and secrets MUST remain outside public packages and Registry records.

The manifest's `calibrationOwnership` field is descriptive so deployers understand prerequisites. RRCA does not interpret calibration data.

## Integrity and publication

A released package Registry entry MUST include:

- exact filename ending in `.rrcf.adptr`;
- HTTPS download URL;
- SHA-256 digest of the package bytes;
- publisher identity;
- package version and compatibility ranges;
- license and source/provenance information;
- signature information when the Registry signing profile is available.

Changing package bytes requires a new Adapter version and Registry review. A published digest is immutable.

## Source-reference entries

During Registry bootstrap, a reference implementation may be listed with `distribution.type: "source"`. It is discoverable documentation, but RRCA MUST NOT treat it as an installable verified package. Production entries use `distribution.type: "package"`.
