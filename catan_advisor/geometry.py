"""Pure topology of the 19-hex board: 19 hexes, 54 vertices, 72 edges.

No resources, no numbers, no weights live here. Everything is derived
analytically from axial coordinates, so vertex identity is exact -- a vertex
*is* the set of three hex positions that meet at it (some of which may be sea).
That removes the floating point tolerance the photo-matching approach needs.

Layout: pointy-top hexes, axial coordinates (q, r), radius-2 hexagon.
Rows run 3-4-5-4-3 from north to south.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import cached_property
from typing import Iterator, NamedTuple

BOARD_RADIUS = 2


class Axial(NamedTuple):
    q: int
    r: int

    def __add__(self, other):  # type: ignore[override]
        return Axial(self.q + other.q, self.r + other.r)

    def distance(self, other: "Axial") -> int:
        dq, dr = self.q - other.q, self.r - other.r
        return (abs(dq) + abs(dr) + abs(dq + dr)) // 2


# Neighbour offsets for pointy-top axial coordinates, clockwise from east.
NEIGHBOURS: tuple[Axial, ...] = (
    Axial(1, 0),    # E
    Axial(0, 1),    # SE
    Axial(-1, 1),   # SW
    Axial(-1, 0),   # W
    Axial(0, -1),   # NW
    Axial(1, -1),   # NE
)

# A corner of a hex is where that hex and two rotationally adjacent neighbours
# meet. Six corners = six consecutive neighbour pairs.
_CORNER_PAIRS: tuple[tuple[Axial, Axial], ...] = tuple(
    (NEIGHBOURS[i], NEIGHBOURS[(i + 1) % 6]) for i in range(6)
)

# Plane coordinates exist only to give humans a stable reading order
# (north to south, west to east) and to draw the board later.
SQRT3 = math.sqrt(3.0)


def hex_center(c: Axial) -> tuple[float, float]:
    return (SQRT3 * (c.q + c.r / 2.0), 1.5 * c.r)


def board_coords(radius: int = BOARD_RADIUS) -> list[Axial]:
    """The 19 land positions of the base board, in reading order."""
    coords = [
        Axial(q, r)
        for r in range(-radius, radius + 1)
        for q in range(-radius, radius + 1)
        if max(abs(q), abs(r), abs(q + r)) <= radius
    ]
    return sorted(
        coords,
        key=lambda c: (round(hex_center(c)[1], 6), round(hex_center(c)[0], 6)),
    )


def corners_of(c: Axial) -> list[frozenset]:
    """The six vertex keys of a hex, clockwise starting from the east corner."""
    return [frozenset((c, c + a, c + b)) for a, b in _CORNER_PAIRS]


def vertex_center(key: frozenset) -> tuple[float, float]:
    xs, ys = zip(*(hex_center(c) for c in key))
    return (sum(xs) / 3.0, sum(ys) / 3.0)


@dataclass(frozen=True)
class Geometry:
    """Immutable topology, computed once and shared by every board."""

    radius: int = BOARD_RADIUS

    # --- hexes ---------------------------------------------------------
    @cached_property
    def hex_coords(self) -> tuple[Axial, ...]:
        return tuple(board_coords(self.radius))

    @cached_property
    def hex_ids(self) -> tuple[str, ...]:
        return tuple(f"h{i:02d}" for i in range(1, len(self.hex_coords) + 1))

    @cached_property
    def coord_of_hex(self) -> dict[str, Axial]:
        return dict(zip(self.hex_ids, self.hex_coords))

    @cached_property
    def hex_of_coord(self) -> dict[Axial, str]:
        return {c: h for h, c in self.coord_of_hex.items()}

    @cached_property
    def hex_rows(self) -> tuple[tuple[str, ...], ...]:
        """Hex ids grouped into the 3-4-5-4-3 rows, north to south."""
        rows: dict[int, list[str]] = {}
        for hid, c in self.coord_of_hex.items():
            rows.setdefault(c.r, []).append(hid)
        return tuple(tuple(sorted(rows[r])) for r in sorted(rows))

    # --- vertices ------------------------------------------------------
    @cached_property
    def vertex_keys(self) -> tuple[frozenset, ...]:
        keys = {k for c in self.hex_coords for k in corners_of(c)}
        return tuple(
            sorted(
                keys,
                key=lambda k: (
                    round(vertex_center(k)[1], 6),
                    round(vertex_center(k)[0], 6),
                ),
            )
        )

    @cached_property
    def vertex_ids(self) -> tuple[str, ...]:
        return tuple(f"v{i:02d}" for i in range(1, len(self.vertex_keys) + 1))

    @cached_property
    def key_of_vertex(self) -> dict[str, frozenset]:
        return dict(zip(self.vertex_ids, self.vertex_keys))

    @cached_property
    def vertex_of_key(self) -> dict[frozenset, str]:
        return {k: v for v, k in self.key_of_vertex.items()}

    @cached_property
    def vertex_hexes(self) -> dict[str, tuple[str, ...]]:
        """Land hex ids touching each vertex (1 to 3; the rest is sea)."""
        out = {}
        for vid, key in self.key_of_vertex.items():
            ids = [self.hex_of_coord[c] for c in key if c in self.hex_of_coord]
            out[vid] = tuple(sorted(ids))
        return out

    @cached_property
    def hex_vertices(self) -> dict[str, tuple[str, ...]]:
        return {
            hid: tuple(self.vertex_of_key[k] for k in corners_of(c))
            for hid, c in self.coord_of_hex.items()
        }

    # --- edges ---------------------------------------------------------
    @cached_property
    def edge_keys(self) -> tuple[frozenset, ...]:
        keys = set()
        for hid in self.hex_ids:
            ring = self.hex_vertices[hid]
            for i in range(6):
                keys.add(frozenset((ring[i], ring[(i + 1) % 6])))
        return tuple(sorted(keys, key=self._edge_sort_key))

    def _edge_sort_key(self, key: frozenset) -> tuple[float, float]:
        pts = [vertex_center(self.key_of_vertex[v]) for v in key]
        return (
            round(sum(p[1] for p in pts) / 2, 6),
            round(sum(p[0] for p in pts) / 2, 6),
        )

    @cached_property
    def edge_ids(self) -> tuple[str, ...]:
        return tuple(f"e{i:02d}" for i in range(1, len(self.edge_keys) + 1))

    @cached_property
    def key_of_edge(self) -> dict[str, frozenset]:
        return dict(zip(self.edge_ids, self.edge_keys))

    @cached_property
    def edge_of_key(self) -> dict[frozenset, str]:
        return {k: e for e, k in self.key_of_edge.items()}

    @cached_property
    def edge_vertices(self) -> dict[str, tuple[str, str]]:
        out = {}
        for eid, key in self.key_of_edge.items():
            a, b = sorted(key)
            out[eid] = (a, b)
        return out

    @cached_property
    def vertex_neighbours(self) -> dict[str, tuple[str, ...]]:
        """Vertices one edge away -- the ones burned by the distance rule."""
        out: dict[str, set[str]] = {v: set() for v in self.vertex_ids}
        for a, b in self.edge_vertices.values():
            out[a].add(b)
            out[b].add(a)
        return {v: tuple(sorted(n)) for v, n in out.items()}

    @cached_property
    def vertex_edges(self) -> dict[str, tuple[str, ...]]:
        out: dict[str, set[str]] = {v: set() for v in self.vertex_ids}
        for eid, (a, b) in self.edge_vertices.items():
            out[a].add(eid)
            out[b].add(eid)
        return {v: tuple(sorted(e)) for v, e in out.items()}

    @cached_property
    def edge_hexes(self) -> dict[str, tuple[str, ...]]:
        """Land hexes on either side of an edge (1 coastal, 2 inland)."""
        out = {}
        for eid, (a, b) in self.edge_vertices.items():
            shared = set(self.vertex_hexes[a]) & set(self.vertex_hexes[b])
            out[eid] = tuple(sorted(shared))
        return out

    # --- coast ---------------------------------------------------------
    @cached_property
    def coastal_edges(self) -> tuple[str, ...]:
        """The 30 outer edges, ordered clockwise starting from due north."""
        edges = [e for e in self.edge_ids if len(self.edge_hexes[e]) == 1]
        return tuple(sorted(edges, key=self._clockwise_angle))

    def _clockwise_angle(self, edge_id: str) -> float:
        a, b = self.edge_vertices[edge_id]
        pa = vertex_center(self.key_of_vertex[a])
        pb = vertex_center(self.key_of_vertex[b])
        x, y = (pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2
        # atan2(x, -y) is 0 at north and grows clockwise.
        angle = math.atan2(x, -y)
        return angle if angle >= 0 else angle + 2 * math.pi

    @cached_property
    def coastal_vertices(self) -> tuple[str, ...]:
        return tuple(v for v in self.vertex_ids if len(self.vertex_hexes[v]) < 3)

    def hex_distance(self, a: str, b: str) -> int:
        return self.coord_of_hex[a].distance(self.coord_of_hex[b])

    def vertices_within(self, vertex_id: str, roads: int) -> dict[str, int]:
        """Map of vertex -> number of roads needed to reach it (1..roads)."""
        seen = {vertex_id: 0}
        frontier = [vertex_id]
        for step in range(1, roads + 1):
            nxt = []
            for v in frontier:
                for n in self.vertex_neighbours[v]:
                    if n not in seen:
                        seen[n] = step
                        nxt.append(n)
            frontier = nxt
        del seen[vertex_id]
        return seen

    def __iter__(self) -> Iterator[str]:
        return iter(self.vertex_ids)


GEOMETRY = Geometry()
