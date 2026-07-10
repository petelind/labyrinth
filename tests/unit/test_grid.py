"""Tests for labyrinth grid perimeter and path validation."""

from __future__ import annotations

import random

import pytest

from labyrinth.domain.grid import (
    is_cardinally_adjacent,
    is_perimeter_square,
    random_perimeter_start,
    validate_prescribed_path,
)
from labyrinth.domain.types import LABYRINTH_SIZE


class TestIsPerimeterSquare:
    def test_corners_are_perimeter(self) -> None:
        assert is_perimeter_square(0, 0) is True
        assert is_perimeter_square(99, 0) is True
        assert is_perimeter_square(0, 99) is True
        assert is_perimeter_square(99, 99) is True

    def test_interior_not_perimeter(self) -> None:
        assert is_perimeter_square(50, 50) is False
        assert is_perimeter_square(1, 1) is False
        assert is_perimeter_square(49, 49) is False

    def test_oob_not_perimeter(self) -> None:
        assert is_perimeter_square(-1, 0) is False
        assert is_perimeter_square(0, 100) is False


class TestRandomPerimeterStart:
    def test_random_perimeter_start_always_on_edge(self) -> None:
        rng = random.Random(42)
        for _ in range(100):
            x, y = random_perimeter_start(rng)
            assert is_perimeter_square(x, y)


class TestValidatePrescribedPath:
    def test_validate_path_accepts_straight_line_from_left_edge(self) -> None:
        path = [(0, 49), (1, 49), (2, 49)]
        result = validate_prescribed_path(path)
        assert result == [(0, 49), (1, 49), (2, 49)]

    def test_validate_path_rejects_diagonal_step(self) -> None:
        path = [(0, 0), (1, 1)]
        assert validate_prescribed_path(path) is None

    def test_validate_path_rejects_oob_coordinate(self) -> None:
        path = [(0, 0), (100, 0)]
        assert validate_prescribed_path(path) is None

    def test_validate_path_rejects_interior_start(self) -> None:
        path = [(50, 50), (51, 50)]
        assert validate_prescribed_path(path) is None

    def test_validate_path_rejects_empty(self) -> None:
        assert validate_prescribed_path([]) is None


class TestIsCardinallyAdjacent:
    def test_adjacent_horizontal(self) -> None:
        assert is_cardinally_adjacent((0, 0), (1, 0)) is True

    def test_not_adjacent_diagonal(self) -> None:
        assert is_cardinally_adjacent((0, 0), (1, 1)) is False
