import json
from pathlib import Path
from typing import Any

import pytest

from box_packer.catalogue import CatalogueError, load_catalogue, parse_catalogue
from box_packer.models import BoxType


def _box(**overrides: Any) -> dict[str, Any]:
    box: dict[str, Any] = {
        "name": "X",
        "width": 10,
        "height": 20,
        "length": 30,
        "maxWeight": 100,
    }
    box.update(overrides)
    return box


def _catalogue_json(*boxes: dict[str, Any]) -> str:
    return json.dumps({"boxes": list(boxes)})


def test_default_catalogue_matches_spec() -> None:
    assert load_catalogue() == (
        BoxType(name="A", width=150, height=150, length=150, max_weight=1000),
        BoxType(name="B", width=100, height=200, length=100, max_weight=1000),
        BoxType(name="C", width=300, height=400, length=300, max_weight=3000),
    )


def test_accepts_fractional_values() -> None:
    (box,) = parse_catalogue(_catalogue_json(_box(width=10.5, maxWeight=99.25)))

    assert box.width == 10.5
    assert box.max_weight == 99.25


def test_integers_are_coerced_to_float() -> None:
    (box,) = parse_catalogue(_catalogue_json(_box()))

    assert isinstance(box.width, float)


def test_loads_from_custom_path(tmp_path: Path) -> None:
    path = tmp_path / "boxes.json"
    path.write_text(_catalogue_json(_box(name="Tube", width=50, height=50, length=500)))

    (box,) = load_catalogue(path)

    assert box == BoxType(name="Tube", width=50, height=50, length=500, max_weight=100)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("width", 0),
        ("height", -1),
        ("length", -0.5),
        ("maxWeight", 0),
        ("maxWeight", -1),
        ("width", True),
        ("width", "150"),
        ("width", None),
        ("name", ""),
    ],
)
def test_rejects_invalid_field_values(field: str, value: Any) -> None:
    with pytest.raises(CatalogueError, match=field):
        parse_catalogue(_catalogue_json(_box(**{field: value})))


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_rejects_non_finite_numbers(literal: str) -> None:
    raw = _catalogue_json(_box()).replace('"width": 10', f'"width": {literal}')

    with pytest.raises(CatalogueError, match="width"):
        parse_catalogue(raw)


@pytest.mark.parametrize("field", ["name", "width", "height", "length", "maxWeight"])
def test_rejects_missing_field(field: str) -> None:
    box = _box()
    del box[field]

    with pytest.raises(CatalogueError, match=field):
        parse_catalogue(_catalogue_json(box))


def test_rejects_unknown_field_to_catch_typos() -> None:
    with pytest.raises(CatalogueError, match="widht"):
        parse_catalogue(_catalogue_json(_box(widht=10)))


def test_rejects_empty_catalogue() -> None:
    with pytest.raises(CatalogueError, match="boxes"):
        parse_catalogue(_catalogue_json())


def test_rejects_duplicate_box_names() -> None:
    with pytest.raises(CatalogueError, match="duplicate box names: A"):
        parse_catalogue(_catalogue_json(_box(name="A"), _box(name="A"), _box(name="B")))


def test_rejects_malformed_json() -> None:
    with pytest.raises(CatalogueError, match="invalid box catalogue"):
        parse_catalogue('{"boxes": [')


def test_missing_file_raises_catalogue_error(tmp_path: Path) -> None:
    with pytest.raises(CatalogueError, match="cannot read box catalogue"):
        load_catalogue(tmp_path / "nope.json")


def test_invalid_file_error_mentions_path(tmp_path: Path) -> None:
    path = tmp_path / "boxes.json"
    path.write_text(_catalogue_json(_box(width=-1)))

    with pytest.raises(CatalogueError, match=str(path)):
        load_catalogue(path)
