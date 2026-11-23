## Box Packer

A small FastAPI service: send it a list of packages, get back how many shipping boxes they need and which packages go in each box.

### Quick start

Requires [uv](https://docs.astral.sh/uv/) (it fetches the pinned Python 3.13 itself) or Docker.

| Command | What it does |
|---|---|
| `make run` | Install deps and serve on `http://127.0.0.1:8000` with auto-reload (`uv run uvicorn box_packer.main:app --reload`) |
| `make docker` | Build and run the container on `http://127.0.0.1:8000` (`docker compose up --build`) |
| `make test` | Run the test suite (`uv run pytest`) |
| `make check` | `ruff` lint + format check, `mypy --strict`, then `pytest` |

Interactive docs are at `http://127.0.0.1:8000/docs`. Try the spec's example payload:

```bash
curl -s -X POST http://127.0.0.1:8000/packing \
  -H 'Content-Type: application/json' \
  -d '[{ "id": 123, "width": 10, "height": 10, "length": 10, "weight": 5 },
       { "id": 125, "width": 5, "height": 5, "length": 10, "weight": 10 }]'
```

```json
{"box_count":1,"boxes":[{"box_type":"B","package_ids":[123,125]}]}
```

### API contract

**`POST /packing`**: the request body is a bare JSON array of packages, exactly as in the spec.

| Field | Type | Rule |
|---|---|---|
| `id` | integer | Required, unique within the request. Booleans, strings and floats are rejected. |
| `width`, `height`, `length` | number | Required, `> 0`, finite. Decimals allowed (`10.5`). |
| `weight` | number | Required, `> 0`, finite. |

Unknown fields are rejected. At most **1,000 packages** per request.

**`200 OK`**: `box_count` plus one entry per box, naming the box type and the packages inside it. An empty list returns `{"box_count": 0, "boxes": []}`.

**`GET /health`**: `{"status": "ok"}`.

#### Errors

Every error, including 404/405/500, uses the same envelope:

```json
{
  "code": "unpackable_packages",
  "message": "Some packages do not fit in any available box.",
  "details": [
    {"loc": [0], "package_id": 99, "type": "too_large",
     "message": "Package 99 is larger than every box, in any orientation."}
  ]
}
```

`loc` is the path into the request body (e.g. `[2, "width"]`), and `type` is a machine-readable reason. All problems are reported at once, not just the first one.

| Status | `code` | When | Example `details[].type` |
|---|---|---|---|
| 400 | `invalid_json` | Body is not parseable JSON | `json_invalid` |
| 422 | `validation_error` | Valid JSON with the wrong shape or values: not an array, missing/extra/mistyped fields, `<= 0`, `NaN`/`Infinity`, more than 1,000 packages | `list_type`, `missing`, `extra_forbidden`, `int_type`, `greater_than`, `finite_number`, `too_long` |
| 422 | `duplicate_package_ids` | Two or more packages share an id (every occurrence is listed) | `duplicate_id` |
| 422 | `unpackable_packages` | A package fits in no box type on its own | `too_large`, `too_heavy`, `too_large_and_too_heavy`, `no_box_fits_size_and_weight` |
| 404 / 405 | `not_found` / `method_not_allowed` | Unknown route or method | - |
| 500 | `internal_error` | Unexpected bug; internals are logged, never returned | - |

**400 vs 422:** a body that can't be parsed as JSON is a malformed request (400). Valid JSON that breaks the contract is understood but can't be processed (422).

### Editing the box catalogue

Boxes live in [`src/box_packer/boxes.json`](src/box_packer/boxes.json):

```json
{ "name": "A", "width": 150, "height": 150, "length": 150, "maxWeight": 1000 }
```

The file is validated once, when the app starts (`create_app()`), so a bad edit stops the service immediately rather than failing on a later request. It must contain at least one box, names must be unique, every number must be finite and `> 0`, and unknown keys (typos like `"widht"`) are rejected. Tests and callers can pass a different catalogue with `create_app(catalogue=...)`.

### Packing approach

The engine is pure Python with no FastAPI imports: `geometry.py` holds the 3D helpers and `solver.py` holds the strategy.

1. **Reject unpackable packages up front.** Any package that no box type can hold on its own (by size *and* weight) is reported, all at once, before packing starts.
2. **Sort** packages by volume descending, then weight, then id, so the same input always produces the same output.
3. **Place each package with real 3D coordinates** (guillotine free-space splitting):
   - Each box keeps a list of empty cuboids.
   - A package goes into the corner of the tightest empty cuboid it fits, trying all **6 orientations**.
   - The leftover is cut into up to three **disjoint** cuboids: beside the package, above it, and in front of it. Slivers thinner than `1e-9` are dropped.
   - Because empty spaces never overlap each other or a placed package, every result is physically valid.
4. **Open new boxes generously.** If no open box has room, open the **largest box type that can hold this package**. This deliberately avoids opening the smallest box that fits, which wastes boxes: two 120-cubes would take two A boxes, but share one C.
5. **Downsize each finished box** by re-packing its contents into smaller box types, smallest volume first, and keeping the first that fits. Two 100-cubes are opened in a C and end up stacked in one B.

All size and weight comparisons use a **`1e-9` absolute tolerance**, so exact fits survive float rounding (three 0.1-wide items fit in a 0.3-wide box).

**Why not compare volumes?** Volume alone gives false positives. Three 160-cubes take up only 34% of box C, but only two physically fit (160 + 160 + 160 > 400). A packing the warehouse cannot actually close is a correctness bug. An extra box is only an inefficiency.

**Box C dominance.** C (300 × 400 × 300, 3000) is at least as large as A and B on every axis, even after rotation, and on weight. With this catalogue, C can hold anything A or B can, so step 4 always opens a C and step 5 shrinks it to A or B when the contents allow. The solver still compares boxes per package rather than hard-coding C, so a non-dominated box added to `boxes.json` (e.g. a 50 × 50 × 500 tube) is used correctly; there is a test for exactly that.

#### How it's tested

- **Unit tests** (`test_geometry.py`, `test_solver.py`): exact fits, rotation, the volume trap and the smallest-box-first trap, weight limits, float rounding, custom catalogues, and every unpackable reason.
- **Property-based tests** (`test_solver_properties.py`, Hypothesis): on random orders and random catalogues they check that every package is packed exactly once, no box is over its weight limit, every package is inside its box and is a rotation of its real size, and no two packages overlap. Unpackable reports are checked against a separate brute-force fit check.
- **API tests** (`test_api.py`): the spec payload, the empty list, duplicates, unpackable packages, every invalid-input case, and the error format.

### Assumptions and design decisions

- **Input is a bare JSON array**, so the spec's example payload works as-is.
- **Package ids must be unique**; duplicates get a 422. Ids are integers (as in the spec) and can be any integer.
- **An empty list is valid** and needs 0 boxes.
- **Units are unitless.** Package and box values are assumed to use the same units.
- **Items can rotate freely** into any axis-aligned orientation. There is no "this side up", stacking-load or fragility rule.
- **A box's weight limit covers its contents only.** The box's own weight is ignored.
- **Fewest boxes is the only objective.** Among equally good results, the smaller box (by volume) is preferred, not the cheapest.
- **Box tie-breaks:** volume, then weight limit, then name. All ordering is deterministic.
- **The route is a sync `def`.** Packing is CPU-bound, so FastAPI runs it in its threadpool instead of blocking the event loop the way an `async def` would.
- **Requests are capped at 1,000 packages**, because runtime grows roughly quadratically (about 0.6 s for 1,000 mixed packages on a laptop).

### Known limitations and what I'd do with more time

- **Empty spaces are never merged.** This keeps placement simple and always physically valid, at the cost of some extra boxes. Example: three slabs that exactly fill box C, (160×400×240), (140×400×240) and (300×400×60), take 2 boxes. The first two leave two side-by-side 400×60 gaps, 160 and 140 wide, and the 300-wide slab fits neither one alone. This is pinned as a strict `xfail` test. Next step: maximal-space tracking or merging adjacent empty spaces, then compare box counts on a benchmark set.
- **O(N²)-ish runtime.** Each placement scans the free spaces of every open box. Indexing free spaces by size would help much larger orders.
- **Box count is the only cost.** Real shipping would optimise price, including dimensional weight, and possibly let the client choose.
- **Per-package constraints:** `upright` (fixed height axis) and `fragile` (nothing stacked on top) flags would fit in via the `orientations()` step and placement checks.
- **Return placement coordinates.** The solver already tracks each package's position and orientation; exposing them (behind a query flag) would give warehouse staff packing instructions.
- **Operational polish:** request IDs and structured logging, and a published benchmark of heuristic quality against lower bounds.

### Project layout

```text
src/box_packer/
  boxes.json       box catalogue (edit me)
  catalogue.py     loads + validates boxes.json
  models.py        framework-free domain dataclasses
  validation.py    shared PositiveFinite input rule
  geometry.py      free spaces, rotations, fit check, guillotine split
  solver.py        packing strategy + unpackable detection
  api/             FastAPI schemas, error envelope/handlers, routes
  main.py          create_app(): wiring + catalogue injection
tests/             unit, property-based and API tests
```
