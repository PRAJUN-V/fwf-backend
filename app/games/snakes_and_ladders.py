"""Pure game logic for Snake & Ladder.

The board is the classic 100 squares. A player starts at position 0 (off board)
and must land exactly on 100 to win; an overshoot keeps the player in place.
"""

import secrets

BOARD_SIZE = 100

# Mapping of square -> destination square.
LADDERS: dict[int, int] = {
    1: 38,
    4: 14,
    9: 31,
    21: 42,
    28: 84,
    36: 44,
    51: 67,
    71: 91,
    80: 100,
}

SNAKES: dict[int, int] = {
    16: 6,
    47: 26,
    49: 11,
    56: 53,
    62: 19,
    64: 60,
    87: 24,
    93: 73,
    95: 75,
    98: 78,
}

JUMPS: dict[int, int] = {**LADDERS, **SNAKES}

# Seven colors so we can support 2-4 players comfortably.
PLAYER_COLORS = ["red", "blue", "green", "yellow"]


def roll_die() -> int:
    """Return a cryptographically-random die roll in [1, 6]."""
    return secrets.randbelow(6) + 1


def resolve_move(position: int, dice: int) -> tuple[int, int | None]:
    """Apply a dice roll to a position.

    Returns (new_position, jumped_from). ``jumped_from`` is the landing square
    before a snake/ladder applied, or ``None`` when no jump happened.
    """
    target = position + dice
    if target > BOARD_SIZE:
        # Overshoot: stay in place (must land exactly on 100).
        return position, None
    if target in JUMPS:
        return JUMPS[target], target
    return target, None


def is_winning_position(position: int) -> bool:
    return position == BOARD_SIZE
