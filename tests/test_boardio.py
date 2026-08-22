"""Regressions for the input path: broken boards and port notation.

Everything here is a bug that actually shipped in the first cut of M1 and was
found by re-reading the code. The input path is the one a photo reading feeds,
so it has to fail informatively rather than crash or silently invent data.
"""

import pytest

from catan_advisor import constants as K
from catan_advisor.board import Board, BoardError, Placement
from catan_advisor.boardio import board_from_dict, board_to_dict, random_board
from catan_advisor.geometry import GEOMETRY as G


@pytest.fixture
def data():
    return board_to_dict(random_board(seed=7))


# --- an incomplete board must not crash the validator ----------------------


def test_warnings_survive_a_board_with_missing_tiles(data):
    data["hexes"].pop()
    board = board_from_dict(data, strict=False)
    assert board.warnings() == []          # used to raise KeyError
    assert any("mancanti" in p for p in board.validate(strict=False))


def test_validate_reports_every_problem_at_once(data):
    data["hexes"][4]["number"] = 6
    data["hexes"][9]["resource"] = "wheat"
    problems = board_from_dict(data, strict=False).validate(strict=False)
    assert len(problems) >= 3
    assert any("terreni" in p for p in problems)
    assert any("gettoni" in p for p in problems)
    assert any("pip totali" in p for p in problems)


# --- ports declared on vertices, KB D.1 notation ---------------------------


def _both_vertices_of_a_coastal_edge() -> tuple[str, str, str]:
    edge = G.coastal_edges[0]
    a, b = G.edge_vertices[edge]
    return edge, a, b


def test_port_on_two_vertices_creates_exactly_one_port(data):
    edge, a, b = _both_vertices_of_a_coastal_edge()
    data.pop("ports")
    spec = {"type": "2:1", "resource": "ore"}
    data["vertices"] = [{"id": a, "port": spec}, {"id": b, "port": spec}]

    board = board_from_dict(data, strict=False)
    assert len(board.ports) == 1           # used to create three
    assert board.ports[0].edge_id == edge
    assert board.ports[0].ratio == 2
    assert board.ports[0].resource == K.ORE
    assert board.vertex_port(a) is board.vertex_port(b) is board.ports[0]


def test_the_coast_is_a_closed_ring():
    """Why a port on a single vertex can never be resolved: every coastal
    vertex sits between exactly two coastal edges."""
    coastal = set(G.coastal_edges)
    per_vertex = {
        v: len([e for e in G.vertex_edges[v] if e in coastal]) for v in G.coastal_vertices
    }
    assert set(per_vertex.values()) == {2}


def test_lone_declaration_is_rejected_as_ambiguous(data):
    data.pop("ports")
    data["vertices"] = [{"id": G.coastal_vertices[0], "port": {"type": "3:1"}}]
    with pytest.raises(BoardError, match="ambiguo"):
        board_from_dict(data, strict=False)


def test_two_vertices_declaring_different_ports_are_rejected(data):
    _, a, b = _both_vertices_of_a_coastal_edge()
    data.pop("ports")
    data["vertices"] = [
        {"id": a, "port": {"type": "3:1"}},
        {"id": b, "port": {"type": "2:1", "resource": "ore"}},
    ]
    with pytest.raises(BoardError, match="ambiguo"):
        board_from_dict(data, strict=False)


def test_ports_given_by_edge_are_preferred_over_vertex_notation(data):
    edge, a, b = _both_vertices_of_a_coastal_edge()
    data["vertices"] = [{"id": a, "port": {"type": "3:1"}}, {"id": b, "port": {"type": "3:1"}}]
    board = board_from_dict(data)
    assert len(board.ports) == 9           # the explicit "ports" list wins


def test_overlapping_ports_are_rejected():
    board = random_board(seed=7)
    edge = G.coastal_edges[0]
    a, _ = G.edge_vertices[edge]
    other = next(e for e in G.vertex_edges[a] if e != edge and e in set(G.coastal_edges))
    from catan_advisor.board import Port

    clashing = Board(
        hexes=board.hexes,
        ports=(Port(edge, 3), Port(other, 3)),
    )
    problems = clashing.validate(strict=False)
    assert any("piu porti sullo stesso incrocio" in p for p in problems)


# --- distance rule ---------------------------------------------------------


def test_adjacent_settlements_are_reported_once():
    board = random_board(seed=6)
    a = "v20"
    b = G.vertex_neighbours[a][0]
    bad = Board(hexes=board.hexes, placements=(Placement(1, a), Placement(2, b)))
    problems = [p for p in bad.validate(strict=False) if "distance rule" in p]
    assert len(problems) == 1              # used to be reported from both ends
