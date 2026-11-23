import pytest

from box_packer.geometry import TOLERANCE, Space, fits_in, orientations, split
from box_packer.models import Dimensions


@pytest.mark.parametrize(
    ("dims", "expected_count"),
    [((1, 1, 1), 1), ((1, 1, 2), 3), ((1, 2, 3), 6)],
)
def test_orientations_are_distinct_rotations(dims: Dimensions, expected_count: int) -> None:
    result = orientations(dims)

    assert len(result) == expected_count
    assert all(sorted(o) == sorted(dims) for o in result)


@pytest.mark.parametrize(
    ("item", "container", "expected"),
    [
        ((10, 10, 10), (150, 150, 150), True),
        ((150, 150, 150), (150, 150, 150), True),
        ((150.000001, 1, 1), (150, 150, 150), False),
        ((200, 100, 100), (100, 200, 100), True),
        ((10, 10, 250), (150, 150, 150), False),
        ((10, 10, 250), (300, 400, 300), True),
        ((0.30000000000000004, 1, 1), (0.3, 1, 1), True),
    ],
    ids=["small", "exact", "just-over", "needs-rotation", "too-long", "long-in-c", "float-noise"],
)
def test_fits_in(item: Dimensions, container: Dimensions, expected: bool) -> None:
    assert fits_in(item, container) is expected


def test_space_can_hold_respects_orientation() -> None:
    space = Space(0, 0, 0, 100, 200, 100)

    assert space.can_hold((100, 200, 100))
    assert not space.can_hold((200, 100, 100))


def test_split_tiles_the_space_exactly() -> None:
    space = Space(5, 6, 7, 100, 200, 300)
    item = (10, 20, 30)

    beside, above, in_front = split(space, item)

    assert beside == Space(15, 6, 7, 90, 200, 300)
    assert above == Space(5, 26, 7, 10, 180, 300)
    assert in_front == Space(5, 6, 37, 10, 20, 270)
    item_volume = 10 * 20 * 30
    assert beside.volume + above.volume + in_front.volume + item_volume == space.volume


def test_split_drops_empty_and_sliver_spaces() -> None:
    space = Space(0, 0, 0, 100, 100, 100)
    almost_full_width = 100 - TOLERANCE / 2

    assert split(space, (100, 100, 100)) == []
    assert split(space, (almost_full_width, 100, 50)) == [
        Space(0, 0, 50, almost_full_width, 100, 50),
    ]
