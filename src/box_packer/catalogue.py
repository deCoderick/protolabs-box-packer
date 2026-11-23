"""Loading and validation of the shipping box catalogue.

The catalogue lives in ``boxes.json`` next to this module so it is easy to find
and edit. It is validated eagerly so a bad edit fails at startup, not mid-request.
"""

from importlib.resources import files
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from box_packer.models import BoxType
from box_packer.validation import PositiveFinite

type Catalogue = tuple[BoxType, ...]

DEFAULT_CATALOGUE_PATH = Path(str(files("box_packer").joinpath("boxes.json")))


class CatalogueError(Exception):
    """The box catalogue file is missing, unreadable, or invalid."""


class _BoxSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    width: PositiveFinite
    height: PositiveFinite
    length: PositiveFinite
    max_weight: PositiveFinite = Field(alias="maxWeight")


class _CatalogueFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    boxes: tuple[_BoxSpec, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _names_are_unique(self) -> Self:
        names = [box.name for box in self.boxes]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"duplicate box names: {', '.join(duplicates)}")
        return self


def parse_catalogue(raw: str) -> Catalogue:
    """Parse and validate catalogue JSON text."""
    try:
        parsed = _CatalogueFile.model_validate_json(raw)
    except ValidationError as exc:
        raise CatalogueError(f"invalid box catalogue:\n{exc}") from exc
    return tuple(
        BoxType(
            name=spec.name,
            width=spec.width,
            height=spec.height,
            length=spec.length,
            max_weight=spec.max_weight,
        )
        for spec in parsed.boxes
    )


def load_catalogue(path: Path = DEFAULT_CATALOGUE_PATH) -> Catalogue:
    """Read and validate the catalogue file at ``path``."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CatalogueError(f"cannot read box catalogue at {path}: {exc}") from exc
    try:
        return parse_catalogue(raw)
    except CatalogueError as exc:
        raise CatalogueError(f"{path}: {exc}") from exc
