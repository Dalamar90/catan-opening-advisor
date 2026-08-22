"""Draft context, opponent simulation, market reading and roads (M4, KB C)."""

import pytest

from catan_advisor import constants as K
from catan_advisor.board import Placement
from catan_advisor.boardio import random_board
from catan_advisor.config import load_config
from catan_advisor.geometry import GEOMETRY as G
from catan_advisor.roads import best_roads, score_road
from catan_advisor.scoring import best_pairs, score_pair
from catan_advisor.scoring.draft import (
    DraftContext,
    draft_context,
    erosion_estimate,
    evaluate_first_pick,
    expected_best_available,
    simulate_opponents,
    snake_order,
)
from catan_advisor.scoring.market import profile_opponents, read_market


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture
def board():
    return random_board(seed=7)


# --- snake draft ------------------------------------------------------------


def test_snake_order_matches_the_kb_table():
    assert snake_order(4) == [1, 2, 3, 4, 4, 3, 2, 1]
    assert snake_order(3) == [1, 2, 3, 3, 2, 1]


@pytest.mark.parametrize(
    "position,n_players,picks",
    [(1, 4, (1, 8)), (2, 4, (2, 7)), (3, 4, (3, 6)), (4, 4, (4, 5)),
     (1, 3, (1, 6)), (2, 3, (2, 5)), (3, 3, (3, 4))],
)
def test_my_picks_match_constants(position, n_players, picks):
    context = DraftContext(n_players, position, snake_order(n_players), 0)
    assert context.my_picks == picks == K.pick_numbers(position, n_players)
    assert context.waiting_picks == K.waiting_picks(position, n_players)


def test_context_tracks_progress_through_the_draft(board):
    board.my_position = 2
    assert draft_context(board).is_first_pick
    assert draft_context(board).next_pick == 2

    order = snake_order(4)
    placed = board
    for pick, player in enumerate(order[:6], start=1):
        choice = max(placed.legal_vertices, key=lambda v: (placed.vertex_pips(v), v))
        placed = placed.with_placement(Placement(player, choice, order=pick))
    placed.my_position = 2
    context = draft_context(placed)
    assert not context.is_first_pick
    assert context.next_pick == 7
    assert context.waiting_picks == 0


def test_context_reports_when_there_is_nothing_left_to_pick(board):
    board.my_position = 4
    order = snake_order(4)
    placed = board
    for pick, player in enumerate(order, start=1):
        choice = max(placed.legal_vertices, key=lambda v: (placed.vertex_pips(v), v))
        placed = placed.with_placement(Placement(player, choice, order=pick))
    placed.my_position = 4
    assert draft_context(placed).next_pick is None


# --- simulation -------------------------------------------------------------


def test_nothing_is_simulated_when_it_is_already_my_turn(board, cfg):
    board.my_position = 1
    simulation = simulate_opponents(board, cfg)
    assert all(p == 1.0 for p in simulation.survival.values())
    assert not simulation.opponent_picks


def test_waiting_six_picks_burns_most_of_the_good_junctions(board, cfg):
    board.my_position = 1
    simulation = simulate_opponents(board, cfg, my_choice="v26")
    gone = [v for v, p in simulation.survival.items() if p < 0.5]
    # Each settlement burns itself plus up to three neighbours.
    assert 12 <= len(gone) <= 6 * 4 + 4
    assert simulation.survival["v26"] == 0.0
    for neighbour in G.vertex_neighbours["v26"]:
        assert simulation.survival[neighbour] == 0.0


def test_simulation_is_reproducible(board, cfg):
    board.my_position = 1
    a = simulate_opponents(board, cfg, my_choice="v26", seed=3)
    b = simulate_opponents(board, cfg, my_choice="v26", seed=3)
    assert a.survival == b.survival


def test_opponents_prefer_the_strong_junctions(board, cfg):
    board.my_position = 1
    simulation = simulate_opponents(board, cfg, my_choice="v01")
    contested = [v for v, _ in simulation.opponent_picks.most_common(5)]
    average_pips = sum(board.vertex_pips(v) for v in contested) / len(contested)
    assert average_pips > 8


def test_expected_best_available_is_between_the_extremes(board, cfg):
    board.my_position = 1
    from catan_advisor.scoring.draft import _static_scores

    static = _static_scores(board, cfg)
    simulation = simulate_opponents(board, cfg, my_choice="v26")
    value = expected_best_available(simulation, static)
    survivors = [v for v, p in simulation.survival.items() if p > 0]
    assert min(static[v] for v in survivors) <= value <= max(static[v] for v in survivors)


def test_static_erosion_estimate_still_available(board, cfg):
    board.my_position = 1
    assert erosion_estimate(board, cfg) == pytest.approx(6 * 2.5)


# --- first pick -------------------------------------------------------------


def test_first_pick_options_are_ranked_by_expected_pair(board, cfg):
    board.my_position = 1
    options = evaluate_first_pick(board, cfg, candidates=5)
    assert options
    scores = [o.expected_pair_score for o in options]
    assert scores == sorted(scores, reverse=True)


def test_the_planned_partner_is_a_legal_partner(board, cfg):
    board.my_position = 1
    for option in evaluate_first_pick(board, cfg, candidates=4):
        partner = option.plan.b if option.plan.a == option.vertex else option.plan.a
        assert partner != option.vertex
        assert partner not in G.vertex_neighbours[option.vertex]
        assert 0 < option.plan_probability <= 1


def test_position_four_can_plan_a_pair_that_position_one_cannot(board, cfg):
    """P4 picks twice in a row, so its plan cannot be stolen; P1 waits six picks."""
    board.my_position = 4
    late = evaluate_first_pick(board, cfg, candidates=4)
    board_early = random_board(seed=7)
    board_early.my_position = 1
    early = evaluate_first_pick(board_early, cfg, candidates=4)
    assert max(o.plan_probability for o in late) == 1.0
    assert max(o.plan_probability for o in early) < 1.0


# --- opponents and market ---------------------------------------------------


def test_profiles_exclude_me_and_aggregate_my_opponents(board):
    board.my_position = 2
    board.placements = (
        Placement(1, "v26", order=1),
        Placement(2, "v23", order=2),
        Placement(3, "v46", order=3),
    )
    profiles = profile_opponents(board)
    assert [p.player for p in profiles] == [1, 3]
    p1 = profiles[0]
    assert p1.production == {
        r: board.vertex_production("v26").get(r, 0) for r in K.RESOURCES
    }
    assert p1.pips == board.vertex_pips("v26")


def test_market_finds_monopolies_and_saturation():
    from catan_advisor.scoring.market import OpponentProfile

    def profile(player, **production):
        full = {r: production.get(r, 0) for r in K.RESOURCES}
        return OpponentProfile(player, ("v01",), full, (6,), frozenset({"h01"}), ())

    profiles = [profile(1, wood=5, wheat=4), profile(3, wood=3, sheep=6)]
    mine = {K.WOOD: 4, K.BRICK: 6, K.WHEAT: 3, K.SHEEP: 0, K.ORE: 0}
    view = read_market(mine, (6, 8, 5), profiles)
    assert K.BRICK in view.monopolies          # nobody else has brick
    assert K.WHEAT not in view.monopolies      # P1 has it
    assert K.WOOD in view.saturated            # everybody has it
    assert view.leader == 1


def test_market_terms_reach_the_pair_score(board, cfg):
    board.my_position = 2
    empty = score_pair(board, "v13", "v32", cfg)
    board.placements = (Placement(1, "v23", order=1), Placement(3, "v20", order=2))
    with_opponents = score_pair(board, "v13", "v32", cfg)
    assert not empty.market.profiles
    assert with_opponents.market.profiles
    assert with_opponents.score != empty.score


def test_no_opponents_means_no_market_terms(board, cfg):
    pair = score_pair(board, "v13", "v32", cfg)
    for key in ("monopoly", "saturated", "neglected_numbers", "shared_with_leader"):
        assert not pair.breakdown.has(key)


def test_second_pick_pairs_with_an_already_placed_settlement(board, cfg):
    """Regression: the first settlement is no longer a legal vertex, so pairing
    used to return nothing at all for the second pick."""
    board.my_position = 2
    board.placements = (Placement(2, "v26", order=1), Placement(1, "v23", order=2))
    pairs = best_pairs(board, cfg, first="v26", limit=5)
    assert pairs
    for p in pairs:
        assert p.a == "v26"
        assert p.b not in G.vertex_neighbours["v26"]
        assert board.is_legal(p.b)


# --- roads ------------------------------------------------------------------


def test_a_road_reserves_junctions_two_and_three_steps_away(board, cfg):
    production = {r: 3 for r in K.RESOURCES}
    for option in best_roads(board, "v26", production, cfg):
        assert option.towards in G.vertex_neighbours["v26"]
        distances = G.vertices_within("v26", roads=3)
        for target in option.targets:
            assert distances[target.vertex] == target.distance
            assert target.distance in (2, 3)


def test_the_road_prefers_the_target_that_fills_a_gap(board, cfg):
    """A junction that covers a missing resource must beat an equally productive
    one that only piles up what we already have."""
    from catan_advisor.roads import marginal_value

    w = cfg.resource_weights(board.pips_by_resource, board.n_players)
    have_everything = {r: 6 for r in K.RESOURCES}
    missing_sheep = dict(have_everything, sheep=0)
    sheep_vertex = next(
        v for v in G.vertex_ids if board.vertex_production(v).get(K.SHEEP, 0) >= 3
    )
    filling, note = marginal_value(cfg, board, sheep_vertex, missing_sheep, w)
    piling, _ = marginal_value(cfg, board, sheep_vertex, have_everything, w)
    assert filling > piling
    assert "pecora" in note


def test_survival_discounts_the_reservation(board, cfg):
    production = {r: 3 for r in K.RESOURCES}
    edge = G.vertex_edges["v26"][0]
    certain = score_road(board, "v26", edge, production, cfg)
    doomed = score_road(
        board, "v26", edge, production, cfg,
        survival={v: 0.1 for v in G.vertex_ids},
    )
    assert doomed.value < certain.value


def test_a_road_with_no_outlet_is_flagged(board, cfg):
    blocked = board
    target = "v01"
    for candidate, distance in G.vertices_within(target, roads=2).items():
        if distance == 2 and blocked.is_legal(candidate):
            blocked = blocked.with_placement(Placement(9, candidate))
    production = {r: 3 for r in K.RESOURCES}
    options = best_roads(blocked, target, production, cfg)
    assert all(any("D.5.8" in w for w in o.warnings) for o in options)


def test_road_must_start_from_the_settlement(board, cfg):
    far_edge = next(e for e in G.edge_ids if "v26" not in G.edge_vertices[e])
    with pytest.raises(ValueError):
        score_road(board, "v26", far_edge, {r: 3 for r in K.RESOURCES}, cfg)
