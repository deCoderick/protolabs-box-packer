"""Core domain types for the packing engine.

These are plain frozen dataclasses with no framework dependencies. They assume
their inputs are already valid: validation happens at the boundaries (catalogue
loading and the HTTP layer), so the solver can trust what it receives.

Axis convention used throughout: x runs along width, y along height, z along length.
"""

from dataclasses import dataclass

type Dimensions = tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class Package:
    id: int
    width: float
    height: float
    length: float
    weight: float

    @property
    def dimensions(self) -> Dimensions:
        return (self.width, self.height, self.length)

    @property
    def volume(self) -> float:
        return self.width * self.height * self.length


@dataclass(frozen=True, slots=True)
class BoxType:
    name: str
    width: float
    height: float
    length: float
    max_weight: float

    @property
    def dimensions(self) -> Dimensions:
        return (self.width, self.height, self.length)

    @property
    def volume(self) -> float:
        return self.width * self.height * self.length


@dataclass(frozen=True, slots=True)
class Placement:
    """A package positioned inside a box.

    (x, y, z) is the corner of the package nearest the box origin; (dx, dy, dz)
    are its extents along each box axis after rotation, so the package occupies
    [x, x + dx) x [y, y + dy) x [z, z + dz).
    """

    package_id: int
    x: float
    y: float
    z: float
    dx: float
    dy: float
    dz: float


@dataclass(frozen=True, slots=True)
class PackedBox:
    box_type: BoxType
    placements: tuple[Placement, ...]
    total_weight: float

    @property
    def package_ids(self) -> tuple[int, ...]:
        return tuple(p.package_id for p in self.placements)
