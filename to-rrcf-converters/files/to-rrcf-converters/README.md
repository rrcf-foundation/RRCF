# rrcf-converters

Generates draft RRCF 1.0 (`.rrcf`) operator-interface files from robot
description files. Source format is auto-detected from the root XML tag,
not the file extension (many formats are all saved as plain `.xml`).

| Format | Root tag     | Status                                         |
|--------|--------------|-------------------------------------------------|
| MJCF   | `<mujoco>`   | Supported (needs `pip install mujoco`)          |
| URDF   | `<robot>`    | Supported (pure XML parse, no ROS install)      |
| SDF    | `<sdf>`      | Supported (pure XML parse)                      |
| USD    | n/a          | Detected, not yet converted — see note below    |
| xacro  | n/a          | Detected, not yet converted — run xacro first   |

## Python

```
pip install mujoco --break-system-packages   # only needed for MJCF sources

python3 convert_to_rrcf.py humanoid.xml --vendor "MuJoCo Playground"
python3 convert_to_rrcf.py ur3.urdf --vendor "Universal Robots"
python3 convert_to_rrcf.py model.sdf --category wheeled
```

Run `python3 convert_to_rrcf.py --help` for all flags (`--name`, `--vendor`,
`--category`, `--format`, `--out`).

## Browser (no install)

Open `web/convert_to_rrcf.html` directly in a browser, or serve it from
anywhere. Drag and drop a file — everything runs client-side, nothing is
uploaded. Use this for a quick batch pass over a directory of models without
installing anything.

## Layout

```
convert_to_rrcf.py        CLI router — detects format, dispatches, writes .rrcf
converters/
  common.py                Shared RRCF-builder — format-agnostic, takes an
                            "info" dict (buckets/actuators/sensors) and emits
                            the RRCF XML tree. This is the one place spec
                            changes need to land.
  mjcf.py                   MJCF analyzer (uses the real MuJoCo compiler)
  urdf.py                   URDF analyzer (raw ElementTree parse)
  sdf.py                    SDF analyzer (raw ElementTree parse)
web/
  convert_to_rrcf.html      Browser port of the same logic (MJCF/URDF/SDF
                            analyzers + shared builder, all in one file)
```

Adding a new source format means writing one `analyze(path) -> info_dict`
function (see the shape documented at the top of `converters/common.py`) and
registering it in `convert_to_rrcf.py`'s `ANALYZERS` dict — the RRCF-building
logic doesn't change.

## Important: this is a draft generator, not a certifier

Every `.rrcf` produced here is scaffolding:
- **Morphology category** is a name-based heuristic (hip/knee/ankle → leg,
  shoulder/elbow/wrist → arm, etc.). It's usually right for real robots,
  shakier for generic test/demo scenes. Always check `<primary category>`.
- **`custom_controls` is capped at 5** per the RRCF spec — high-DOF models
  will have unmapped actuators listed in a comment for you to fold into
  `<skills>` or a dedicated `<attach>` block by hand.
- **Skills, safety limits, and transport credentials are stubs.** RRCF spec
  §11 conformance needs real values here before a file drives an actual
  robot — the converter has no way to know your e-stop topic or your
  vendor's skill names.

## On USD

USD (`.usd`/`.usda`) isn't converted yet. It needs the `usd-core` package
and a prim-graph walk rather than a flat XML parse (USD's articulation/joint
data lives in `UsdPhysics` schema prims, not simple tags), which is a
bigger lift than the three formats above. If you have a USD pipeline (e.g.
Isaac Sim), exporting to URDF or MJCF first and converting that is the
practical path for now.
