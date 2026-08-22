"""S(v) and the breakdown machinery (M2, KB B.3)."""

import pytest

from catan_advisor import constants as K
from catan_advisor.board import Placement
from catan_advisor.boardio import random_board
from catan_advisor.config import load_config
from catan_advisor.scoring import Breakdown, score_all, score_vertex
from catan_advisor.scoring.ports import generic_port_value, specific_port_value
from catan_advisor.geometry import GEOMETRY as G


@pytest.fixture(scope="module")
def board():
    return random_board(seed=7)


@pytest.fixture(scope="module")
def cfg():
    return load_config()


# --- the breakdown contract ------------------------------------------------


def test_total_is_the_sum_of_the_parts(board, cfg):
    for v in G.vertex_ids:
        s = score_vertex(board, v, cfg)
        assert s.score == pytest.approx(sum(c.value for c in s.breakdown.contributions))


def test_zero_valued_terms_are_dropped_but_notes_are_kept():
    bd = Breakdown("v01")
    bd.add("a", "vale qualcosa", 1.5)
    bd.add("b", "vale zero", 0.0)
    bd.note("c", "solo informativo")
    assert [c.key for c in bd.contributions] == ["a", "c"]
    assert bd.total == pytest.approx(1.5)


def test_breakdown_lookups(board, cfg):
    s = score_vertex(board, "v26", cfg)
    assert s.breakdown.has("production")
    assert s.breakdown.get("production") > 0
    assert not s.breakdown.has("nonesistente")
    assert s.breakdown.get("nonesistente") == 0


def test_by_magnitude_is_sorted_by_absolute_value(board, cfg):
    s = score_vertex(board, "v26", cfg)
    values = [abs(c.value) for c in s.breakdown.by_magnitude()]
    assert values == sorted(values, reverse=True)


# --- production ------------------------------------------------------------


def test_production_term_is_pips_times_weight(board, cfg):
    weights = cfg.resource_weights(board.pips_by_resource, board.n_players)
    for v in ("v23", "v26", "v01"):
        s = score_vertex(board, v, cfg)
        expected = sum(p * weights[r] for r, p in s.production.items())
        assert s.breakdown.get("production") == pytest.approx(expected)
        assert s.weighted_pips == pytest.approx(expected)


def test_raw_pips_travel_with_the_score(board, cfg):
    for v in G.vertex_ids:
        s = score_vertex(board, v, cfg)
        assert s.pips == board.vertex_pips(v)
        assert s.cards_per_roll == pytest.approx(s.pips / 36)
        assert s.cards_per_round == pytest.approx(s.pips / 36 * board.n_players)


def test_desert_produces_nothing_but_is_mentioned(board, cfg):
    desert = next(h.id for h in board.hexes.values() if h.is_desert)
    v = G.hex_vertices[desert][0]
    s = score_vertex(board, v, cfg)
    assert s.breakdown.has("production_desert")
    assert s.breakdown.get("production_desert") == 0


# --- diversity -------------------------------------------------------------


def test_diversity_is_per_distinct_resource(board, cfg):
    per = cfg.get("vertex.diversity_per_resource")
    for v in G.vertex_ids:
        s = score_vertex(board, v, cfg)
        assert s.breakdown.get("diversity") == pytest.approx(len(s.resources) * per)


def test_diversity_can_be_switched_off_for_the_pair_evaluation(board, cfg):
    with_it = score_vertex(board, "v26", cfg, include_diversity=True)
    without = score_vertex(board, "v26", cfg, include_diversity=False)
    assert not without.breakdown.has("diversity")
    assert with_it.score > without.score


# --- numbers ---------------------------------------------------------------


def test_three_distinct_numbers_earn_the_bonus(board, cfg):
    v = next(v for v in G.vertex_ids if len(set(board.vertex_numbers(v))) == 3)
    assert score_vertex(board, v, cfg).breakdown.has("distinct_numbers")


def test_repeated_number_is_penalised(board, cfg):
    candidates = [
        v
        for v in G.vertex_ids
        if len(board.vertex_numbers(v)) > len(set(board.vertex_numbers(v)))
    ]
    v = candidates[0]
    s = score_vertex(board, v, cfg)
    assert s.breakdown.get("repeated_number") < 0
    assert not s.breakdown.has("distinct_numbers")


def test_mid_band_and_extremes_are_mutually_exclusive(board, cfg):
    for v in G.vertex_ids:
        bd = score_vertex(board, v, cfg).breakdown
        assert not (bd.has("mid_band") and bd.has("extremes_only"))


def test_only_extreme_numbers_is_penalised(board, cfg):
    for v in G.vertex_ids:
        numbers = board.vertex_numbers(v)
        if numbers and all(n in K.EXTREME_NUMBERS for n in numbers):
            assert score_vertex(board, v, cfg).breakdown.get("extremes_only") < 0


# --- expansion: the geometric correction to B.3 ----------------------------


def test_expansion_never_counts_an_adjacent_junction(board, cfg):
    """A junction one edge away is banned by the distance rule, forever."""
    for v in ("v26", "v23", "v01", "v54"):
        s = score_vertex(board, v, cfg)
        neighbours = set(G.vertex_neighbours[v])
        assert not any(t in neighbours for t, _, _ in s.expansion_targets)
        assert all(distance in (2, 3) for _, distance, _ in s.expansion_targets)


def test_expansion_cap_binds_only_for_a_minority_of_junctions(cfg):
    """Regression on the calibration: the KB coefficients put 76% of junctions
    at the cap, which turned a continuous term back into a step function."""
    cap = cfg.get("vertex.expansion_near_cap")
    at_cap = total = 0
    for seed in range(6):
        b = random_board(seed=seed)
        for v in b.geometry.vertex_ids:
            value = score_vertex(b, v, cfg).breakdown.get("expansion_near")
            total += 1
            if value >= cap - 1e-9:
                at_cap += 1
    assert at_cap / total < 0.25


def test_blocked_surroundings_produce_a_dead_end_penalty(cfg):
    board = random_board(seed=7)
    target = "v01"
    for candidate in list(G.vertices_within(target, roads=2)):
        if G.vertices_within(target, roads=2)[candidate] == 2 and board.is_legal(candidate):
            board = board.with_placement(Placement(player=9, vertex=candidate))
    s = score_vertex(board, target, cfg)
    assert s.breakdown.get("dead_end") < 0
    assert not s.breakdown.has("expansion_near")


def test_three_players_boosts_expansion(cfg):
    """The multiplier scales the cap too, otherwise it would vanish exactly on
    the junctions with the most expansion room."""
    four = random_board(seed=7, n_players=4)
    three = random_board(seed=7, n_players=3)
    multiplier = cfg.get("vertex.expansion_multiplier_3p")
    for v in ("v23", "v26", "v13"):
        a = score_vertex(four, v, cfg).breakdown.get("expansion_near")
        b = score_vertex(three, v, cfg).breakdown.get("expansion_near")
        assert b == pytest.approx(a * multiplier)


# --- ports -----------------------------------------------------------------


def test_specific_port_value_grows_with_production(cfg):
    values = [specific_port_value(cfg, p) for p in (0, 2, 3, 5, 8, 12)]
    assert values == sorted(values)
    assert values[0] == 0.0
    assert values[-1] == values[-2]      # saturates at the top bracket


def test_generic_port_bonuses_need_a_known_portfolio(cfg):
    base = generic_port_value(cfg)
    assert generic_port_value(cfg, total_pips=22) > base
    assert generic_port_value(cfg, max_resource_pips=9) > base


def test_port_is_valued_as_an_option_at_the_first_pick(board, cfg):
    port_vertices = [v for v in G.vertex_ids if board.vertex_port(v)]
    scored = [score_vertex(board, v, cfg) for v in port_vertices]
    assert any(s.breakdown.has("port_option") for s in scored)
    assert any(s.breakdown.has("port_generic") for s in scored)
    for s in scored:
        assert s.breakdown.get("port_option") + s.breakdown.get("port_generic") > 0


def test_a_junction_without_a_port_has_no_port_term(board, cfg):
    v = next(v for v in G.vertex_ids if board.vertex_port(v) is None)
    bd = score_vertex(board, v, cfg).breakdown
    assert not bd.has("port_option")
    assert not bd.has("port_generic")


# --- robber ----------------------------------------------------------------


def _high_pips(board, vertex):
    return sum(h.pips for h in board.vertex_hexes(vertex) if h.number in K.HIGH_NUMBERS)


def test_balanced_setup_makes_the_robber_threshold_unreachable(cfg):
    """The three tiles of a junction are mutually adjacent, and the official
    setup forbids 6 and 8 from touching. So at most one of them is a 6 or an 8,
    capping a junction at 5 pips on high numbers -- the KB threshold of 10 can
    never fire on a balanced board."""
    for seed in range(8):
        board = random_board(seed=seed, balanced=True)
        assert max(_high_pips(board, v) for v in G.vertex_ids) <= 5


def _blocked_around(board, target):
    for candidate, distance in G.vertices_within(target, roads=2).items():
        if distance == 2 and board.is_legal(candidate):
            board = board.with_placement(Placement(player=9, vertex=candidate))
    return board


def test_robber_penalty_needs_both_high_numbers_and_no_escape(cfg):
    threshold = cfg.get("vertex.robber_pip_threshold")
    board = target = None
    for seed in range(40):
        candidate_board = random_board(seed=seed, balanced=False)
        loaded = [v for v in G.vertex_ids if _high_pips(candidate_board, v) >= threshold]
        if loaded:
            board, target = candidate_board, loaded[0]
            break
    assert target, "serve un tabellone non bilanciato con 6 e 8 adiacenti"

    # An open board is not a trap, however loaded the junction is.
    assert not score_vertex(board, target, cfg).breakdown.has("robber_target")
    assert score_vertex(_blocked_around(board, target), target, cfg).breakdown.get(
        "robber_target"
    ) < 0


# --- score_all -------------------------------------------------------------


def test_score_all_is_sorted_and_legal_only(cfg):
    board = random_board(seed=7).with_placement(Placement(player=2, vertex="v26"))
    scores = score_all(board, cfg)
    assert [s.score for s in scores] == sorted((s.score for s in scores), reverse=True)
    assert all(s.legal for s in scores)
    assert "v26" not in {s.vertex for s in scores}
    assert len(scores) == len(board.legal_vertices)


def test_score_all_can_include_occupied_junctions(cfg):
    board = random_board(seed=7).with_placement(Placement(player=2, vertex="v26"))
    scores = score_all(board, cfg, legal_only=False)
    assert len(scores) == 54
    assert any(not s.legal for s in scores)
