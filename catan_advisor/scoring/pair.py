"""S(A,B): the pair of opening settlements, KB B.4 -- the real output.

Two settlements are not scored, a portfolio is. Everything that belongs to the
portfolio rather than to a junction is computed exactly once here: resource
variety, ports, expansion room, robber exposure, number spread. The member
junctions contribute only their production and the quality of their numbers.

The single biggest correction to the KB v1 lives here: KB E.2 found that
Catanatron prices each distinct resource at 4 production points, so a 5/5 pair
at 19 pips beats a 3/5 pair at 23. We keep that, with one change: the credit for
covering a resource ramps with how much of it you actually produce, because a
resource "covered" by a lone 12 is not covered in any useful sense.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations

from .. import constants as K
from ..board import Board, Placement, Port
from ..config import Config, load_config
from .breakdown import Breakdown
from .ports import score_port
from .vertex import ExpansionTarget, VertexScore, score_vertex

_RES = K.RESOURCE_LABEL_IT


@dataclass
class PairScore:
    a: str
    b: str
    board: Board = field(repr=False)
    members: tuple[VertexScore, VertexScore] = field(repr=False)
    production: dict[str, int] = field(default_factory=dict)
    numbers: tuple[int, ...] = ()
    distinct_tiles: int = 0
    ports: tuple[Port, ...] = ()
    breakdown: Breakdown = field(default_factory=lambda: Breakdown("pair"))
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    expansion_targets: list[ExpansionTarget] = field(default_factory=list)

    @property
    def score(self) -> float:
        return self.breakdown.total

    @property
    def pips(self) -> int:
        return sum(self.production.values())

    @property
    def resources_covered(self) -> int:
        return sum(1 for p in self.production.values() if p > 0)

    @property
    def cards_per_roll(self) -> float:
        return K.expected_cards_per_roll(self.pips)

    @property
    def cards_per_round(self) -> float:
        return K.expected_cards_per_round(self.pips, self.board.n_players)

    def verdict(self) -> str:
        """KB B.4 benchmark, on raw pips."""
        pips = self.pips
        if pips >= 22:
            return "apertura da vincitore"
        if pips >= 20:
            return "molto forte"
        if pips >= 18:
            return "solida"
        if pips >= 16:
            return "sotto media, serve un piano"
        return "apertura persa: punta su scambi e strada piu lunga"

    def headline(self) -> str:
        flag = "  [!]" if self.violations else ""
        covered = f"{self.resources_covered}/5"
        return (
            f"{self.a} + {self.b}  S={self.score:6.2f}  pip {self.pips:>2}  "
            f"{covered} risorse  {self.cards_per_round:.2f} carte/giro{flag}"
        )


def score_pair(
    board: Board,
    a: str,
    b: str,
    config: Config | None = None,
    weights: dict[str, float] | None = None,
    members: dict[str, VertexScore] | None = None,
) -> PairScore:
    cfg = config or load_config()
    w = weights if weights is not None else cfg.resource_weights(
        board.pips_by_resource, board.n_players
    )
    sa = (members or {}).get(a) or score_vertex(board, a, cfg, w, standalone=False)
    sb = (members or {}).get(b) or score_vertex(board, b, cfg, w, standalone=False)

    production: dict[str, int] = {r: 0 for r in K.RESOURCES}
    for source in (sa.production, sb.production):
        for resource, pips in source.items():
            production[resource] += pips

    tiles = set(board.geometry.vertex_hexes[a]) | set(board.geometry.vertex_hexes[b])
    productive_tiles = {t for t in tiles if not board.hexes[t].is_desert}
    numbers = tuple(sorted(sa.numbers + sb.numbers))
    ports = tuple(
        p for p in (board.vertex_port(a), board.vertex_port(b)) if p is not None
    )

    bd = Breakdown(subject=f"{a}+{b}")
    bd.merge(sa.breakdown, prefix=f"{a}.")
    bd.merge(sb.breakdown, prefix=f"{b}.")

    pair = PairScore(
        a=a,
        b=b,
        board=board,
        members=(sa, sb),
        production=production,
        numbers=numbers,
        distinct_tiles=len(productive_tiles),
        ports=ports,
        breakdown=bd,
    )

    _add_coverage(cfg, board, pair, bd)
    _add_engines(cfg, production, bd)
    _add_number_spread(cfg, numbers, bd)
    _add_distinct_tiles(cfg, pair, bd)
    for port in ports:
        score_port(cfg, port, production, portfolio_known=True, breakdown=bd)
    pair.expansion_targets = _add_expansion(board, a, b, cfg, bd)
    _add_high_number_concentration(cfg, board, a, b, production, bd)
    _add_hard_constraints(cfg, pair, bd)
    pair.warnings = _anti_patterns(cfg, board, pair)
    return pair


# --- terms ------------------------------------------------------------------


def _coverage_credit(cfg: Config, pips: int) -> float:
    table = {int(k): float(v) for k, v in cfg.require("pair.coverage.credit_by_pips").items()}
    full_from = int(cfg.get("pair.coverage.full_credit_from_pips", 4))
    if pips >= full_from:
        return max(table.values())
    return table.get(pips, 0.0)


def _add_coverage(cfg: Config, board: Board, pair: PairScore, bd: Breakdown) -> None:
    """KB B.4 with E.2 magnitudes, made continuous.

    Each fully covered resource is worth `variety_pip_equivalent` pips, counted
    against a 3-of-5 baseline. A resource sitting on a single 12 earns a
    fraction of that, not the whole thing.
    """
    per_resource = float(cfg.get("meta.variety_pip_equivalent", 4.0))
    baseline = float(cfg.get("pair.coverage.baseline_resources", 3))
    redundant_credit = float(cfg.get("pair.coverage.redundant_port_credit", 0.5))

    credits = {r: _coverage_credit(cfg, p) for r, p in pair.production.items()}
    total_credit = sum(credits.values())

    # A 2:1 port on a resource we produce in surplus partly compensates a gap:
    # KB B.4 prices 4/5 + such a port between 4/5 and 5/5.
    port_note = ""
    missing = [r for r, p in pair.production.items() if p == 0]
    if len(missing) == 1:
        surplus = [r for r, p in pair.production.items() if p >= 5]
        for port in pair.ports:
            if port.resource and port.resource in surplus:
                total_credit += redundant_credit
                port_note = f", + {port} sulla ridondante"
                break

    value = (total_credit - baseline) * per_resource
    if board.n_players == 3:
        multiplier = float(cfg.get("pair.coverage.bonus_3p_multiplier", 1.125))
        value *= multiplier
        port_note += " (x1.125 a 3 giocatori: il mercato e piu rigido)"

    detail = ", ".join(
        f"{_RES[r]} {pair.production[r]}pip={credits[r]:.2f}"
        for r in K.RESOURCES
        if credits[r] > 0
    )
    label = (
        f"copertura {total_credit:.2f}/5 risorse contro una base di {baseline:.0f} "
        f"({detail}{port_note})"
    )
    bd.add("coverage", label, value, ref="B.4/E.2")

    if missing:
        bd.note(
            "coverage_missing",
            f"non produci: {', '.join(_RES[r] for r in missing)}",
            ref="B.4",
        )


def _add_engines(cfg: Config, production: dict[str, int], bd: Breakdown) -> None:
    wood, brick = production[K.WOOD], production[K.BRICK]
    if wood and brick:
        ratio = max(wood, brick) / min(wood, brick)
        if ratio <= 1.5:
            bd.add(
                "wood_brick_balance",
                f"legno {wood} e mattone {brick} bilanciati ({ratio:.2f}:1): motore strade",
                float(cfg.get("pair.wood_brick_balance_bonus", 1.0)),
                ref="B.4",
            )

    if production[K.WHEAT] >= 6:
        bd.add(
            "wheat_engine",
            f"grano {production[K.WHEAT]} pip: la risorsa piu universale e coperta bene",
            float(cfg.get("pair.wheat_engine_bonus", 1.0)),
            ref="B.4",
        )

    if production[K.ORE] >= 5 and production[K.WHEAT] >= 5:
        bd.add(
            "city_engine",
            f"minerale {production[K.ORE]} e grano {production[K.WHEAT]}: motore citta attivo",
            float(cfg.get("pair.city_engine_bonus", 1.5)),
            ref="B.4",
        )


def _add_number_spread(cfg: Config, numbers: tuple[int, ...], bd: Breakdown) -> None:
    distinct = len(set(numbers))
    if distinct >= 5:
        bd.add(
            "number_diversity",
            f"{distinct} numeri distinti: non dipendi da pochi tiri",
            float(cfg.get("pair.number_diversity_bonus", 1.0)),
            ref="B.4",
        )
    elif distinct <= 3:
        bd.add(
            "number_concentration",
            f"solo {distinct} numeri distinti: partita a lotteria",
            float(cfg.get("pair.number_diversity_penalty", -1.5)),
            ref="B.4",
        )

    total = sum(K.PIPS[n] for n in numbers)
    if total:
        share = {n: sum(K.PIPS[m] for m in numbers if m == n) / total for n in set(numbers)}
        worst, worst_share = max(share.items(), key=lambda kv: kv[1])
        threshold = float(cfg.get("pair.dominant_number_threshold", 0.35))
        if worst_share <= threshold:
            bd.add(
                "no_dominant_number",
                f"nessun numero oltre il {threshold:.0%} dei pip "
                f"(il piu pesante e il {worst} col {worst_share:.0%})",
                float(cfg.get("pair.no_dominant_number_bonus", 0.8)),
                ref="B.4",
            )
        else:
            bd.note(
                "dominant_number",
                f"il {worst} pesa il {worst_share:.0%} dei tuoi pip",
                ref="B.4",
            )


def _add_distinct_tiles(cfg: Config, pair: PairScore, bd: Breakdown) -> None:
    """KB E.6: distinct tiles touched, as robber antifragility."""
    per_tile = float(cfg.get("pair.distinct_tile_bonus", 0.25))
    shared = 6 - pair.distinct_tiles
    label = f"{pair.distinct_tiles} tessere produttive distinte"
    if shared > 0:
        label += f" (ne condividi {shared}: il ladro ti costa di piu)"
    bd.add("distinct_tiles", label, pair.distinct_tiles * per_tile, ref="E.6")


def _add_expansion(
    board: Board, a: str, b: str, cfg: Config, bd: Breakdown
) -> list[ExpansionTarget]:
    """Expansion room of the pair, computed jointly.

    Computed here and not on the members because the two settlements often
    reach the same junctions: scoring them separately would count the same
    square metre of board twice.
    """
    occupied = board.with_placement(Placement(0, a)).with_placement(Placement(0, b))
    reach: dict[str, int] = {}
    for origin in (a, b):
        for vertex, distance in board.geometry.vertices_within(origin, roads=3).items():
            if vertex in (a, b) or not occupied.is_legal(vertex):
                continue
            reach[vertex] = min(reach.get(vertex, 99), distance)

    multiplier = (
        float(cfg.get("vertex.expansion_multiplier_3p", 1.4)) if board.n_players == 3 else 1.0
    )
    counted = int(cfg.get("vertex.expansion_targets_counted", 2)) * 2  # two settlements
    chosen: list[ExpansionTarget] = []
    has_near = False

    for distance, key, coef_key, cap_key, phrase in (
        (2, "expansion_near", "expansion_near_coef", "expansion_near_cap", "a 2 strade"),
        (3, "expansion_far", "expansion_far_coef", "expansion_far_cap", "a 3 strade"),
    ):
        targets = sorted(
            ((v, board.vertex_pips(v)) for v, d in reach.items() if d == distance),
            key=lambda t: (-t[1], t[0]),
        )
        if distance == 2:
            has_near = bool(targets)
        best = targets[:counted]
        if not best:
            continue
        coef = float(cfg.get(f"vertex.{coef_key}", 0.1)) * multiplier
        cap = float(cfg.get(f"vertex.{cap_key}", 1.0)) * multiplier * 2
        value = min(cap, coef * sum(p for _, p in best))
        detail = ", ".join(f"{v} ({p} pip)" for v, p in best)
        bd.add(key, f"espansione {phrase}: {detail}", value, ref="B.3/E.3")
        total_pips = sum(p for _, p in best) or 1
        chosen.extend(ExpansionTarget(v, distance, p, value * p / total_pips) for v, p in best)

    if not has_near:
        bd.add(
            "dead_end",
            "vicolo cieco: nessun incrocio libero a 2 strade da nessuna delle due colonie",
            float(cfg.get("vertex.dead_end_penalty", -1.2)),
            ref="B.3",
        )
    return chosen


def _add_high_number_concentration(
    cfg: Config, board: Board, a: str, b: str, production: dict[str, int], bd: Breakdown
) -> None:
    """Anti-pattern 4 of KB D.5, at the level where it can actually happen.

    The per-junction robber term of B.3 cannot fire on a balanced board, since
    6 and 8 never touch. Across a pair it can: two settlements each sitting on a
    high number make you the table's designated robber target.
    """
    tiles = set(board.geometry.vertex_hexes[a]) | set(board.geometry.vertex_hexes[b])
    high = sum(board.hexes[t].pips for t in tiles if board.hexes[t].number in K.HIGH_NUMBERS)
    total = sum(board.hexes[t].pips for t in tiles)
    if not total:
        return
    share = high / total
    threshold = float(cfg.get("pair.high_number_share_threshold", 0.5))
    if share > threshold:
        bd.add(
            "high_number_concentration",
            f"il {share:.0%} dei tuoi pip sta su 6 e 8: grande su carta, "
            "ma il ladro vivra su di te",
            float(cfg.get("pair.high_number_share_penalty", -1.0)),
            ref="D.5",
        )


def _add_hard_constraints(cfg: Config, pair: PairScore, bd: Breakdown) -> None:
    """KB B.4. A violation never removes a candidate from the ranking -- at pick
    #8 there may be nothing better -- it costs points and raises a red flag."""
    hc = cfg.require("pair.hard_constraints")
    penalty = float(hc.get("violation_penalty", -3.0))
    p = pair.production

    checks = [
        (p[K.WHEAT] < hc["min_wheat_pips"],
         f"grano {p[K.WHEAT]} pip, sotto il minimo di {hc['min_wheat_pips']}: "
         "senza grano non costruisci colonie, citta ne carte"),
        (pair.pips < hc["min_total_pips"],
         f"{pair.pips} pip totali, sotto il minimo di {hc['min_total_pips']}: "
         "sei in ritardo strutturale"),
        (p[K.WOOD] < hc["min_wood_pips"],
         f"legno {p[K.WOOD]} pip, sotto il minimo di {hc['min_wood_pips']}: "
         "senza strade resti a 2 colonie"),
        (p[K.BRICK] < hc["min_brick_pips"],
         f"mattone {p[K.BRICK]} pip, sotto il minimo di {hc['min_brick_pips']}: "
         "senza strade resti a 2 colonie"),
        (pair.resources_covered < hc["min_resources_covered"],
         f"solo {pair.resources_covered} risorse su 5: il buco lo copri solo "
         "con gli scambi, e sei ostaggio del tavolo"),
    ]
    for failed, message in checks:
        if failed:
            pair.violations.append(message)
    if pair.violations:
        bd.add(
            "hard_constraints",
            f"{len(pair.violations)} vincoli hard violati",
            len(pair.violations) * penalty,
            ref="B.4",
        )


def _anti_patterns(cfg: Config, board: Board, pair: PairScore) -> list[str]:
    """The warnings of KB D.5 that are properties of the pair."""
    out = []
    p = pair.production

    for port in pair.ports:
        if port.resource and p.get(port.resource, 0) < 3:
            out.append(
                f"D.5.1 porto senza produzione: {port} ma solo "
                f"{p.get(port.resource, 0)} pip di quella risorsa"
            )

    if p[K.WHEAT] == 0:
        out.append("D.5.2 zero grano: apertura non giocabile")

    for resource in (K.WOOD, K.BRICK):
        if p[resource] == 0:
            out.append(
                f"D.5.3 zero {_RES[resource]}: niente strade, resti bloccato a 2 colonie"
            )

    if pair.resources_covered <= 3 and pair.pips >= 20:
        out.append(
            f"D.5.5 {pair.pips} pip ma solo {pair.resources_covered} risorse: "
            "inseguire i pip ignorando la copertura e il modo classico di perdere"
        )

    shared = 6 - pair.distinct_tiles
    if shared >= 2:
        out.append(
            f"D.5.7 le due colonie condividono {shared} tessere: "
            "raddoppi la varianza invece di diversificarla"
        )

    has_sheep_port = any(port.resource == K.SHEEP for port in pair.ports)
    if p[K.SHEEP] > 6 and not has_sheep_port:
        out.append(
            f"D.5.9 pecora {p[K.SHEEP]} pip senza porto 2:1: e la risorsa con il "
            "peggior tasso di scambio, oltre 6 pip e surplus morto"
        )
    return out


# --- enumeration ------------------------------------------------------------


def legal_pairs(board: Board) -> list[tuple[str, str]]:
    """Pairs of junctions that can both hold a settlement at once."""
    legal = board.legal_vertices
    neighbours = board.geometry.vertex_neighbours
    return [
        (a, b) for a, b in combinations(legal, 2) if b not in neighbours[a]
    ]


def best_pairs(
    board: Board,
    config: Config | None = None,
    first: str | None = None,
    limit: int | None = None,
) -> list[PairScore]:
    """Rank pairs. With `first` fixed, this is the second-pick decision."""
    cfg = config or load_config()
    w = cfg.resource_weights(board.pips_by_resource, board.n_players)
    members = {
        v: score_vertex(board, v, cfg, w, standalone=False) for v in board.legal_vertices
    }

    pairs = legal_pairs(board)
    if first is not None:
        pairs = [(a, b) for a, b in pairs if first in (a, b)]
    scored = [score_pair(board, a, b, cfg, w, members) for a, b in pairs]
    scored.sort(key=lambda s: (-s.score, -s.pips, s.a, s.b))
    return scored[:limit] if limit else scored
