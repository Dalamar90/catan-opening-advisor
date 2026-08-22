"""Board model: pips, production, and the validation that catches misreadings."""

import pytest

from catan_advisor import constants as K
from catan_advisor.board import Board, BoardError, Placement
from catan_advisor.boardio import board_from_dict, board_to_dict, random_board
from catan_advisor.geometry import GEOMETRY as G


# --- Part A facts ----------------------------------------------------------


def test_number_tokens_sum_to_58_pips():
    assert sum(K.PIPS[n] for n in K.NUMBER_TOKENS) == K.TOTAL_PIPS == 58


def test_tile_counts_add_up_to_19():
    assert sum(K.TILE_COUNTS.values()) == K.N_HEXES == 19
    assert len(K.NUMBER_TOKENS) == K.N_PRODUCTIVE_HEXES == 18


def test_pip_table_matches_two_dice():
    assert sum(K.PIPS.values()) == 36
    assert K.PIPS[7] == 6


@pytest.mark.parametrize(
    "position,n_players,expected,k",
    [
        (1, 4, (1, 8), 6),
        (2, 4, (2, 7), 4),
        (3, 4, (3, 6), 2),
        (4, 4, (4, 5), 0),
        (1, 3, (1, 6), 4),
        (2, 3, (2, 5), 2),
        (3, 3, (3, 4), 0),
    ],
)
def test_snake_draft_matches_kb_table(position, n_players, expected, k):
    assert K.pick_numbers(position, n_players) == expected
    assert K.waiting_picks(position, n_players) == k


# --- generated boards ------------------------------------------------------


@pytest.mark.parametrize("seed", [0, 1, 7, 42, 123])
def test_random_boards_are_legal(seed):
    board = random_board(seed=seed)
    assert board.validate(strict=False) == []
    assert board.total_pips == 58
    assert len(board.hexes) == 19
    assert len(board.ports) == 9


def test_random_board_is_reproducible():
    a, b = random_board(seed=99), random_board(seed=99)
    assert board_to_dict(a) == board_to_dict(b)


def test_balanced_board_has_no_touching_six_or_eight():
    board = random_board(seed=5, balanced=True)
    assert board.warnings() == []


def test_pips_by_resource_sum_to_total():
    board = random_board(seed=3)
    assert sum(board.pips_by_resource.values()) == board.total_pips


def test_json_roundtrip():
    board = random_board(seed=11)
    restored = board_from_dict(board_to_dict(board))
    assert board_to_dict(restored) == board_to_dict(board)


def test_italian_resource_names_are_accepted():
    board = random_board(seed=2)
    data = board_to_dict(board)
    for hexdata in data["hexes"]:
        hexdata["resource"] = K.RESOURCE_LABEL_IT[hexdata["resource"]]
    assert board_from_dict(data).pips_by_resource == board.pips_by_resource


# --- production ------------------------------------------------------------


def _handmade_board() -> Board:
    """A board we control, so the production numbers are checkable by hand."""
    board = random_board(seed=1)
    return board


def test_vertex_pips_equal_sum_of_its_tiles():
    board = _handmade_board()
    for v in G.vertex_ids:
        expected = sum(board.hexes[h].pips for h in G.vertex_hexes[v])
        assert board.vertex_pips(v) == expected
        assert sum(board.vertex_production(v).values()) == expected


def test_no_vertex_touches_more_than_three_tiles():
    board = _handmade_board()
    assert max(len(board.vertex_hexes(v)) for v in G.vertex_ids) == 3


def test_expected_cards_conversion():
    assert K.expected_cards_per_roll(36) == pytest.approx(1.0)
    assert K.expected_cards_per_round(10, 4) == pytest.approx(10 / 36 * 4)


# --- validation catches misreadings ---------------------------------------


def test_missing_tile_is_rejected():
    board = random_board(seed=4)
    data = board_to_dict(board)
    data["hexes"].pop()
    with pytest.raises(BoardError, match="mancanti"):
        board_from_dict(data)


def test_wrong_token_multiset_is_rejected():
    board = random_board(seed=4)
    data = board_to_dict(board)
    for hexdata in data["hexes"]:
        if hexdata["number"] == 5:
            hexdata["number"] = 6
            break
    with pytest.raises(BoardError, match="gettoni"):
        board_from_dict(data)


def test_seven_token_is_rejected():
    board = random_board(seed=4)
    data = board_to_dict(board)
    for hexdata in data["hexes"]:
        if hexdata["number"] == 6:
            hexdata["number"] = 7
            break
    with pytest.raises(BoardError):
        board_from_dict(data)


def test_desert_with_a_number_is_rejected():
    board = random_board(seed=4)
    data = board_to_dict(board)
    for hexdata in data["hexes"]:
        if hexdata["resource"] == K.DESERT:
            hexdata["number"] = 8
    with pytest.raises(BoardError):
        board_from_dict(data)


def test_unknown_resource_is_rejected():
    board = random_board(seed=4)
    data = board_to_dict(board)
    data["hexes"][0]["resource"] = "pizza"
    with pytest.raises(BoardError, match="risorsa sconosciuta"):
        board_from_dict(data)


# --- distance rule ---------------------------------------------------------


def test_placement_burns_its_neighbours():
    board = random_board(seed=6)
    target = "v20"
    placed = board.with_placement(Placement(player=2, vertex=target, order=1))
    assert not placed.is_legal(target)
    for n in G.vertex_neighbours[target]:
        assert not placed.is_legal(n)
    assert len(placed.legal_vertices) == 54 - 1 - len(G.vertex_neighbours[target])


def test_adjacent_settlements_are_rejected():
    board = random_board(seed=6)
    a = "v20"
    b = G.vertex_neighbours[a][0]
    bad = Board(
        hexes=board.hexes,
        ports=board.ports,
        placements=(Placement(1, a), Placement(2, b)),
    )
    with pytest.raises(BoardError, match="distance rule"):
        bad.validate(strict=True)


def test_with_placement_does_not_mutate_the_original():
    board = random_board(seed=6)
    before = len(board.legal_vertices)
    board.with_placement(Placement(player=1, vertex="v20"))
    assert len(board.legal_vertices) == before


# --- ports -----------------------------------------------------------------


def test_ports_sit_on_coastal_edges_and_cover_two_vertices_each():
    board = random_board(seed=8)
    for port in board.ports:
        assert port.edge_id in G.coastal_edges
        a, b = G.edge_vertices[port.edge_id]
        assert board.vertex_port(a) is port
        assert board.vertex_port(b) is port
    assert len(board.port_by_vertex) == 18


def test_port_mix_is_four_generic_and_five_specific():
    board = random_board(seed=8)
    generic = [p for p in board.ports if p.is_generic]
    assert len(generic) == K.N_PORTS_GENERIC
    assert len(board.ports) - len(generic) == K.N_PORTS_SPECIFIC
    assert {p.resource for p in board.ports if not p.is_generic} == set(K.RESOURCES)


def test_ports_do_not_share_vertices():
    board = random_board(seed=8)
    vertices = [v for p in board.ports for v in G.edge_vertices[p.edge_id]]
    assert len(vertices) == len(set(vertices))
