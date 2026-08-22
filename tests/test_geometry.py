"""Topology: the numbers that must never move."""

from collections import Counter

import pytest

from catan_advisor.geometry import GEOMETRY as G
from catan_advisor.geometry import Axial, corners_of


def test_board_has_19_hexes_in_3_4_5_4_3_rows():
    assert len(G.hex_ids) == 19
    assert [len(row) for row in G.hex_rows] == [3, 4, 5, 4, 3]


def test_board_has_54_vertices_and_72_edges():
    assert len(G.vertex_ids) == 54
    assert len(G.edge_ids) == 72


def test_every_vertex_is_the_meeting_point_of_exactly_three_positions():
    for key in G.vertex_keys:
        assert len(key) == 3


def test_vertices_touch_one_two_or_three_land_hexes():
    counts = Counter(len(h) for h in G.vertex_hexes.values())
    # 18 outer corners touch 1 hex, 12 touch 2, the 24 inner ones touch 3.
    assert counts == {1: 18, 2: 12, 3: 24}


def test_coast_has_30_edges_and_30_vertices():
    assert len(G.coastal_edges) == 30
    assert len(G.coastal_vertices) == 30
    assert len(G.edge_ids) - len(G.coastal_edges) == 42  # inland edges


def test_vertex_degree_is_two_or_three():
    counts = Counter(len(n) for n in G.vertex_neighbours.values())
    assert counts == {2: 18, 3: 36}


def test_each_hex_has_six_distinct_vertices_and_six_edges():
    for hid in G.hex_ids:
        ring = G.hex_vertices[hid]
        assert len(ring) == 6
        assert len(set(ring)) == 6


def test_edges_join_vertices_that_share_hexes():
    for eid, (a, b) in G.edge_vertices.items():
        shared = set(G.vertex_hexes[a]) & set(G.vertex_hexes[b])
        assert 1 <= len(shared) <= 2
        assert G.edge_hexes[eid] == tuple(sorted(shared))


def test_adjacency_is_symmetric():
    for v, neighbours in G.vertex_neighbours.items():
        for n in neighbours:
            assert v in G.vertex_neighbours[n]


def test_corner_derivation_is_shared_between_neighbouring_hexes():
    a, b = Axial(0, 0), Axial(1, 0)
    shared = set(corners_of(a)) & set(corners_of(b))
    assert len(shared) == 2  # two hexes share exactly one edge, so two corners


def test_reading_order_is_stable():
    assert G.hex_ids[0] == "h01"
    assert G.hex_ids[-1] == "h19"
    assert G.vertex_ids[0] == "v01"
    assert G.vertex_ids[-1] == "v54"
    # v01 is the northern tip of the first hex of the top row.
    assert G.vertex_hexes["v01"] == ("h01",)


def test_vertices_within_two_roads():
    reach = G.vertices_within("v28", roads=2)
    assert all(1 <= steps <= 2 for steps in reach.values())
    one_step = {v for v, s in reach.items() if s == 1}
    assert one_step == set(G.vertex_neighbours["v28"])


@pytest.mark.parametrize("hid", ["h01", "h10", "h19"])
def test_hex_distance_to_itself_is_zero(hid):
    assert G.hex_distance(hid, hid) == 0


def test_center_hex_is_distance_two_from_every_corner():
    center = "h10"  # middle of the middle row
    assert G.coord_of_hex[center] == Axial(0, 0)
    assert max(G.hex_distance(center, h) for h in G.hex_ids) == 2
