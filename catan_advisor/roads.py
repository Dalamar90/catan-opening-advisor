"""Choosing the initial road (KB C.4 and B.3, anti-pattern 8 of D.5).

The initial road is not transport, it is a reservation. It runs to an adjacent
junction -- which the distance rule makes unbuildable forever -- and from there
one more road reaches the first junction you can actually settle. So a road is
worth what its best reachable target is worth *to this portfolio*, discounted by
the chance that target is still free when you get to build.

That last clause is why the road choice belongs after the draft simulation: a
road pointing at the best junction on the board is worthless if three opponents
will pass before you can use it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import constants as K
from .board import Board
from .config import Config, load_config
from .scoring.breakdown import Breakdown

_RES = K.RESOURCE_LABEL_IT


@dataclass
class RoadTarget:
    vertex: str
    distance: int
    pips: int
    marginal: float          # what it would add to this portfolio
    survival: float          # chance it is still free when we can build


@dataclass
class RoadOption:
    edge: str
    towards: str
    targets: list[RoadTarget] = field(default_factory=list)
    breakdown: Breakdown = field(default_factory=lambda: Breakdown("road"))
    warnings: list[str] = field(default_factory=list)

    @property
    def value(self) -> float:
        return self.breakdown.total

    @property
    def best(self) -> RoadTarget | None:
        return self.targets[0] if self.targets else None

    def headline(self, board: Board) -> str:
        if not self.best:
            return f"{self.edge} verso {self.towards}: nessuno sbocco utile"
        t = self.best
        return (
            f"{self.edge} verso {self.towards}  valore {self.value:5.2f}  "
            f"prenota {t.vertex} ({t.pips} pip, {t.survival:.0%} di sopravvivenza) "
            f"[{board.vertex_label(t.vertex)}]"
        )


def _coverage_credit(cfg: Config, pips: int) -> float:
    table = {int(k): float(v) for k, v in cfg.require("pair.coverage.credit_by_pips").items()}
    if pips >= int(cfg.get("pair.coverage.full_credit_from_pips", 4)):
        return max(table.values())
    return table.get(pips, 0.0)


def marginal_value(
    cfg: Config,
    board: Board,
    target: str,
    production: dict[str, int],
    weights: dict[str, float],
) -> tuple[float, str]:
    """What settling `target` would add to a portfolio that already produces
    `production`: its weighted pips plus whatever coverage it unlocks."""
    target_production = board.vertex_production(target)
    pips_value = sum(p * weights[r] for r, p in target_production.items())

    per_resource = float(cfg.get("meta.variety_pip_equivalent", 4.0))
    gain = 0.0
    filled = []
    for resource, pips in target_production.items():
        before = _coverage_credit(cfg, production.get(resource, 0))
        after = _coverage_credit(cfg, production.get(resource, 0) + pips)
        if after > before:
            gain += (after - before) * per_resource
            if production.get(resource, 0) == 0:
                filled.append(_RES[resource])

    note = f", copre {' e '.join(filled)}" if filled else ""
    return pips_value + gain, note


def score_road(
    board: Board,
    settlement: str,
    edge: str,
    production: dict[str, int],
    config: Config | None = None,
    weights: dict[str, float] | None = None,
    survival: dict[str, float] | None = None,
) -> RoadOption:
    cfg = config or load_config()
    w = weights if weights is not None else cfg.resource_weights(
        board.pips_by_resource, board.n_players
    )
    geo = board.geometry
    a, b = geo.edge_vertices[edge]
    if settlement not in (a, b):
        raise ValueError(f"il lato {edge} non parte da {settlement}")
    towards = b if a == settlement else a

    option = RoadOption(edge=edge, towards=towards)
    two_step_weight = float(cfg.get("roads.two_step_weight", 0.33))
    use_survival = bool(cfg.get("roads.survival_discount", True))

    def chance(vertex: str) -> float:
        if survival is None or not use_survival:
            return 1.0
        return survival.get(vertex, 1.0)

    # Distance 2 from the settlement, reached through `towards`.
    near = [v for v in geo.vertex_neighbours[towards] if v != settlement and board.is_legal(v)]
    # Distance 3, reached through one of those.
    far = {
        u
        for v in near
        for u in geo.vertex_neighbours[v]
        if u not in (settlement, towards) and u not in near and board.is_legal(u)
    }

    for vertex in near:
        value, note = marginal_value(cfg, board, vertex, production, w)
        option.targets.append(
            RoadTarget(vertex, 2, board.vertex_pips(vertex), value, chance(vertex))
        )
    for vertex in sorted(far):
        value, note = marginal_value(cfg, board, vertex, production, w)
        option.targets.append(
            RoadTarget(vertex, 3, board.vertex_pips(vertex), value * two_step_weight, chance(vertex))
        )

    option.targets.sort(key=lambda t: -(t.marginal * t.survival))

    best_near = next((t for t in option.targets if t.distance == 2), None)
    if best_near:
        value, note = marginal_value(cfg, board, best_near.vertex, production, w)
        option.breakdown.add(
            "reservation",
            f"prenota {best_near.vertex} ({best_near.pips} pip{note}), "
            f"sopravvivenza {best_near.survival:.0%}",
            value * best_near.survival,
            ref="C.4",
        )
    best_far = next((t for t in option.targets if t.distance == 3), None)
    if best_far:
        option.breakdown.add(
            "second_ring",
            f"apre anche {best_far.vertex} ({best_far.pips} pip) a 3 strade",
            best_far.marginal * best_far.survival,
            ref="B.3",
        )

    option.warnings = _road_warnings(board, settlement, option, near)
    return option


def _road_warnings(
    board: Board, settlement: str, option: RoadOption, near: list[str]
) -> list[str]:
    out = []
    if not near:
        out.append(
            f"D.5.8 strada sprecata: da {option.towards} non parte nessun incrocio "
            "edificabile, o sono tutti gia invalidati dalla distance rule"
        )
    else:
        best = max(board.vertex_pips(v) for v in near)
        if best <= 4:
            out.append(
                f"D.5.8 sbocco debole: il miglior incrocio prenotabile da qui fa {best} pip"
            )
    towards_tiles = board.geometry.vertex_hexes[option.towards]
    if all(board.hexes[t].is_desert for t in towards_tiles):
        out.append("D.5.8 la strada punta verso il deserto")
    return out


def best_roads(
    board: Board,
    settlement: str,
    production: dict[str, int],
    config: Config | None = None,
    survival: dict[str, float] | None = None,
) -> list[RoadOption]:
    """Every legal initial road from `settlement`, best first."""
    cfg = config or load_config()
    w = cfg.resource_weights(board.pips_by_resource, board.n_players)
    options = [
        score_road(board, settlement, edge, production, cfg, w, survival)
        for edge in board.geometry.vertex_edges[settlement]
    ]
    options.sort(key=lambda o: -o.value)
    return options
