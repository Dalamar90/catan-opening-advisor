"""S(A,B): the pair evaluation (M3, KB B.4 with the E.2 magnitudes)."""

import pytest

from catan_advisor import constants as K
from catan_advisor.board import Board, Hex, Placement, Port
from catan_advisor.boardio import random_board
from catan_advisor.config import load_config
from catan_advisor.geometry import GEOMETRY as G
from catan_advisor.scoring import best_pairs, legal_pairs, score_pair, score_vertex


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def board():
    return random_board(seed=7)


# --- a controllable board ---------------------------------------------------


def _two_independent_vertices() -> tuple[str, str]:
    """Two three-tile junctions that are neither adjacent nor tile-sharing."""
    inner = [v for v in G.vertex_ids if len(G.vertex_hexes[v]) == 3]
    for a in inner:
        for b in inner:
            if a < b and b not in G.vertex_neighbours[a]:
                if not set(G.vertex_hexes[a]) & set(G.vertex_hexes[b]):
                    return a, b
    raise AssertionError("il tabellone deve avere due incroci indipendenti")


def _make_board(assignments: dict[str, list[tuple[str, int]]], n_players: int = 4) -> Board:
    """Board built tile by tile, bypassing validation, so a test can state
    exactly what a pair produces."""
    hexes = {h: Hex(h, K.DESERT, None) for h in G.hex_ids}
    for vertex, tiles in assignments.items():
        for hex_id, (resource, number) in zip(G.vertex_hexes[vertex], tiles):
            hexes[hex_id] = Hex(hex_id, resource, number)
    return Board(hexes=hexes, n_players=n_players)


A, B = _two_independent_vertices()


def _coverage_of(production_a, production_b, n_players=4):
    board = _make_board({A: production_a, B: production_b}, n_players=n_players)
    return score_pair(board, A, B)


def _coastal_pair() -> tuple[str, str, str]:
    """A coastal junction that can hold a port, plus an independent partner."""
    coastal_edges = set(G.coastal_edges)
    inner = [v for v in G.vertex_ids if len(G.vertex_hexes[v]) == 3]
    for c in G.coastal_vertices:
        if len(G.vertex_hexes[c]) != 2:
            continue
        for d in inner:
            if d in G.vertex_neighbours[c]:
                continue
            if set(G.vertex_hexes[c]) & set(G.vertex_hexes[d]):
                continue
            edge = next(e for e in G.vertex_edges[c] if e in coastal_edges)
            return c, d, edge
    raise AssertionError("serve un incrocio costiero indipendente")


C, D, PORT_EDGE = _coastal_pair()


def _with_port(tiles_c, tiles_d, port: Port):
    board = _make_board({C: tiles_c, D: tiles_d})
    board = Board(hexes=board.hexes, ports=(port,), n_players=4)
    return score_pair(board, C, D)


# --- the contract -----------------------------------------------------------


def test_total_is_the_sum_of_the_parts(board, cfg):
    for a, b in legal_pairs(board)[:60]:
        pair = score_pair(board, a, b, cfg)
        assert pair.score == pytest.approx(
            sum(c.value for c in pair.breakdown.contributions)
        )


def test_production_is_the_sum_of_the_members(board, cfg):
    pair = score_pair(board, "v18", "v26", cfg)
    for resource in K.RESOURCES:
        expected = board.vertex_production("v18").get(resource, 0) + board.vertex_production(
            "v26"
        ).get(resource, 0)
        assert pair.production[resource] == expected
    assert pair.pips == board.vertex_pips("v18") + board.vertex_pips("v26")


def test_portfolio_terms_are_not_counted_inside_the_members(board, cfg):
    """Variety, ports, expansion and robber exposure belong to the pair. If the
    members carried them too, every one of them would be counted twice."""
    pair = score_pair(board, "v18", "v26", cfg)
    member_keys = {
        c.key for c in pair.breakdown.contributions if c.key.startswith(("v18.", "v26."))
    }
    for forbidden in ("diversity", "expansion_near", "expansion_far", "port_option",
                      "port_generic", "robber_target", "dead_end"):
        assert not any(k.endswith(forbidden) for k in member_keys)


# --- coverage, the headline term -------------------------------------------


def test_full_coverage_is_worth_eight_pips_over_the_baseline(cfg):
    """KB E.2: each distinct resource is worth 4 production points, counted
    against a 3-of-5 baseline. So 5/5 is +8 and 3/5 is the zero point."""
    five = _coverage_of(
        [(K.WOOD, 6), (K.BRICK, 8), (K.WHEAT, 5)],
        [(K.SHEEP, 9), (K.ORE, 5), (K.WHEAT, 10)],
    )
    assert five.resources_covered == 5
    assert five.breakdown.get("coverage") == pytest.approx(8.0)

    three = _coverage_of(
        [(K.WOOD, 6), (K.BRICK, 8), (K.WHEAT, 5)],
        [(K.WOOD, 9), (K.BRICK, 4), (K.WHEAT, 10)],
    )
    assert three.resources_covered == 3
    assert three.breakdown.get("coverage") == pytest.approx(0.0)


def test_two_resources_are_worth_minus_four(cfg):
    two = _coverage_of(
        [(K.WOOD, 6), (K.WOOD, 8), (K.WHEAT, 5)],
        [(K.WOOD, 9), (K.WHEAT, 4), (K.WHEAT, 10)],
    )
    assert two.resources_covered == 2
    assert two.breakdown.get("coverage") == pytest.approx(-4.0)


def test_coverage_credit_ramps_with_production(cfg):
    """A resource 'covered' by a lone 12 is not covered in any useful sense.
    KB B.4 taken literally would pay the full +4 for it."""
    token = _coverage_of(
        [(K.WOOD, 6), (K.BRICK, 8), (K.WHEAT, 5)],
        [(K.SHEEP, 12), (K.ORE, 4), (K.WHEAT, 10)],   # sheep on a 12 = 1 pip
    )
    real = _coverage_of(
        [(K.WOOD, 6), (K.BRICK, 8), (K.WHEAT, 5)],
        [(K.SHEEP, 5), (K.ORE, 9), (K.WHEAT, 10)],    # sheep on a 5 = 4 pips
    )
    assert token.resources_covered == real.resources_covered == 5
    assert token.breakdown.get("coverage") < real.breakdown.get("coverage")
    assert real.breakdown.get("coverage") == pytest.approx(8.0)


def test_three_players_raise_the_value_of_full_coverage(cfg):
    tiles_a = [(K.WOOD, 6), (K.BRICK, 8), (K.WHEAT, 5)]
    tiles_b = [(K.SHEEP, 9), (K.ORE, 4), (K.WHEAT, 10)]
    four = _coverage_of(tiles_a, tiles_b, n_players=4)
    three = _coverage_of(tiles_a, tiles_b, n_players=3)
    multiplier = cfg.get("pair.coverage.bonus_3p_multiplier")
    assert three.breakdown.get("coverage") == pytest.approx(
        four.breakdown.get("coverage") * multiplier
    )


def test_a_two_to_one_port_on_a_surplus_partly_covers_the_gap(cfg):
    tiles_c = [(K.ORE, 6), (K.ORE, 8)]                    # coastal: 10 pips of ore
    tiles_d = [(K.WOOD, 5), (K.BRICK, 9), (K.WHEAT, 5)]   # no sheep anywhere
    plain = _make_board({C: tiles_c, D: tiles_d})
    plain_score = score_pair(plain, C, D)
    with_port = _with_port(tiles_c, tiles_d, Port(PORT_EDGE, 2, K.ORE))
    assert plain_score.resources_covered == 4
    assert with_port.breakdown.get("coverage") > plain_score.breakdown.get("coverage")


def test_the_kb_headline_claim_holds(cfg):
    """KB E.2: a 5/5 pair at 19 pips beats a 3/5 pair at 23."""
    five = _coverage_of(
        [(K.WOOD, 5), (K.BRICK, 9), (K.WHEAT, 5)],       # 4+4+4 = 12
        [(K.SHEEP, 6), (K.ORE, 10), (K.WHEAT, 3)],       # 5+3+2 = 10
    )
    three = _coverage_of(
        [(K.WOOD, 6), (K.BRICK, 8), (K.WHEAT, 6)],       # 5+5+5 = 15
        [(K.WOOD, 8), (K.BRICK, 5), (K.WHEAT, 9)],       # 5+4+4 = 13
    )
    assert five.pips < three.pips
    assert five.score > three.score


# --- engines and spread -----------------------------------------------------


def test_city_engine_needs_both_ore_and_wheat(cfg):
    yes = _coverage_of(
        [(K.ORE, 6), (K.WHEAT, 8), (K.WOOD, 5)],
        [(K.SHEEP, 9), (K.BRICK, 4), (K.WHEAT, 10)],
    )
    assert yes.breakdown.has("city_engine")
    no = _coverage_of(
        [(K.ORE, 12), (K.WHEAT, 8), (K.WOOD, 5)],
        [(K.SHEEP, 9), (K.BRICK, 4), (K.WHEAT, 10)],
    )
    assert not no.breakdown.has("city_engine")


def test_wood_brick_balance_needs_both(cfg):
    balanced = _coverage_of(
        [(K.WOOD, 6), (K.BRICK, 8), (K.WHEAT, 5)],
        [(K.SHEEP, 9), (K.ORE, 4), (K.WHEAT, 10)],
    )
    assert balanced.breakdown.has("wood_brick_balance")
    lopsided = _coverage_of(
        [(K.WOOD, 6), (K.BRICK, 12), (K.WHEAT, 5)],
        [(K.SHEEP, 9), (K.ORE, 4), (K.WHEAT, 10)],
    )
    assert not lopsided.breakdown.has("wood_brick_balance")


def test_few_distinct_numbers_is_penalised(cfg):
    lottery = _coverage_of(
        [(K.WOOD, 6), (K.BRICK, 6), (K.WHEAT, 8)],
        [(K.SHEEP, 8), (K.ORE, 6), (K.WHEAT, 8)],
    )
    assert lottery.breakdown.get("number_concentration") < 0
    assert not lottery.breakdown.has("number_diversity")


def test_high_numbers_concentration_is_penalised(cfg):
    """Anti-pattern 4 of D.5, which cannot fire on a single junction."""
    loaded = _coverage_of(
        [(K.WOOD, 6), (K.BRICK, 8), (K.WHEAT, 2)],
        [(K.SHEEP, 6), (K.ORE, 8), (K.WHEAT, 12)],
    )
    assert loaded.breakdown.get("high_number_concentration") < 0


def test_distinct_tiles_reward_spreading_out(board, cfg):
    """KB E.6. Two settlements sharing tiles double the variance instead of
    diversifying it, and the robber takes a bigger bite."""
    shared = None
    spread = None
    for a, b in legal_pairs(board):
        tiles = len(set(G.vertex_hexes[a]) | set(G.vertex_hexes[b]))
        if tiles == 6 and spread is None:
            spread = score_pair(board, a, b, cfg)
        if tiles <= 4 and shared is None:
            shared = score_pair(board, a, b, cfg)
    assert shared and spread
    assert shared.breakdown.get("distinct_tiles") < spread.breakdown.get("distinct_tiles")


# --- expansion counted once -------------------------------------------------


def test_shared_expansion_targets_are_not_counted_twice(board, cfg):
    pair = score_pair(board, "v18", "v26", cfg)
    targets = [t.vertex for t in pair.expansion_targets]
    assert len(targets) == len(set(targets))
    assert pair.a not in targets and pair.b not in targets


def test_expansion_excludes_junctions_blocked_by_our_own_settlements(board, cfg):
    pair = score_pair(board, "v18", "v26", cfg)
    banned = set(G.vertex_neighbours["v18"]) | set(G.vertex_neighbours["v26"])
    assert not any(t.vertex in banned for t in pair.expansion_targets)


# --- hard constraints and warnings -----------------------------------------


def test_violations_are_flagged_and_penalised_but_never_excluded(cfg):
    starved = _coverage_of(
        [(K.SHEEP, 6), (K.SHEEP, 8), (K.ORE, 5)],
        [(K.SHEEP, 9), (K.ORE, 4), (K.ORE, 10)],
    )
    assert starved.violations
    assert any("grano" in v for v in starved.violations)
    assert any("legno" in v for v in starved.violations)
    assert starved.breakdown.get("hard_constraints") < 0
    # still a scored candidate, because at pick 8 there may be nothing better
    assert isinstance(starved.score, float)


def test_verdict_follows_the_kb_benchmark(cfg):
    strong = _coverage_of(
        [(K.WOOD, 6), (K.BRICK, 8), (K.WHEAT, 5)],
        [(K.SHEEP, 6), (K.ORE, 8), (K.WHEAT, 5)],
    )
    assert strong.pips >= 22
    assert strong.verdict() == "apertura da vincitore"
    weak = _coverage_of(
        [(K.WOOD, 2), (K.BRICK, 12), (K.WHEAT, 3)],
        [(K.SHEEP, 11), (K.ORE, 2), (K.WHEAT, 12)],
    )
    assert weak.verdict().startswith("apertura persa")


def test_anti_patterns_are_reported(cfg):
    sheepy = _coverage_of(
        [(K.SHEEP, 6), (K.SHEEP, 8), (K.WHEAT, 5)],
        [(K.WOOD, 9), (K.BRICK, 4), (K.ORE, 10)],
    )
    assert any("D.5.9" in w for w in sheepy.warnings)

    no_brick = _coverage_of(
        [(K.WOOD, 6), (K.ORE, 8), (K.WHEAT, 5)],
        [(K.SHEEP, 9), (K.ORE, 4), (K.WHEAT, 10)],
    )
    assert any("D.5.3" in w for w in no_brick.warnings)


def test_port_without_production_is_an_anti_pattern(cfg):
    pair = _with_port(
        [(K.WOOD, 6), (K.BRICK, 8)],
        [(K.SHEEP, 9), (K.WHEAT, 5), (K.WHEAT, 10)],
        Port(PORT_EDGE, 2, K.ORE),                        # zero ore produced
    )
    assert any("D.5.1" in w for w in pair.warnings)


def test_a_fed_port_is_valued_with_the_real_portfolio(cfg):
    """At the pair stage the portfolio is known, so the port is priced on real
    production instead of the option value used at the first pick."""
    pair = _with_port(
        [(K.ORE, 6), (K.ORE, 8)],
        [(K.WOOD, 5), (K.BRICK, 9), (K.WHEAT, 5)],
        Port(PORT_EDGE, 2, K.ORE),
    )
    assert pair.breakdown.get("port_specific") > 0
    assert not pair.breakdown.has("port_option")


# --- enumeration ------------------------------------------------------------


def test_legal_pairs_excludes_adjacent_junctions(board):
    pairs = legal_pairs(board)
    assert len(pairs) == 54 * 53 // 2 - len(G.edge_ids)
    for a, b in pairs:
        assert b not in G.vertex_neighbours[a]


def test_legal_pairs_respects_existing_placements(board):
    occupied = board.with_placement(Placement(player=2, vertex="v26"))
    for a, b in legal_pairs(occupied):
        assert "v26" not in (a, b)
        assert a not in G.vertex_neighbours["v26"]
        assert b not in G.vertex_neighbours["v26"]


def test_best_pairs_is_sorted(board, cfg):
    pairs = best_pairs(board, cfg, limit=50)
    assert [p.score for p in pairs] == sorted((p.score for p in pairs), reverse=True)


def test_best_pairs_can_fix_the_first_settlement(board, cfg):
    pairs = best_pairs(board, cfg, first="v23", limit=20)
    assert pairs
    for p in pairs:
        assert "v23" in (p.a, p.b)
