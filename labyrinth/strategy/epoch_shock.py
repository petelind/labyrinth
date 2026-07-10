"""Pure epoch shock detection for strategy route caches."""

from __future__ import annotations


def detect_epoch_shock(
    epoch_turns_remaining: int | None,
    last_epoch_turns_remaining: int | None,
    known_map_size: int,
    had_known_map: bool,
) -> bool:
    """
    Detect labyrinth epoch rollover without oracle trap-type access.

    Shock when the epoch counter resets upward or known_map was wiped.

    :param epoch_turns_remaining: Current epoch turns left.
    :param last_epoch_turns_remaining: Previous turn's epoch turns left.
    :param known_map_size: Current known_map entry count.
    :param had_known_map: Whether known_map was non-empty last turn.
    :return: True if route cache should be invalidated and scout resumed.
    """
    if (
        last_epoch_turns_remaining is not None
        and epoch_turns_remaining is not None
        and epoch_turns_remaining > last_epoch_turns_remaining
    ):
        return True
    if had_known_map and known_map_size == 0:
        return True
    return False
