"""The advice objects and the D.3 output (M5)."""

import pytest

from catan_advisor import constants as K
from catan_advisor.advisor import advise
from catan_advisor.board import Placement
from catan_advisor.boardio import random_board
from catan_advisor.config import load_config
from catan_advisor.explain import render_advice
from catan_advisor.geometry import GEOMETRY as G
from catan_advisor.scoring.draft import snake_order


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture
def first_pick_board():
    board = random_board(seed=7)
    board.my_position = 1
    return board


@pytest.fixture
def second_pick_board():
    """Six settlements down: it is P2's turn again, at pick #7."""
    board = random_board(seed=7)
    for pick, player in enumerate(snake_order(4)[:6], start=1):
        choice = max(board.legal_vertices, key=lambda v: (board.vertex_pips(v), v))
        board = board.with_placement(Placement(player, choice, order=pick))
    board.my_position = 2
    return board


# --- structure of the advice -----------------------------------------------


def test_at_least_three_options_as_the_kb_demands(first_pick_board, cfg):
    advice = advise(first_pick_board, cfg, samples=6)
    assert len(advice.recommendations) >= 3
    assert [r.rank for r in advice.recommendations] == [1, 2, 3]


def test_every_option_carries_a_plan_a_road_and_an_archetype(first_pick_board, cfg):
    advice = advise(first_pick_board, cfg, samples=6)
    for rec in advice.recommendations:
        assert rec.reasons, "una raccomandazione senza motivazioni e inutile"
        assert rec.road is not None
        assert rec.partner and rec.partner != rec.vertex
        assert rec.archetype
        assert 0 < rec.plan_probability <= 1


def test_first_pick_options_carry_a_fallback(first_pick_board, cfg):
    advice = advise(first_pick_board, cfg, samples=12)
    assert any(rec.fallbacks for rec in advice.recommendations)


def test_recommended_vertices_are_legal_and_distinct(first_pick_board, cfg):
    advice = advise(first_pick_board, cfg, samples=6)
    seen = [rec.vertex for rec in advice.recommendations]
    assert len(seen) == len(set(seen))
    for vertex in seen:
        assert first_pick_board.is_legal(vertex)


# --- reasons and risks come from the breakdown -----------------------------


def test_reasons_quote_real_contributions(first_pick_board, cfg):
    """Every bullet must correspond to a term that actually moved the score."""
    advice = advise(first_pick_board, cfg, samples=6)
    rec = advice.recommendations[0]
    labels = {c.label for c in rec.pair.breakdown.contributions if c.value > 0}
    quoted = [r for r in rec.reasons if any(label in r for label in labels)]
    assert quoted, "nessuna motivazione risale a un contributo del breakdown"


def test_risks_report_hard_violations(cfg):
    """A pair that breaks a hard constraint must say so in the risks."""
    board = random_board(seed=7)
    board.my_position = 1
    advice = advise(board, cfg, samples=6)
    offenders = [r for r in advice.recommendations if r.pair.violations]
    for rec in offenders:
        assert any("VINCOLO HARD" in risk for risk in rec.risks)


def test_missing_resources_are_named_as_a_risk(first_pick_board, cfg):
    advice = advise(first_pick_board, cfg, samples=6)
    for rec in advice.recommendations:
        missing = [r for r, p in rec.pair.production.items() if p == 0]
        if missing:
            assert any("non produce" in risk for risk in rec.risks)


def test_a_fragile_plan_is_flagged(first_pick_board, cfg):
    advice = advise(first_pick_board, cfg, samples=12)
    fragile = [r for r in advice.recommendations if r.plan_probability < 0.6]
    for rec in fragile:
        assert any("fallback" in risk for risk in rec.risks)


# --- second pick ------------------------------------------------------------


def test_second_pick_pairs_with_my_existing_settlement(second_pick_board, cfg):
    advice = advise(second_pick_board, cfg)
    assert not advice.is_first_pick
    assert advice.existing
    mine = advice.existing[0]
    for rec in advice.recommendations:
        assert rec.partner == mine
        assert rec.plan_probability == 1.0
        assert rec.vertex != mine


def test_second_pick_reads_the_market(second_pick_board, cfg):
    advice = advise(second_pick_board, cfg)
    assert advice.profiles
    assert advice.recommendations[0].pair.market.profiles


def test_nothing_to_advise_once_both_are_placed(cfg):
    board = random_board(seed=7)
    for pick, player in enumerate(snake_order(4), start=1):
        choice = max(board.legal_vertices, key=lambda v: (board.vertex_pips(v), v))
        board = board.with_placement(Placement(player, choice, order=pick))
    board.my_position = 3
    advice = advise(board, cfg)
    assert advice.recommendations == []
    assert "entrambe le colonie" in render_advice(advice)


# --- the D.3 rendering ------------------------------------------------------


@pytest.mark.parametrize("fixture", ["first_pick_board", "second_pick_board"])
def test_output_has_every_section_of_d3(fixture, cfg, request):
    board = request.getfixturevalue(fixture)
    text = render_advice(advise(board, cfg, samples=6))
    for section in (
        "RACCOMANDAZIONE #1",
        "PERCHE:",
        "RISCHI:",
        "STRADA CONSIGLIATA:",
        "PIANO DI COPPIA:",
        "ARCHETIPO ABILITATO:",
    ):
        assert section in text, f"manca la sezione {section}"
    assert "RACCOMANDAZIONE #3" in text


def test_output_always_shows_raw_pips_next_to_the_score(first_pick_board, cfg):
    text = render_advice(advise(first_pick_board, cfg, samples=6))
    assert "Pip:" in text
    assert "carte/giro" in text
    assert "pip-equivalenti" in text


def test_output_warns_when_no_opponent_is_known(first_pick_board, cfg):
    text = render_advice(advise(first_pick_board, cfg, samples=6))
    assert "Nessun piazzamento avversario" in text


def test_output_lists_opponents_when_they_exist(second_pick_board, cfg):
    text = render_advice(advise(second_pick_board, cfg))
    assert "AVVERSARI GIA PIAZZATI" in text
    assert "non produce" in text
