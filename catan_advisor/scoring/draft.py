"""Draft context: what will still be there when it is your turn again (KB C.1).

The value of a pick is not S(v), it is S(v) minus what you could have had at
your next pick -- KB calls it VOR. The knowledge base estimates the erosion with
a constant (2.5 junctions burned per opponent pick). We simulate instead: 54
junctions is a small enough board that playing the remaining picks forward is
cheap, and unlike a constant it also tells us *which* junctions survive, which
is exactly the fallback plan the output of D.3 has to contain.

Opponent model: each opponent takes the best junction available by standalone
S(v), with multiplicative noise so that the simulation explores the plausible
alternatives rather than one deterministic line. This deliberately ignores that
an opponent's second settlement should complement their first; modelling that
would multiply the cost by the number of pairs, and at the table people do
mostly take the best remaining spot.
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field

from ..board import Board, Placement
from ..config import Config, load_config
from .pair import PairScore, score_pair
from .vertex import VertexScore, score_vertex


def snake_order(n_players: int) -> list[int]:
    """Player number for each pick of the placement phase, 1-based picks."""
    return list(range(1, n_players + 1)) + list(range(n_players, 0, -1))


@dataclass
class DraftContext:
    n_players: int
    my_position: int
    order: list[int]
    picks_made: int

    @property
    def next_pick(self) -> int | None:
        """1-based number of my next pick, or None if I have placed both."""
        for index in range(self.picks_made, len(self.order)):
            if self.order[index] == self.my_position:
                return index + 1
        return None

    @property
    def my_picks(self) -> tuple[int, int]:
        picks = [i + 1 for i, p in enumerate(self.order) if p == self.my_position]
        return picks[0], picks[1]

    @property
    def is_first_pick(self) -> bool:
        return self.next_pick == self.my_picks[0]

    @property
    def waiting_picks(self) -> int:
        """Opponent picks between my next pick and the one after it."""
        first, second = self.my_picks
        if self.next_pick != first:
            return 0
        return second - first - 1

    def opponent_picks_before_my_next(self) -> int:
        if self.next_pick is None:
            return 0
        return self.next_pick - self.picks_made - 1

    def describe(self) -> str:
        first, second = self.my_picks
        if self.next_pick is None:
            return f"P{self.my_position}: entrambe le colonie piazzate"
        which = "primo" if self.is_first_pick else "secondo"
        return (
            f"P{self.my_position} su {self.n_players}, {which} pick (#{self.next_pick} "
            f"di {len(self.order)}), i tuoi pick sono #{first} e #{second}, "
            f"k = {self.waiting_picks} pick di attesa"
        )


def draft_context(board: Board) -> DraftContext:
    return DraftContext(
        n_players=board.n_players,
        my_position=board.my_position,
        order=snake_order(board.n_players),
        picks_made=len(board.placements),
    )


@dataclass
class Simulation:
    samples: int
    survival: dict[str, float]              # vertex -> P(still legal at my next pick)
    opponent_picks: Counter                 # vertex -> how often an opponent took it

    def surviving(self, threshold: float = 0.5) -> list[str]:
        return [v for v, p in self.survival.items() if p >= threshold]


def _static_scores(board: Board, cfg: Config) -> dict[str, float]:
    """S(v) computed once on the current board.

    Used only as the opponents' preference ordering during simulation, so it can
    ignore how placements slightly change the expansion term -- resampling every
    junction after every simulated pick would cost far more than it is worth.
    """
    w = cfg.resource_weights(board.pips_by_resource, board.n_players)
    return {
        v: score_vertex(board, v, cfg, w, standalone=True).score
        for v in board.geometry.vertex_ids
    }


def simulate_opponents(
    board: Board,
    cfg: Config | None = None,
    my_choice: str | None = None,
    samples: int | None = None,
    seed: int | None = 0,
    static: dict[str, float] | None = None,
) -> Simulation:
    """Play the opponents' picks forward until my next turn."""
    cfg = cfg or load_config()
    samples = samples or int(cfg.get("draft.simulation_samples", 24))
    noise = float(cfg.get("draft.simulation_noise", 0.15))
    scores = static if static is not None else _static_scores(board, cfg)
    context = draft_context(board)

    base = board
    if my_choice is not None:
        base = board.with_placement(Placement(board.my_position, my_choice))
    to_simulate = context.opponent_picks_before_my_next()
    if my_choice is not None:
        # I have just taken my pick, so the remaining wait is k.
        to_simulate = context.waiting_picks

    rng = random.Random(seed)
    survival = Counter()
    taken = Counter()
    for _ in range(samples):
        state = base
        for _ in range(to_simulate):
            options = state.legal_vertices
            if not options:
                break
            pick = max(options, key=lambda v: scores[v] * (1.0 + rng.gauss(0.0, noise)))
            state = state.with_placement(Placement(0, pick))
            taken[pick] += 1
        for v in state.legal_vertices:
            survival[v] += 1

    return Simulation(
        samples=samples,
        survival={v: survival[v] / samples for v in board.geometry.vertex_ids},
        opponent_picks=taken,
    )


def erosion_estimate(board: Board, cfg: Config | None = None) -> float:
    """KB C.1 degraded mode, for when the board is only partly known."""
    cfg = cfg or load_config()
    rate = float(cfg.get("draft.erosion_rate", 2.5))
    return draft_context(board).waiting_picks * rate


@dataclass
class FirstPickOption:
    """A candidate first settlement, judged by the pair it is likely to become."""

    vertex: str
    vertex_score: VertexScore
    expected_pair_score: float
    plan: PairScore                      # the pair if the plan holds
    plan_probability: float              # how often the planned partner survived
    fallbacks: list[tuple[str, float]]   # (partner, frequency)
    vor: float = 0.0

    @property
    def score(self) -> float:
        return self.expected_pair_score

    def headline(self) -> str:
        return (
            f"{self.vertex}  attesa coppia {self.expected_pair_score:6.2f}  "
            f"S(v)={self.vertex_score.score:5.2f}  pip {self.vertex_score.pips:>2}  "
            f"piano {self.plan.b if self.plan.a == self.vertex else self.plan.a} "
            f"({self.plan_probability:.0%})"
        )


def evaluate_first_pick(
    board: Board,
    cfg: Config | None = None,
    candidates: int | None = None,
    samples: int | None = None,
    seed: int | None = 0,
) -> list[FirstPickOption]:
    """Rank first settlements by the pair they can realistically become.

    KB D.2: for each strong candidate, simulate the wait and take the best
    partner still available. The average over samples is the number that
    matters; the spread over samples is the fallback plan.
    """
    cfg = cfg or load_config()
    candidates = candidates or int(cfg.get("report.first_pick_candidates", 8))
    w = cfg.resource_weights(board.pips_by_resource, board.n_players)
    static = _static_scores(board, cfg)
    members = {
        v: score_vertex(board, v, cfg, w, standalone=False)
        for v in board.geometry.vertex_ids
    }

    ranked = sorted(board.legal_vertices, key=lambda v: -static[v])[:candidates]
    options: list[FirstPickOption] = []

    for vertex in ranked:
        simulation = simulate_opponents(
            board, cfg, my_choice=vertex, samples=samples, seed=seed, static=static
        )
        mine = board.with_placement(Placement(board.my_position, vertex))
        partner_cache: dict[str, PairScore] = {}

        def pair_with(other: str) -> PairScore:
            if other not in partner_cache:
                partner_cache[other] = score_pair(mine, vertex, other, cfg, w, members)
            return partner_cache[other]

        # Candidate partners, ranked once: the simulation only decides which of
        # them are still on the table.
        eligible = [v for v in mine.legal_vertices if simulation.survival.get(v, 0) > 0]
        eligible.sort(key=lambda v: -pair_with(v).score)
        if not eligible:
            continue

        # Expected best partner: walk the ranked list, each partner claims the
        # probability mass not already claimed by a better one that survived.
        total = 0.0
        chosen = Counter()
        remaining = 1.0
        for partner in eligible:
            p = simulation.survival[partner]
            weight = remaining * p
            if weight <= 1e-9:
                continue
            total += weight * pair_with(partner).score
            chosen[partner] = weight
            remaining -= weight
            if remaining <= 1e-6:
                break
        if remaining > 1e-6 and eligible:
            worst = pair_with(eligible[-1]).score
            total += remaining * worst

        plan_partner, plan_weight = chosen.most_common(1)[0]
        options.append(
            FirstPickOption(
                vertex=vertex,
                vertex_score=score_vertex(board, vertex, cfg, w, standalone=True),
                expected_pair_score=total,
                plan=pair_with(plan_partner),
                plan_probability=plan_weight,
                fallbacks=[(v, wgt) for v, wgt in chosen.most_common(4)[1:]],
                vor=static[vertex] - expected_best_available(simulation, static),
            )
        )

    options.sort(key=lambda o: -o.expected_pair_score)
    return options


def expected_best_available(simulation: Simulation, static: dict[str, float]) -> float:
    """E[best junction still free at my next pick], the replacement level of C.1."""
    ranked = sorted(simulation.survival, key=lambda v: -static[v])
    remaining = 1.0
    expected = 0.0
    for vertex in ranked:
        weight = remaining * simulation.survival[vertex]
        if weight <= 1e-9:
            continue
        expected += weight * static[vertex]
        remaining -= weight
        if remaining <= 1e-6:
            break
    return expected
