"""Packing engine: assigns packages to as few boxes as a greedy heuristic can find.

Strategy (First-Fit Decreasing with 3D guillotine placement):

1. Reject up front every package that no single box type can hold (size and
   weight), reporting all of them at once.
2. Sort packages largest-volume first (then heaviest, then by id for determinism).
3. Place each package into the first open box with room for it, trying the
   tightest free space first and every rotation. If none has room, open the
   largest box type that can hold the package, so later items can share it.
4. Downsize each finished box: re-pack its contents into smaller box types,
   smallest volume first, and keep the first that holds them all.

Placement tracks real coordinates, so a result is always physically valid; the
heuristic may use more boxes than optimal, but never claims an impossible fit.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from box_packer.geometry import TOLERANCE, Space, fits_in, orientations, split
from box_packer.models import BoxType, Dimensions, Package, PackedBox, Placement


class UnpackableReason(StrEnum):
    TOO_LARGE = "too_large"
    TOO_HEAVY = "too_heavy"
    TOO_LARGE_AND_TOO_HEAVY = "too_large_and_too_heavy"
    NO_BOX_FITS_SIZE_AND_WEIGHT = "no_box_fits_size_and_weight"


@dataclass(frozen=True, slots=True)
class UnpackablePackage:
    package_id: int
    reason: UnpackableReason


class UnpackablePackagesError(Exception):
    def __init__(self, packages: Sequence[UnpackablePackage]) -> None:
        self.packages = tuple(packages)
        ids = ", ".join(str(p.package_id) for p in self.packages)
        super().__init__(f"packages that fit in no available box: {ids}")


def pack(packages: Sequence[Package], catalogue: Sequence[BoxType]) -> tuple[PackedBox, ...]:
    """Pack ``packages`` into boxes from ``catalogue``.

    Raises UnpackablePackagesError if any package cannot fit in any box type.
    """
    if unpackable := find_unpackable(packages, catalogue):
        raise UnpackablePackagesError(unpackable)

    boxes: list[_OpenBox] = []
    for package in sorted(packages, key=_packing_order):
        for box in boxes:
            if box.try_place(package):
                break
        else:
            box = _OpenBox(_largest_type_accepting(package, catalogue))
            placed = box.try_place(package)
            assert placed, "a box type that accepts the package must hold it when empty"
            boxes.append(box)

    return tuple(_downsize(box, catalogue) for box in boxes)


def find_unpackable(
    packages: Sequence[Package], catalogue: Sequence[BoxType]
) -> tuple[UnpackablePackage, ...]:
    return tuple(
        UnpackablePackage(package.id, reason)
        for package in packages
        if (reason := _unpackable_reason(package, catalogue)) is not None
    )


def _unpackable_reason(package: Package, catalogue: Sequence[BoxType]) -> UnpackableReason | None:
    if any(_accepts(box_type, package) for box_type in catalogue):
        return None
    fits_some_size = any(fits_in(package.dimensions, b.dimensions) for b in catalogue)
    fits_some_weight = any(package.weight <= b.max_weight + TOLERANCE for b in catalogue)
    match fits_some_size, fits_some_weight:
        case False, False:
            return UnpackableReason.TOO_LARGE_AND_TOO_HEAVY
        case False, True:
            return UnpackableReason.TOO_LARGE
        case True, False:
            return UnpackableReason.TOO_HEAVY
        case _:
            return UnpackableReason.NO_BOX_FITS_SIZE_AND_WEIGHT


def _accepts(box_type: BoxType, package: Package) -> bool:
    """Whether an empty box of this type can hold the package on its own."""
    return package.weight <= box_type.max_weight + TOLERANCE and fits_in(
        package.dimensions, box_type.dimensions
    )


def _packing_order(package: Package) -> tuple[float, float, int]:
    return (-package.volume, -package.weight, package.id)


def _smallest_first(box_type: BoxType) -> tuple[float, float, str]:
    return (box_type.volume, box_type.max_weight, box_type.name)


def _largest_type_accepting(package: Package, catalogue: Sequence[BoxType]) -> BoxType:
    candidates = [b for b in catalogue if _accepts(b, package)]
    return max(candidates, key=_smallest_first)


def _downsize(box: "_OpenBox", catalogue: Sequence[BoxType]) -> PackedBox:
    for candidate in sorted(catalogue, key=_smallest_first):
        if candidate.volume >= box.box_type.volume:
            break
        if (repacked := _pack_into_one(box.packages, candidate)) is not None:
            return repacked.freeze()
    return box.freeze()


def _pack_into_one(packages: Sequence[Package], box_type: BoxType) -> "_OpenBox | None":
    box = _OpenBox(box_type)
    if all(box.try_place(package) for package in packages):
        return box
    return None


def _space_preference(space: Space) -> tuple[float, float, float, float]:
    """Tightest space first (best fit), then lowest, then nearest the back-left corner."""
    return (space.volume, space.y, space.z, space.x)


class _OpenBox:
    """A box being filled. Its free spaces are disjoint and never overlap placements."""

    def __init__(self, box_type: BoxType) -> None:
        self.box_type = box_type
        self.free_spaces = [Space(0.0, 0.0, 0.0, *box_type.dimensions)]
        self.packages: list[Package] = []
        self.placements: list[Placement] = []
        self.weight = 0.0

    def try_place(self, package: Package) -> bool:
        if self.weight + package.weight > self.box_type.max_weight + TOLERANCE:
            return False
        for space in sorted(self.free_spaces, key=_space_preference):
            for size in orientations(package.dimensions):
                if space.can_hold(size):
                    self._place(package, space, size)
                    return True
        return False

    def _place(self, package: Package, space: Space, size: Dimensions) -> None:
        self.free_spaces.remove(space)
        self.free_spaces.extend(split(space, size))
        self.placements.append(Placement(package.id, space.x, space.y, space.z, *size))
        self.packages.append(package)
        self.weight += package.weight

    def freeze(self) -> PackedBox:
        return PackedBox(
            box_type=self.box_type,
            placements=tuple(self.placements),
            total_weight=self.weight,
        )
