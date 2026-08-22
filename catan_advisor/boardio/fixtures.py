"""Board generation: the standard port frame and legal random boards.

The port *positions* are a property of the physical frame and are stable across
editions: 9 ports spread over the 30 coastal edges with gaps of 2, 2, 3 repeated
three times. The port *types* in DEFAULT_PORT_TYPES are the usual arrangement but
are marked UNVERIFIED -- check them against your own box, or just let the photo
step read them off the real board.
"""

from __future__ import annotations

import random

from .. import constants as K
from ..board import Board, Hex, Port
from ..geometry import GEOMETRY, Geometry

# Offsets into Geometry.coastal_edges (clockwise from due north).
PORT_EDGE_OFFSETS: tuple[int, ...] = (0, 3, 6, 10, 13, 16, 20, 23, 26)

# UNVERIFIED: clockwise from due north. Override from the board input.
DEFAULT_PORT_TYPES: tuple[tuple[int, str | None], ...] = (
    (3, None),
    (2, K.SHEEP),
    (3, None),
    (2, K.WOOD),
    (2, K.BRICK),
    (3, None),
    (2, K.WHEAT),
    (2, K.ORE),
    (3, None),
)


def standard_port_frame(
    port_types: tuple[tuple[int, str | None], ...] = DEFAULT_PORT_TYPES,
    geometry: Geometry = GEOMETRY,
) -> tuple[Port, ...]:
    if len(port_types) != len(PORT_EDGE_OFFSETS):
        raise ValueError(f"servono {len(PORT_EDGE_OFFSETS)} porti, ricevuti {len(port_types)}")
    coast = geometry.coastal_edges
    return tuple(
        Port(edge_id=coast[offset], ratio=ratio, resource=resource)
        for offset, (ratio, resource) in zip(PORT_EDGE_OFFSETS, port_types)
    )


def _terrain_bag() -> list[str]:
    bag: list[str] = []
    for resource, count in K.TILE_COUNTS.items():
        bag.extend([resource] * count)
    return bag


def random_board(
    seed: int | None = None,
    balanced: bool = True,
    geometry: Geometry = GEOMETRY,
    ports: tuple[Port, ...] | None = None,
    n_players: int = 4,
    my_position: int = 1,
) -> Board:
    """A legal random board. With balanced=True, no two 6/8 tiles touch.

    Not the official beginner layout -- just a valid board, which is all the
    tests and the simulations need.
    """
    rng = random.Random(seed)
    adjacency = _hex_adjacency(geometry)

    for _ in range(2000):
        terrains = _terrain_bag()
        rng.shuffle(terrains)
        tokens = list(K.NUMBER_TOKENS)
        rng.shuffle(tokens)

        hexes: dict[str, Hex] = {}
        token_iter = iter(tokens)
        for hid, terrain in zip(geometry.hex_ids, terrains):
            number = None if terrain == K.DESERT else next(token_iter)
            hexes[hid] = Hex(id=hid, resource=terrain, number=number)

        if balanced and _has_adjacent_high_numbers(hexes, adjacency):
            continue

        board = Board(
            hexes=hexes,
            ports=ports if ports is not None else standard_port_frame(geometry=geometry),
            n_players=n_players,
            my_position=my_position,
            geometry=geometry,
        )
        board.validate(strict=True)
        return board

    raise RuntimeError("nessun tabellone bilanciato trovato in 2000 tentativi")


def _hex_adjacency(geometry: Geometry) -> dict[str, tuple[str, ...]]:
    out: dict[str, set[str]] = {h: set() for h in geometry.hex_ids}
    for hs in geometry.edge_hexes.values():
        if len(hs) == 2:
            out[hs[0]].add(hs[1])
            out[hs[1]].add(hs[0])
    return {h: tuple(sorted(n)) for h, n in out.items()}


def _has_adjacent_high_numbers(
    hexes: dict[str, Hex], adjacency: dict[str, tuple[str, ...]]
) -> bool:
    for hid, neighbours in adjacency.items():
        if hexes[hid].number in K.HIGH_NUMBERS:
            if any(hexes[n].number in K.HIGH_NUMBERS for n in neighbours):
                return True
    return False
