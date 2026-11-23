"""Axis-aligned 3D geometry used by the packer: free spaces, rotations, fits and splits."""

from dataclasses import dataclass
from itertools import permutations

from box_packer.models import Dimensions

# Absolute tolerance for every size/weight comparison, so values that fit exactly
# (e.g. 0.1 + 0.1 + 0.1 into 0.3) are not rejected due to float rounding.
TOLERANCE = 1e-9


@dataclass(frozen=True, slots=True)
class Space:
    """An empty cuboid inside a box: corner (x, y, z), extents (dx, dy, dz)."""

    x: float
    y: float
    z: float
    dx: float
    dy: float
    dz: float

    @property
    def volume(self) -> float:
        return self.dx * self.dy * self.dz

    def can_hold(self, size: Dimensions) -> bool:
        sx, sy, sz = size
        return sx <= self.dx + TOLERANCE and sy <= self.dy + TOLERANCE and sz <= self.dz + TOLERANCE


def orientations(dims: Dimensions) -> tuple[Dimensions, ...]:
    """All distinct axis-aligned rotations of ``dims`` (1, 3 or 6 of them)."""
    return tuple(dict.fromkeys(permutations(dims, 3)))


def fits_in(item: Dimensions, container: Dimensions) -> bool:
    """Whether ``item`` fits inside ``container`` in some axis-aligned rotation.

    Pairing the sorted extents is sufficient: if any rotation fits, the one that
    matches smallest-to-smallest, ..., largest-to-largest also fits.
    """
    return all(i <= c + TOLERANCE for i, c in zip(sorted(item), sorted(container), strict=True))


def split(space: Space, size: Dimensions) -> list[Space]:
    """Place an item of ``size`` at the corner of ``space`` and return the leftover.

    The leftover is cut into at most three pairwise-disjoint cuboids (a guillotine
    split), which together with the item exactly tile ``space``:

    - beside the item along x, spanning the full height and length of ``space``;
    - above the item along y, over the item's width and the full length;
    - in front of the item along z, over the item's width and height.

    Slivers with any extent <= TOLERANCE are dropped; nothing can be placed in them.
    """
    dx, dy, dz = size
    leftovers = (
        Space(space.x + dx, space.y, space.z, space.dx - dx, space.dy, space.dz),
        Space(space.x, space.y + dy, space.z, dx, space.dy - dy, space.dz),
        Space(space.x, space.y, space.z + dz, dx, dy, space.dz - dz),
    )
    return [s for s in leftovers if min(s.dx, s.dy, s.dz) > TOLERANCE]
