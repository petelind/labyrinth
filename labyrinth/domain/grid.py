"""Pure grid geometry helpers for labyrinth movement."""

from __future__ import annotations

import random
from collections.abc import Sequence

from labyrinth.domain.types import LABYRINTH_SIZE


def is_perimeter_square(
    x: int,
    y: int,
    *,
    size: int = LABYRINTH_SIZE,
) -> bool:
    """
    Return True when (x, y) lies on the outer edge of a square grid.

    :param x: Column index.
    :param y: Row index.
    :param size: Grid side length.
    :return: True if the coordinate is on the perimeter and in bounds.
    """
    max_index = size - 1
    if not (0 <= x <= max_index and 0 <= y <= max_index):
        return False
    return x == 0 or x == max_index or y == 0 or y == max_index


def is_cardinally_adjacent(a: tuple[int, int], b: tuple[int, int]) -> bool:
    """
    Return True when two squares share an edge (Manhattan distance 1).

    :param a: First coordinate.
    :param b: Second coordinate.
    :return: True if the squares are cardinally adjacent.
    """
    ax, ay = a
    bx, by = b
    return abs(ax - bx) + abs(ay - by) == 1


def _build_perimeter_squares(size: int = LABYRINTH_SIZE) -> tuple[tuple[int, int], ...]:
    """Return all perimeter coordinates for a square grid."""
    max_index = size - 1
    squares: list[tuple[int, int]] = []
    for x in range(size):
        for y in range(size):
            if is_perimeter_square(x, y, size=size):
                squares.append((x, y))
    return tuple(squares)


_PERIMETER_SQUARES: tuple[tuple[int, int], ...] = _build_perimeter_squares()


def random_perimeter_start(
    rng: random.Random,
    *,
    size: int = LABYRINTH_SIZE,
) -> tuple[int, int]:
    """
    Pick a uniform random perimeter square as a trip entry point.

    :param rng: Injectable RNG.
    :param size: Grid side length.
    :return: A coordinate on the labyrinth perimeter.
    """
    if size != LABYRINTH_SIZE:
        perimeter = _build_perimeter_squares(size)
    else:
        perimeter = _PERIMETER_SQUARES
    return rng.choice(perimeter)


def validate_prescribed_path(
    path: Sequence[tuple[int, int]],
    *,
    size: int = LABYRINTH_SIZE,
) -> list[tuple[int, int]] | None:
    """
    Validate a strategy-prescribed path for labyrinth entry and movement.

    Checks: non-empty; in bounds; starts on perimeter; each step cardinally adjacent.

    :param path: Ordered list of grid coordinates.
    :param size: Grid side length.
    :return: Normalized path copy, or None if validation fails.
    """
    if not path:
        return None

    max_index = size - 1
    normalized: list[tuple[int, int]] = []

    for i, (x, y) in enumerate(path):
        if not (0 <= x <= max_index and 0 <= y <= max_index):
            return None
        if i == 0 and not is_perimeter_square(x, y, size=size):
            return None
        if i > 0 and not is_cardinally_adjacent(normalized[i - 1], (x, y)):
            return None
        normalized.append((x, y))

    return normalized
