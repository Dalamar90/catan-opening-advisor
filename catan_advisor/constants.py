"""Part A of the knowledge base: verified facts about base-game Catan.

Nothing in this module is tunable. If a number is a rule of the game it lives
here; if it is an opinion of ours it lives in config.yaml. This separation is
what keeps weight calibration (M6) from accidentally breaking the rules.
"""

from __future__ import annotations

# --- Resources -------------------------------------------------------------

WOOD = "wood"
BRICK = "brick"
WHEAT = "wheat"
SHEEP = "sheep"
ORE = "ore"
DESERT = "desert"

RESOURCES: tuple[str, ...] = (WOOD, BRICK, WHEAT, SHEEP, ORE)
TERRAINS: tuple[str, ...] = RESOURCES + (DESERT,)

# Italian labels, used by the CLI and by the shorthand parser (KB is in Italian).
RESOURCE_LABEL_IT: dict[str, str] = {
    WOOD: "legno",
    BRICK: "mattone",
    WHEAT: "grano",
    SHEEP: "pecora",
    ORE: "minerale",
    DESERT: "deserto",
}

# --- Board composition (KB A.1) --------------------------------------------

TILE_COUNTS: dict[str, int] = {
    WOOD: 4,
    WHEAT: 4,
    SHEEP: 4,
    BRICK: 3,
    ORE: 3,
    DESERT: 1,
}
N_HEXES = 19
N_VERTICES = 54
N_EDGES = 72
N_PRODUCTIVE_HEXES = 18

# --- Number tokens (KB A.2) ------------------------------------------------

NUMBER_TOKENS: tuple[int, ...] = (2, 3, 3, 4, 4, 5, 5, 6, 6, 8, 8, 9, 9, 10, 10, 11, 11, 12)

PIPS: dict[int, int] = {2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 7: 6, 8: 5, 9: 4, 10: 3, 11: 2, 12: 1}

TOTAL_PIPS = 58          # sum of PIPS over NUMBER_TOKENS
ROLL_OUTCOMES = 36       # combinations of 2d6
PROBA_POINT = 1 / 36     # value of one pip, KB E.1

HIGH_NUMBERS: frozenset[int] = frozenset({6, 8})
MID_BAND: frozenset[int] = frozenset({4, 5, 6, 8, 9, 10})
EXTREME_NUMBERS: frozenset[int] = frozenset({2, 3, 11, 12})

# --- Expected share of board pips per resource (KB B.2) --------------------
# Derived from tile counts, not from pips: 4/18 and 3/18.

EXPECTED_QUOTA: dict[str, float] = {
    WOOD: 4 / 18,
    WHEAT: 4 / 18,
    SHEEP: 4 / 18,
    BRICK: 3 / 18,
    ORE: 3 / 18,
}

# --- Building costs (KB A.3) -----------------------------------------------

COSTS: dict[str, dict[str, int]] = {
    "road": {WOOD: 1, BRICK: 1},
    "settlement": {WOOD: 1, BRICK: 1, WHEAT: 1, SHEEP: 1},
    "city": {WHEAT: 2, ORE: 3},
    "development_card": {WHEAT: 1, SHEEP: 1, ORE: 1},
}

# --- Ports (KB A.4) --------------------------------------------------------

N_PORTS_GENERIC = 4      # 3:1
N_PORTS_SPECIFIC = 5     # 2:1, one per resource

# --- Draft order (KB A.5) --------------------------------------------------


def pick_numbers(position: int, n_players: int) -> tuple[int, int]:
    """1-based pick numbers of `position` in a snake draft."""
    if not 1 <= position <= n_players:
        raise ValueError(f"position {position} out of range for {n_players} players")
    return position, 2 * n_players - position + 1


def waiting_picks(position: int, n_players: int) -> int:
    """Opponent picks between my first and my second placement (KB A.5, 'k')."""
    first, second = pick_numbers(position, n_players)
    return second - first - 1


def expected_cards_per_roll(pips: int) -> float:
    return pips * PROBA_POINT


def expected_cards_per_round(pips: int, n_players: int) -> float:
    return expected_cards_per_roll(pips) * n_players
