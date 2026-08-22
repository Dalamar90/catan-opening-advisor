"""Pre-computation of KB B.6 and the scarcity weighting of KB B.2."""

import pytest

from catan_advisor import constants as K
from catan_advisor.boardio import random_board
from catan_advisor.config import load_config
from catan_advisor.precompute import precompute
from catan_advisor.report import render_precompute


@pytest.fixture(scope="module")
def pre():
    return precompute(random_board(seed=7))


def test_expected_quotas_sum_to_one():
    assert sum(K.EXPECTED_QUOTA.values()) == pytest.approx(1.0)


def test_every_vertex_is_summarised(pre):
    assert len(pre.vertices) == 54
    assert {v.vertex for v in pre.vertices} == set(pre.board.geometry.vertex_ids)


def test_scarcity_quotas_sum_to_one(pre):
    assert sum(row["quota"] for row in pre.scarcity.values()) == pytest.approx(1.0)
    assert sum(int(row["pips"]) for row in pre.scarcity.values()) == 58


def test_scarce_resource_gets_a_higher_weight_than_abundant_one():
    cfg = load_config()
    # Same base weight for both, so only scarcity can separate them.
    pips = {K.WOOD: 4, K.BRICK: 20, K.WHEAT: 12, K.SHEEP: 12, K.ORE: 10}
    weights = cfg.resource_weights(pips)
    assert weights[K.WOOD] > cfg["resource_weights"][K.WOOD]
    assert weights[K.BRICK] < cfg["resource_weights"][K.BRICK]


def test_scarcity_multiplier_is_clamped():
    cfg = load_config()
    lo = cfg.get("scarcity.min_multiplier")
    hi = cfg.get("scarcity.max_multiplier")
    pips = {K.WOOD: 0, K.BRICK: 1, K.WHEAT: 1, K.SHEEP: 55, K.ORE: 1}
    weights = cfg.resource_weights(pips)
    for resource, weight in weights.items():
        base = cfg["resource_weights"][resource]
        assert base * lo - 1e-9 <= weight <= base * hi + 1e-9


def test_three_players_raises_wood_and_brick():
    cfg = load_config()
    four = cfg.resource_weights(None, n_players=4)
    three = cfg.resource_weights(None, n_players=3)
    assert three[K.WOOD] == pytest.approx(four[K.WOOD] + 0.1)
    assert three[K.BRICK] == pytest.approx(four[K.BRICK] + 0.1)
    assert three[K.WHEAT] == four[K.WHEAT]


def test_top_list_is_sorted_and_legal(pre):
    top = pre.top(10)
    assert len(top) == 10
    assert [v.pips for v in top] == sorted((v.pips for v in top), reverse=True)
    assert all(v.legal for v in top)


def test_weighted_pips_are_consistent_with_production(pre):
    for s in pre.vertices:
        expected = sum(p * pre.weights[r] for r, p in s.production.items())
        assert s.weighted_pips == pytest.approx(expected)
        assert sum(s.production.values()) == s.pips


def test_cards_per_round_conversion(pre):
    s = pre.top(1)[0]
    assert s.cards_per_round(4) == pytest.approx(s.pips / 36 * 4)


def test_hot_zones_do_not_fully_overlap(pre):
    assert 1 <= len(pre.hot_zones) <= 3
    for i, a in enumerate(pre.hot_zones):
        for b in pre.hot_zones[i + 1 :]:
            assert len(set(a.hexes) & set(b.hexes)) <= 2


def test_port_map_covers_every_port(pre):
    assert len(pre.ports) == len(pre.board.ports) == 9
    for info in pre.ports:
        assert info.served_pips >= 0
        assert len(info.vertices) == 2


def test_concentration_index_is_bounded(pre):
    for resource, value in pre.concentration.items():
        assert -1.0 <= value <= 1.0


def test_clustered_resource_scores_higher_than_spread_one():
    """Three ore tiles side by side must beat three ore tiles far apart."""
    from catan_advisor.board import Board, Hex
    from catan_advisor.geometry import GEOMETRY as G
    from catan_advisor.precompute import _concentration

    def board_with_ore_at(ore_hexes):
        others = [h for h in G.hex_ids if h not in ore_hexes]
        hexes = {h: Hex(h, K.ORE, 6) for h in ore_hexes}
        hexes.update({h: Hex(h, K.WOOD, 6) for h in others})
        return Board(hexes=hexes)

    clustered = _concentration(board_with_ore_at(["h09", "h10", "h11"]))
    spread = _concentration(board_with_ore_at(["h01", "h17", "h19"]))
    assert clustered[K.ORE] > 0 > spread[K.ORE]


def test_strong_vertex_count_matches_threshold(pre):
    manual = sum(1 for v in pre.vertices if v.legal and v.pips >= pre.strong_threshold)
    assert pre.strong_vertex_count == manual


def test_report_renders_and_mentions_the_key_facts(pre):
    text = render_precompute(pre)
    assert "pip totali 58" in text
    assert "tessere 19" in text
    assert "incroci 54" in text
    assert "lati 72" in text
    for label in ("legno", "mattone", "grano", "pecora", "minerale"):
        assert label in text
    assert "carte/giro" in text
