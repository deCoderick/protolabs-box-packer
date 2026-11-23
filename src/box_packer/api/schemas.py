from collections.abc import Sequence
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field

from box_packer.models import Package, PackedBox
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


class PackedBoxOut(BaseModel):
    box_type: str = Field(description="Name of the catalogue box type to use.")
    package_ids: list[int] = Field(description="Ids of the packages that go in this box.")


class PackingResponse(BaseModel):
    box_count: int
    boxes: list[PackedBoxOut]

    @classmethod
    def from_domain(cls, boxes: Sequence[PackedBox]) -> Self:
        return cls(
            box_count=len(boxes),
            boxes=[
                PackedBoxOut(box_type=box.box_type.name, package_ids=list(box.package_ids))
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
