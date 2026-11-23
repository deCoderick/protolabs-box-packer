import pytest

from box_packer.catalogue import load_catalogue
from box_packer.models import BoxType, Package, PackedBox
from box_packer.solver import (
    UnpackablePackage,
    UnpackablePackagesError,
    UnpackableReason,
    pack,
)

CATALOGUE = load_catalogue()


def cube(package_id: int, side: float, weight: float = 1) -> Package:
    return Package(id=package_id, width=side, height=side, length=side, weight=weight)


def summary(boxes: tuple[PackedBox, ...]) -> list[tuple[str, list[int]]]:
    return [(box.box_type.name, sorted(box.package_ids)) for box in boxes]


def test_empty_input_needs_no_boxes() -> None:
    assert pack([], CATALOGUE) == ()


def test_spec_example_fits_in_one_box() -> None:
    packages = [
        Package(id=123, width=10, height=10, length=10, weight=5),
        Package(id=125, width=5, height=5, length=10, weight=10),
    ]

    boxes = pack(packages, CATALOGUE)

    assert summary(boxes) == [("B", [123, 125])]
    assert boxes[0].total_weight == 15


def test_exact_fit_is_accepted() -> None:
    assert summary(pack([cube(1, 150)], CATALOGUE)) == [("A", [1])]


def test_item_is_rotated_to_fit() -> None:
    lying_down = Package(id=1, width=200, height=100, length=100, weight=1)

    (box,) = pack([lying_down], CATALOGUE)

    assert box.box_type.name == "B"
    assert (box.placements[0].dx, box.placements[0].dy, box.placements[0].dz) == (100, 200, 100)


def test_long_item_only_fits_largest_box() -> None:
    rod = Package(id=1, width=10, height=10, length=250, weight=1)

    assert summary(pack([rod], CATALOGUE)) == [("C", [1])]


def test_volume_alone_does_not_decide_fit() -> None:
    # Three 160-cubes are 34% of box C's volume, but only two physically fit.
    boxes = pack([cube(i, 160) for i in range(3)], CATALOGUE)

    assert len(boxes) == 2


def test_items_share_a_large_box_instead_of_two_small_ones() -> None:
    # Smallest-box-first would open an A per 120-cube; both fit together in C.
    assert summary(pack([cube(1, 120), cube(2, 120)], CATALOGUE)) == [("C", [1, 2])]


def test_downsizes_by_repacking_into_smaller_box() -> None:
    # Two 100-cubes need two A boxes, but fit stacked in a single B.
    assert summary(pack([cube(1, 100), cube(2, 100)], CATALOGUE)) == [("B", [1, 2])]


def test_weight_limit_prevents_downsizing() -> None:
    # Tiny but heavy: together they exceed A and B's 1000 limit.
    assert summary(pack([cube(1, 1, 600), cube(2, 1, 600)], CATALOGUE)) == [("C", [1, 2])]


def test_weight_limit_forces_extra_box() -> None:
    boxes = pack([cube(1, 1, 2000), cube(2, 1, 2000)], CATALOGUE)

    assert summary(boxes) == [("C", [1]), ("C", [2])]


def test_weight_exactly_at_limit_is_accepted() -> None:
    assert summary(pack([cube(1, 1, 3000)], CATALOGUE)) == [("C", [1])]


def test_float_rounding_does_not_reject_exact_fit() -> None:
    thin_box = BoxType(name="Thin", width=0.3, height=0.1, length=0.1, max_weight=1)

    boxes = pack([cube(i, 0.1, 0.1) for i in range(3)], [thin_box])

    assert summary(boxes) == [("Thin", [0, 1, 2])]


def test_opens_largest_box_that_fits_not_largest_overall() -> None:
    tube = BoxType(name="Tube", width=50, height=50, length=500, max_weight=100)
    catalogue = [*CATALOGUE, tube]
    rod = Package(id=1, width=40, height=40, length=450, weight=1)

    assert summary(pack([rod, cube(2, 10)], catalogue)) == [("Tube", [1, 2])]


@pytest.mark.xfail(
    strict=True,
    reason="Known limitation: free spaces are never merged. The first two slabs leave "
    "two side-by-side 160- and 140-wide gaps; the 300-wide slab fits neither alone.",
)
def test_known_limitation_three_slabs_that_exactly_fill_box_c() -> None:
    slabs = [
        Package(id=1, width=160, height=400, length=240, weight=1),
        Package(id=2, width=140, height=400, length=240, weight=1),
        Package(id=3, width=300, height=400, length=60, weight=1),
    ]

    assert len(pack(slabs, CATALOGUE)) == 1


def test_packing_is_deterministic() -> None:
    packages = [cube(i, 40 + i * 7, i) for i in range(20)]

    assert pack(packages, CATALOGUE) == pack(list(reversed(packages)), CATALOGUE)


@pytest.mark.parametrize(
    ("package", "reason"),
    [
        (cube(1, 500), UnpackableReason.TOO_LARGE),
        (cube(1, 1, 5000), UnpackableReason.TOO_HEAVY),
        (cube(1, 500, 5000), UnpackableReason.TOO_LARGE_AND_TOO_HEAVY),
    ],
)
def test_reports_why_a_package_cannot_be_packed(package: Package, reason: UnpackableReason) -> None:
    with pytest.raises(UnpackablePackagesError) as exc_info:
        pack([package], CATALOGUE)

    assert exc_info.value.packages == (UnpackablePackage(1, reason),)


def test_reports_package_whose_size_and_weight_fit_only_different_boxes() -> None:
    small_strong = BoxType(name="S", width=10, height=10, length=10, max_weight=1000)
    big_weak = BoxType(name="L", width=100, height=100, length=100, max_weight=5)

    with pytest.raises(UnpackablePackagesError) as exc_info:
        pack([cube(1, 50, 10)], [small_strong, big_weak])

    assert exc_info.value.packages == (
        UnpackablePackage(1, UnpackableReason.NO_BOX_FITS_SIZE_AND_WEIGHT),
    )


def test_reports_every_unpackable_package_in_input_order() -> None:
    packages = [cube(1, 10), cube(2, 1, 9999), cube(3, 20), cube(4, 999)]

    with pytest.raises(UnpackablePackagesError) as exc_info:
        pack(packages, CATALOGUE)

    assert [p.package_id for p in exc_info.value.packages] == [2, 4]
    assert "2, 4" in str(exc_info.value)
