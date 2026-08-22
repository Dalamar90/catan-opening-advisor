"""S(v): the score of a single junction, KB B.3.

Everything is expressed in pips, where one pip is 1/36 of a card per roll, so
that bonuses and production stay on the same scale and remain comparable.

The raw pip count travels alongside the score at all times: the score is the
model's opinion, the pip count is the fact you can check by eye at the table.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .. import constants as K
from ..board import Board
from ..config import Config, load_config
from .breakdown import Breakdown
from .ports import score_port


@dataclass
class VertexScore:
    vertex: str
    label: str
    pips: int
    weighted_pips: float
    production: dict[str, int]
    numbers: tuple[int, ...]
    resources: tuple[str, ...]
    port: str | None
    legal: bool
    n_players: int
    breakdown: Breakdown
    expansion_targets: list[tuple[str, int, int]] = field(default_factory=list)

    @property
    def score(self) -> float:
        return self.breakdown.total

    @property
    def cards_per_roll(self) -> float:
        return K.expected_cards_per_roll(self.pips)

    @property
    def cards_per_round(self) -> float:
        return K.expected_cards_per_round(self.pips, self.n_players)

    def headline(self) -> str:
        return (
            f"{self.vertex}  S={self.score:5.2f}  pip {self.pips:>2} "
            f"(pesati {self.weighted_pips:4.1f})  "
            f"{self.cards_per_round:.2f} carte/giro  [{self.label}]"
        )


def score_vertex(
    board: Board,
    vertex_id: str,
    config: Config | None = None,
    weights: dict[str, float] | None = None,
    include_diversity: bool = True,
) -> VertexScore:
    """Score one junction as a standalone candidate.

    `include_diversity` exists because resource variety is a property of the
    portfolio, not of a junction (KB E.2). It is on when ranking junctions in
    isolation and off when the pair evaluation of M3 accounts for variety once.
    """
    cfg = config or load_config()
    w = weights if weights is not None else cfg.resource_weights(
        board.pips_by_resource, board.n_players
    )
    production = board.vertex_production(vertex_id)
    numbers = board.vertex_numbers(vertex_id)
    bd = Breakdown(subject=vertex_id)

    _add_production(board, vertex_id, w, bd)
    if include_diversity:
        _add_diversity(cfg, production, bd)
    _add_number_quality(cfg, numbers, bd)
    targets = _add_expansion(board, vertex_id, cfg, bd)
    score_port(cfg, board.vertex_port(vertex_id), production, portfolio_known=False, breakdown=bd)
    _add_robber_risk(board, vertex_id, cfg, targets, bd)

    return VertexScore(
        vertex=vertex_id,
        label=board.vertex_label(vertex_id),
        pips=board.vertex_pips(vertex_id),
        weighted_pips=sum(p * w[r] for r, p in production.items()),
        production=production,
        numbers=numbers,
        resources=tuple(sorted(production)),
        port=str(board.vertex_port(vertex_id)) if board.vertex_port(vertex_id) else None,
        legal=board.is_legal(vertex_id),
        n_players=board.n_players,
        breakdown=bd,
        expansion_targets=targets,
    )


# --- terms ------------------------------------------------------------------


def _add_production(board: Board, vertex_id: str, w: dict[str, float], bd: Breakdown) -> None:
    """One line per tile, so the explanation shows where the pips come from."""
    for hex_ in sorted(board.vertex_hexes(vertex_id), key=lambda h: -h.pips):
        if hex_.is_desert:
            bd.note("production_desert", f"{hex_.id} deserto: nessuna produzione", ref="B.1")
            continue
        weight = w[hex_.resource]
        bd.add(
            "production",
            f"{hex_} : {hex_.pips} pip x {weight:.2f}",
            hex_.pips * weight,
            ref="B.2",
        )


def _add_diversity(cfg: Config, production: dict[str, int], bd: Breakdown) -> None:
    per_resource = float(cfg.get("vertex.diversity_per_resource", 1.5))
    n = len(production)
    if n:
        names = ", ".join(K.RESOURCE_LABEL_IT[r] for r in sorted(production))
        bd.add(
            "diversity",
            f"{n} risorse distinte ({names})",
            n * per_resource,
            ref="B.3",
        )


def _add_number_quality(cfg: Config, numbers: tuple[int, ...], bd: Breakdown) -> None:
    if len(numbers) == 3 and len(set(numbers)) == 3:
        bd.add("distinct_numbers", "tre numeri distinti",
               float(cfg.get("vertex.distinct_numbers_bonus", 0.5)), ref="B.3")

    repetitions = len(numbers) - len(set(numbers))
    if repetitions:
        repeated = sorted({n for n in numbers if numbers.count(n) > 1})
        bd.add(
            "repeated_number",
            f"numero ripetuto ({', '.join(map(str, repeated))}): varianza alta",
            repetitions * float(cfg.get("vertex.repeated_number_penalty", -0.8)),
            ref="B.3",
        )

    mid = [n for n in numbers if n in K.MID_BAND]
    if len(mid) >= 2:
        bd.add("mid_band", f"{len(mid)} numeri in fascia media",
               float(cfg.get("vertex.mid_band_bonus", 0.5)), ref="B.3")
    elif numbers and all(n in K.EXTREME_NUMBERS for n in numbers):
        bd.add(
            "extremes_only",
            f"solo numeri estremi ({', '.join(map(str, numbers))})",
            float(cfg.get("vertex.extremes_only_penalty", -1.5)),
            ref="B.3",
        )


def _add_expansion(
    board: Board, vertex_id: str, cfg: Config, bd: Breakdown
) -> list[tuple[str, int, int]]:
    """Reachable production, KB B.3 corrected by E.3.

    Distance 1 is deliberately absent: a junction adjacent to this one can never
    be settled, because our own settlement blocks it under the distance rule.
    Returns the counted targets as (vertex, distance, pips).
    """
    reach = board.geometry.vertices_within(vertex_id, roads=3)
    multiplier = float(cfg.get("vertex.expansion_multiplier_3p", 1.4)) if board.n_players == 3 else 1.0
    counted = int(cfg.get("vertex.expansion_targets_counted", 2))

    tiers = [
        (2, "expansion_near", "expansion_near_coef", "expansion_near_cap", "a 2 strade"),
        (3, "expansion_far", "expansion_far_coef", "expansion_far_cap", "a 3 strade"),
    ]
    chosen: list[tuple[str, int, int]] = []
    near_targets: list[str] = []

    for distance, key, coef_key, cap_key, phrase in tiers:
        targets = [
            (v, board.vertex_pips(v))
            for v, d in reach.items()
            if d == distance and board.is_legal(v)
        ]
        targets.sort(key=lambda t: (-t[1], t[0]))
        if distance == 2:
            near_targets = [v for v, _ in targets]

        best = targets[:counted]
        if not best:
            continue
        # The 3-player multiplier scales the cap too: capping afterwards would
        # silently cancel the boost exactly on the junctions it should reward.
        coef = float(cfg.get(f"vertex.{coef_key}", 0.1)) * multiplier
        cap = float(cfg.get(f"vertex.{cap_key}", 1.0)) * multiplier
        value = min(cap, coef * sum(p for _, p in best))
        detail = ", ".join(f"{v} ({p} pip)" for v, p in best)
        bd.add(key, f"espansione {phrase}: {detail}", value, ref="B.3/E.3")
        chosen.extend((v, distance, p) for v, p in best)

    if not near_targets:
        bd.add(
            "dead_end",
            "vicolo cieco: nessun incrocio libero a 2 strade",
            float(cfg.get("vertex.dead_end_penalty", -1.2)),
            ref="B.3",
        )
    return chosen


def _add_robber_risk(
    board: Board,
    vertex_id: str,
    cfg: Config,
    targets: list[tuple[str, int, int]],
    bd: Breakdown,
) -> None:
    high = sum(h.pips for h in board.vertex_hexes(vertex_id) if h.number in K.HIGH_NUMBERS)
    threshold = int(cfg.get("vertex.robber_pip_threshold", 10))
    isolated = not any(distance == 2 for _, distance, _ in targets)
    if high >= threshold and isolated:
        bd.add(
            "robber_target",
            f"{high} pip su 6/8 e nessuna via di fuga: bersaglio designato del ladro",
            float(cfg.get("vertex.robber_target_penalty", -0.6)),
            ref="B.3",
        )


def score_all(
    board: Board,
    config: Config | None = None,
    legal_only: bool = True,
    include_diversity: bool = True,
) -> list[VertexScore]:
    cfg = config or load_config()
    w = cfg.resource_weights(board.pips_by_resource, board.n_players)
    scores = [
        score_vertex(board, v, cfg, w, include_diversity)
        for v in board.geometry.vertex_ids
        if board.is_legal(v) or not legal_only
    ]
    scores.sort(key=lambda s: (-s.score, -s.pips, s.vertex))
    return scores
