"""Pure route resolution for labyrinth trips."""

from __future__ import annotations

from labyrinth.domain.criteria import matches_all_criteria
from labyrinth.domain.entities import Raksha, Route
from labyrinth.logging_config import get_logger

log = get_logger(__name__)


def resolve_route_for_raksha(
    raksha: Raksha,
    routes: list[Route],
) -> list[tuple[int, int]] | None:
    """
    Return the path from the first route whose criteria match the Raksha.

    :param raksha: Raksha about to enter the labyrinth.
    :param routes: Ordered list of criteria-mapped routes.
    :return: Mutable path copy, or None if no route matches.
    """
    if not raksha.alive or not routes:
        return None

    for index, route in enumerate(routes):
        if matches_all_criteria(raksha, route.criteria):
            log.debug(
                "trip.route_resolved",
                raksha_id=str(raksha.id),
                matched=True,
                route_index=index,
                path_len=len(route.path),
            )
            return list(route.path)

    log.debug(
        "trip.route_resolved",
        raksha_id=str(raksha.id),
        matched=False,
        route_index=-1,
    )
    return None
