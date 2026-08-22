"""Opponent profiling and the trade market, KB C.3.

This is the part Catanatron does not model at all (KB E.7), and it is where the
advisor earns its keep: the value of a resource is not how many pips of it sit
on the board, it is how many pips of it sit on the board *that other people do
not already have*. A resource nobody else produces is a monopoly for the whole
game; one everybody produces is worth nothing at the trading table.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .. import constants as K
from ..board import Board, Port
from ..config import Config
from .breakdown import Breakdown

_RES = K.RESOURCE_LABEL_IT


@dataclass
class OpponentProfile:
    player: int
    vertices: tuple[str, ...]
    production: dict[str, int]
    numbers: tuple[int, ...]
    tiles: frozenset[str]
    ports: tuple[Port, ...]

    @property
    def pips(self) -> int:
        return sum(self.production.values())

    @property
    def covered(self) -> tuple[str, ...]:
        return tuple(r for r in K.RESOURCES if self.production.get(r, 0) > 0)

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(r for r in K.RESOURCES if self.production.get(r, 0) == 0)

    def archetype(self) -> str:
        """A rough read of where this opponent is heading, KB C.4."""
        p = self.production
        if p.get(K.ORE, 0) >= 5 and p.get(K.WHEAT, 0) >= 5:
            return "citta/carte"
        if p.get(K.WOOD, 0) >= 5 and p.get(K.BRICK, 0) >= 5:
            return "espansione"
        if any(port.ratio == 2 for port in self.ports):
            return "porto"
        if len(self.covered) >= 4:
            return "bilanciato"
        return "in costruzione"

    def summary(self) -> str:
        prod = " ".join(
            f"{_RES[r][:3]}{self.production.get(r, 0)}" for r in K.RESOURCES
        )
        where = "+".join(self.vertices)
        return (
            f"P{self.player} [{where}] {self.pips} pip  {prod}  "
            f"-> {self.archetype()}"
        )


def profile_opponents(board: Board, me: int | None = None) -> list[OpponentProfile]:
    """One profile per opponent who has already placed something."""
    me = board.my_position if me is None else me
    by_player: dict[int, list[str]] = {}
    for placement in board.placements:
        if placement.player == me:
            continue
        by_player.setdefault(placement.player, []).append(placement.vertex)

    profiles = []
    for player, vertices in sorted(by_player.items()):
        production: dict[str, int] = {r: 0 for r in K.RESOURCES}
        numbers: list[int] = []
        tiles: set[str] = set()
        ports = []
        for vertex in vertices:
            for resource, pips in board.vertex_production(vertex).items():
                production[resource] += pips
            numbers.extend(board.vertex_numbers(vertex))
            tiles.update(board.geometry.vertex_hexes[vertex])
            port = board.vertex_port(vertex)
            if port:
                ports.append(port)
        profiles.append(
            OpponentProfile(
                player=player,
                vertices=tuple(vertices),
                production=production,
                numbers=tuple(sorted(numbers)),
                tiles=frozenset(tiles),
                ports=tuple(ports),
            )
        )
    return profiles


def my_placements(board: Board, me: int | None = None) -> tuple[str, ...]:
    me = board.my_position if me is None else me
    return tuple(p.vertex for p in board.placements if p.player == me)


@dataclass
class MarketView:
    """How each resource trades, given who produces what."""

    monopolies: tuple[str, ...] = ()
    saturated: tuple[str, ...] = ()
    leader: int | None = None
    neglected_numbers: tuple[int, ...] = ()
    profiles: list[OpponentProfile] = field(default_factory=list)


def read_market(
    production: dict[str, int],
    numbers: tuple[int, ...],
    profiles: list[OpponentProfile],
) -> MarketView:
    if not profiles:
        return MarketView()

    monopolies = tuple(
        r
        for r in K.RESOURCES
        if production.get(r, 0) >= 3
        and all(p.production.get(r, 0) == 0 for p in profiles)
    )
    saturated = tuple(
        r
        for r in K.RESOURCES
        if production.get(r, 0) > 0
        and all(p.production.get(r, 0) > 0 for p in profiles)
    )
    opponent_numbers = {n for p in profiles for n in p.numbers}
    neglected = tuple(sorted({n for n in numbers if n not in opponent_numbers}))
    leader = max(profiles, key=lambda p: p.pips).player if profiles else None
    return MarketView(
        monopolies=monopolies,
        saturated=saturated,
        leader=leader,
        neglected_numbers=neglected,
        profiles=profiles,
    )


def add_market_terms(
    cfg: Config,
    board: Board,
    production: dict[str, int],
    numbers: tuple[int, ...],
    tiles: set[str],
    profiles: list[OpponentProfile],
    bd: Breakdown,
) -> MarketView:
    """KB C.3. No opponents placed yet means no market to read: stay silent
    rather than invent one."""
    view = read_market(production, numbers, profiles)
    if not profiles:
        return view

    for resource in view.monopolies:
        bd.add(
            "monopoly",
            f"{_RES[resource]}: {production[resource]} pip e nessun avversario lo produce, "
            "potere di mercato per tutta la partita",
            float(cfg.get("market.monopoly_bonus", 1.5)),
            ref="C.3",
        )
    for resource in view.saturated:
        bd.add(
            "saturated",
            f"{_RES[resource]}: lo producono tutti, valore di scambio quasi nullo",
            float(cfg.get("market.saturated_penalty", -1.0)),
            ref="C.3",
        )
    if view.neglected_numbers:
        bd.add(
            "neglected_numbers",
            f"numeri trascurati dal tavolo ({', '.join(map(str, view.neglected_numbers))}): "
            "il ladro passera altrove",
            float(cfg.get("market.neglected_numbers_bonus", 0.5)),
            ref="C.3",
        )

    if view.leader is not None:
        leader = next(p for p in profiles if p.player == view.leader)
        shared = tiles & leader.tiles
        if shared:
            bd.add(
                "shared_with_leader",
                f"{len(shared)} tessere condivise con P{leader.player}, "
                f"il piu forte finora ({leader.pips} pip)",
                len(shared) * float(cfg.get("market.shared_tile_penalty", -0.3)),
                ref="C.3",
            )
    return view
