"""Turning scores into advice: the recommendation objects of KB D.3.

The reasons and the risks are *mined from the breakdown*, never written by hand.
That is the whole point of having made every score a list of labelled
contributions: when a weight changes, the explanation changes with it instead of
drifting into fiction. A bullet you read here corresponds to a term that really
moved the number.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import constants as K
from .board import Board, Placement
from .config import Config, load_config
from .precompute import Precompute, precompute
from .roads import RoadOption, best_roads
from .scoring.draft import (
    DraftContext,
    FirstPickOption,
    Simulation,
    draft_context,
    evaluate_first_pick,
    simulate_opponents,
)
from .scoring.market import OpponentProfile, my_placements, profile_opponents
from .scoring.pair import PairScore, best_pairs
from .scoring.vertex import VertexScore, score_vertex

_RES = K.RESOURCE_LABEL_IT

# Breakdown keys whose labels already read as an explanation. Production lines
# are excluded: they are summarised in one line instead of listed one by one.
_REASON_KEYS = (
    "coverage",
    "city_engine",
    "wheat_engine",
    "wood_brick_balance",
    "number_diversity",
    "no_dominant_number",
    "distinct_tiles",
    "expansion_near",
    "expansion_far",
    "port_specific",
    "port_generic",
    "port_option",
    "monopoly",
    "neglected_numbers",
)


@dataclass
class Recommendation:
    rank: int
    vertex: str                       # the settlement to place now
    vertex_score: VertexScore
    pair: PairScore                   # the plan this settlement is half of
    partner: str
    plan_probability: float
    expected_score: float
    reasons: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    road: RoadOption | None = None
    road_alternative: RoadOption | None = None
    fallbacks: list[tuple[str, float]] = field(default_factory=list)
    availability: float = 1.0   # chance it is still free when my turn comes
    landing: float = 1.0        # chance this is the one I actually end up taking

    @property
    def archetype(self) -> str:
        return self.pair.archetype()


@dataclass
class Advice:
    board: Board
    context: DraftContext
    precomputed: Precompute
    profiles: list[OpponentProfile]
    recommendations: list[Recommendation]
    simulation: Simulation | None = None
    existing: tuple[str, ...] = ()
    pending_opponent_picks: int = 0

    @property
    def is_first_pick(self) -> bool:
        return self.context.is_first_pick

    @property
    def turn_not_reached(self) -> bool:
        """True when opponents still have to place before me.

        The advice is then a plan, not a decision: what it ranks may well be
        gone by the time I actually pick. Entering their placements as they
        happen turns the plan back into a decision.
        """
        return self.pending_opponent_picks > 0


def advise(
    board: Board,
    config: Config | None = None,
    limit: int | None = None,
    samples: int | None = None,
) -> Advice:
    cfg = config or load_config()
    limit = limit or int(cfg.get("report.min_recommendations", 3))
    context = draft_context(board)
    pre = precompute(board, cfg)
    profiles = profile_opponents(board)
    mine = my_placements(board)

    if context.next_pick is None:
        return Advice(board, context, pre, profiles, [], existing=mine)

    pending = context.opponent_picks_before_my_next()
    # With opponents still to place, three options may not cover what will
    # realistically be left, so the list is grown and trimmed by coverage below.
    wanted = max(limit, 6) if pending else limit
    if context.is_first_pick:
        recommendations, simulation = _first_pick_advice(board, cfg, wanted, samples, pre)
    else:
        recommendations, simulation = _second_pick_advice(board, cfg, wanted, mine, pre)

    if pending:
        # Opponents still have to place, so the ranking is a priority list, not
        # a single choice: I take the best option that is still on the table.
        # Each option therefore gets two numbers -- how likely it is to survive,
        # and how likely it is to be the one I actually end up with.
        before = simulate_opponents(board, cfg, samples=samples)
        remaining = 1.0
        covered = 0.0
        kept: list[Recommendation] = []
        for rec in recommendations:
            rec.availability = before.survival.get(rec.vertex, 1.0)
            rec.landing = remaining * rec.availability
            remaining -= rec.landing
            kept.append(rec)
            covered += rec.landing
            if len(kept) >= limit and covered >= 0.85:
                break
        recommendations = kept
        for rank, rec in enumerate(recommendations, start=1):
            rec.rank = rank

    return Advice(
        board=board,
        context=context,
        precomputed=pre,
        profiles=profiles,
        recommendations=recommendations,
        simulation=simulation,
        existing=mine,
        pending_opponent_picks=pending,
    )


def _first_pick_advice(board, cfg, limit, samples, pre):
    options = evaluate_first_pick(board, cfg, samples=samples)
    if not options:
        return [], None
    simulation = simulate_opponents(
        board, cfg, my_choice=options[0].vertex, samples=samples
    )
    recommendations = []
    for rank, option in enumerate(options[:limit], start=1):
        recommendations.append(_from_first_pick(board, cfg, rank, option, simulation, pre))
    return recommendations, simulation


def _from_first_pick(
    board: Board,
    cfg: Config,
    rank: int,
    option: FirstPickOption,
    simulation: Simulation,
    pre: Precompute,
) -> Recommendation:
    partner = option.plan.b if option.plan.a == option.vertex else option.plan.a
    roads = best_roads(
        board, option.vertex, option.plan.production, cfg, simulation.survival
    )
    rec = Recommendation(
        rank=rank,
        vertex=option.vertex,
        vertex_score=option.vertex_score,
        pair=option.plan,
        partner=partner,
        plan_probability=option.plan_probability,
        expected_score=option.expected_pair_score,
        road=roads[0] if roads else None,
        road_alternative=roads[1] if len(roads) > 1 else None,
        fallbacks=option.fallbacks,
    )
    rec.reasons = _reasons(board, cfg, rec, pre, option)
    rec.risks = _risks(board, cfg, rec, simulation)
    return rec


def _second_pick_advice(board, cfg, limit, mine, pre):
    first = mine[0] if mine else None
    if first is None:
        return [], None
    pairs = best_pairs(board, cfg, first=first, limit=limit)
    w = cfg.resource_weights(board.pips_by_resource, board.n_players)
    recommendations = []
    for rank, pair in enumerate(pairs, start=1):
        second = pair.b if pair.a == first else pair.a
        # The placement phase is over after this pick, so nothing left to survive.
        roads = best_roads(board, second, pair.production, cfg)
        rec = Recommendation(
            rank=rank,
            vertex=second,
            vertex_score=score_vertex(board, second, cfg, w, standalone=True),
            pair=pair,
            partner=first,
            plan_probability=1.0,
            expected_score=pair.score,
            road=roads[0] if roads else None,
            road_alternative=roads[1] if len(roads) > 1 else None,
        )
        rec.reasons = _reasons(board, cfg, rec, pre)
        rec.risks = _risks(board, cfg, rec, None)
        recommendations.append(rec)
    return recommendations, None


# --- mining the breakdown ---------------------------------------------------


def _reasons(
    board: Board,
    cfg: Config,
    rec: Recommendation,
    pre: Precompute,
    option: FirstPickOption | None = None,
) -> list[str]:
    out: list[str] = []
    score = rec.vertex_score

    rank = 1 + sum(
        1 for s in pre.vertices if s.legal and s.pips > score.pips
    )
    out.append(
        f"{score.pips} pip ({score.cards_per_round:.2f} carte a giro), "
        f"il {rank}o valore fra gli incroci ancora liberi; "
        f"produce {_production_phrase(score.production)}"
    )

    scarce = _scarce_resources_taken(pre, rec.pair.production)
    if scarce:
        out.append(
            "prende la fetta migliore di "
            + " e ".join(scarce)
            + ", la risorsa piu scarsa di questo tabellone"
        )

    for contribution in rec.pair.breakdown.by_magnitude():
        if contribution.value <= 0:
            continue
        key = contribution.key.split(".")[-1]
        if key in _REASON_KEYS:
            out.append(f"{contribution.label} ({contribution.value:+.1f})")
        if len(out) >= 6:
            break

    if option is not None and option.vor > 0:
        out.append(
            f"VOR {option.vor:+.2f}: vale piu di quanto ti aspetti di trovare "
            "al prossimo pick"
        )
    return out


def _risks(
    board: Board, cfg: Config, rec: Recommendation, simulation: Simulation | None
) -> list[str]:
    out: list[str] = []

    for violation in rec.pair.violations:
        out.append(f"VINCOLO HARD: {violation}")
    for warning in rec.pair.warnings:
        out.append(warning)

    for contribution in rec.pair.breakdown.by_magnitude():
        if contribution.value >= 0:
            continue
        key = contribution.key.split(".")[-1]
        if key in ("hard_constraints",):
            continue
        out.append(f"{contribution.label} ({contribution.value:+.1f})")

    missing = [r for r, p in rec.pair.production.items() if p == 0]
    if missing:
        out.append(
            "la coppia non produce "
            + " ne ".join(_RES[r] for r in missing)
            + ": dipenderai dagli scambi"
        )

    if rec.plan_probability < 0.6 and simulation is not None:
        out.append(
            f"il piano su {rec.partner} regge solo il {rec.plan_probability:.0%} "
            "delle volte: preparati al fallback"
        )
    if rec.road and rec.road.warnings:
        out.extend(rec.road.warnings)
    return out


def _production_phrase(production: dict[str, int]) -> str:
    parts = [
        f"{_RES[r]} {p}"
        for r, p in sorted(production.items(), key=lambda kv: -kv[1])
        if p
    ]
    return ", ".join(parts) if parts else "nulla"


def _scarce_resources_taken(pre: Precompute, production: dict[str, int]) -> list[str]:
    """Resources that are scarce on this board and that this pair actually gets."""
    out = []
    for resource in K.RESOURCES:
        row = pre.scarcity[resource]
        if row["ratio"] <= 0.85 and production.get(resource, 0) >= 4:
            out.append(_RES[resource])
    return out
