from collections.abc import Sequence
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field

from box_packer.models import Package, PackedBox, Placement
from box_packer.validation import PositiveFinite

StrictInt = Annotated[int, Field(strict=True)]


class PackageIn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: StrictInt
    width: PositiveFinite
    height: PositiveFinite
    length: PositiveFinite
    weight: PositiveFinite

    def to_domain(self) -> Package:
        return Package(
            id=self.id,
            width=self.width,
            height=self.height,
            length=self.length,
            weight=self.weight,
        )


class PackingResponse(BaseModel):
    box_count: int

    @classmethod
    def from_domain(cls, boxes: Sequence[PackedBox]) -> Self:
        return cls(box_count=len(boxes))


class PlacementOut(BaseModel):
    package_id: int
    x: float
    y: float
    z: float
    dx: float
    dy: float
    dz: float

    @classmethod
    def from_domain(cls, placement: Placement) -> Self:
        return cls(
            package_id=placement.package_id,
            x=placement.x,
            y=placement.y,
            z=placement.z,
            dx=placement.dx,
            dy=placement.dy,
            dz=placement.dz,
        )


class PackedBoxOut(BaseModel):
    box_type: str = Field(description="Name of the catalogue box type to use.")
    package_ids: list[int] = Field(description="Ids of the packages that go in this box.")
    placements: list[PlacementOut] = Field(
        description="Position and oriented extents of each package in the box."
    )


class DebugPackingResponse(BaseModel):
    box_count: int
    boxes: list[PackedBoxOut]

    @classmethod
    def from_domain(cls, boxes: Sequence[PackedBox]) -> Self:
        return cls(
            box_count=len(boxes),
            boxes=[
                PackedBoxOut(
                    box_type=box.box_type.name,
                    package_ids=list(box.package_ids),
                    placements=[PlacementOut.from_domain(p) for p in box.placements],
                )
                for box in boxes
            ],
        )


class ErrorDetail(BaseModel):
    loc: list[str | int] = Field(
        default_factory=list,
        description="Path to the offending value in the request body, e.g. [0, 'width'].",
    )
    package_id: int | None = Field(
        default=None, description="Id of the package concerned, when known."
    )
    type: str = Field(description="Machine-readable error type, e.g. 'greater_than'.")
    message: str


class ErrorResponse(BaseModel):
    code: str = Field(description="Machine-readable error code, e.g. 'validation_error'.")
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)
