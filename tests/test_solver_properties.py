"""Property-based tests: any packing the solver returns must be physically valid."""

from collections import Counter
from collections.abc import Sequence
from itertools import combinations, permutations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from box_packer.catalogue import load_catalogue
from box_packer.geometry import TOLERANCE
from box_packer.models import BoxType, Package, PackedBox, Placement
from box_packer.solver import UnpackablePackagesError, pack

CATALOGUE = load_catalogue()


def _positive(max_value: float) -> st.SearchStrategy[float]:
    # A floor well above TOLERANCE keeps absolute-tolerance comparisons meaningful.
    return st.floats(min_value=0.01, max_value=max_value, allow_nan=False, allow_infinity=False)


@st.composite
def package_lists(
    draw: st.DrawFn, max_side: float, max_weight: float, max_size: int = 25
) -> list[Package]:
    specs = draw(
        st.lists(
            st.tuples(
                _positive(max_side), _positive(max_side), _positive(max_side), _positive(max_weight)
            ),
            max_size=max_size,
        )
    )
    return [Package(i, w, h, length, weight) for i, (w, h, length, weight) in enumerate(specs)]


@st.composite
def catalogues(draw: st.DrawFn) -> list[BoxType]:
    specs = draw(
        st.lists(
            st.tuples(_positive(500), _positive(500), _positive(500), _positive(5000)),
            min_size=1,
            max_size=4,
        )
    )
    return [BoxType(f"T{i}", w, h, length, mw) for i, (w, h, length, mw) in enumerate(specs)]


def fits_alone(package: Package, box_type: BoxType) -> bool:
    """Brute-force oracle, deliberately independent of the solver's fits_in."""
    return package.weight <= box_type.max_weight + TOLERANCE and any(
        all(p <= b + TOLERANCE for p, b in zip(rotation, box_type.dimensions, strict=True))
        for rotation in permutations(package.dimensions)
    )


def overlaps(a: Placement, b: Placement) -> bool:
    return (
        a.x < b.x + b.dx - TOLERANCE
        and b.x < a.x + a.dx - TOLERANCE
        and a.y < b.y + b.dy - TOLERANCE
        and b.y < a.y + a.dy - TOLERANCE
        and a.z < b.z + b.dz - TOLERANCE
        and b.z < a.z + a.dz - TOLERANCE
    )


def assert_valid_packing(
    packages: Sequence[Package], boxes: Sequence[PackedBox], catalogue: Sequence[BoxType]
) -> None:
    by_id = {p.id: p for p in packages}
    placed_ids = [pid for box in boxes for pid in box.package_ids]
    assert Counter(placed_ids) == Counter(p.id for p in packages), "each package packed once"
    assert len(boxes) <= len(packages)

    for box in boxes:
        assert box.box_type in catalogue
        assert box.placements, "no empty boxes"
        weight = sum(by_id[pid].weight for pid in box.package_ids)
        assert abs(box.total_weight - weight) <= TOLERANCE * max(1.0, weight)
        assert weight <= box.box_type.max_weight + TOLERANCE

        bw, bh, bl = box.box_type.dimensions
        for p in box.placements:
            assert sorted((p.dx, p.dy, p.dz)) == sorted(by_id[p.package_id].dimensions)
            assert min(p.x, p.y, p.z) >= -TOLERANCE
            assert p.x + p.dx <= bw + TOLERANCE
            assert p.y + p.dy <= bh + TOLERANCE
            assert p.z + p.dz <= bl + TOLERANCE

        for a, b in combinations(box.placements, 2):
            assert not overlaps(a, b), f"{a} overlaps {b}"


@settings(max_examples=200, deadline=None)
@given(package_lists(max_side=300, max_weight=3000))
def test_packing_with_default_catalogue_is_valid(packages: list[Package]) -> None:
    # Every side <= 300 and weight <= 3000 always fits box C, so nothing is unpackable.
    boxes = pack(packages, CATALOGUE)

    assert_valid_packing(packages, boxes, CATALOGUE)


@settings(max_examples=200, deadline=None)
@given(package_lists(max_side=40, max_weight=50, max_size=40))
def test_small_items_are_consolidated(packages: list[Package]) -> None:
    boxes = pack(packages, CATALOGUE)

    assert_valid_packing(packages, boxes, CATALOGUE)
    total_weight = sum(p.weight for p in packages)
    total_volume = sum(p.volume for p in packages)
    if total_weight <= 1000 and total_volume <= 0.25 * 2_000_000:
        assert len(boxes) <= 1


@settings(max_examples=200, deadline=None)
@given(catalogues(), package_lists(max_side=500, max_weight=5000))
def test_any_catalogue_packs_validly_or_reports_exactly_the_unfit(
    catalogue: list[BoxType], packages: list[Package]
) -> None:
    expected_unfit = [p.id for p in packages if not any(fits_alone(p, b) for b in catalogue)]

    if expected_unfit:
        with pytest.raises(UnpackablePackagesError) as exc_info:
            pack(packages, catalogue)
        assert [u.package_id for u in exc_info.value.packages] == expected_unfit
    else:
        assert_valid_packing(packages, pack(packages, catalogue), catalogue)
