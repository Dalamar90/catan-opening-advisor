"""The board model: topology from geometry.py plus terrain, tokens and ports.

A Board is a snapshot of one game. It answers questions ("what does this vertex
produce?", "is it legal?") but holds no opinions -- every weight and heuristic
lives in the scoring package.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property

from . import constants as K
from .geometry import GEOMETRY, Geometry


class BoardError(ValueError):
    """Raised when a board description is not a legal base-game board."""


@dataclass(frozen=True)
class Hex:
    id: str
    resource: str
    number: int | None

    @property
    def is_desert(self) -> bool:
        return self.resource == K.DESERT

    @property
    def pips(self) -> int:
        return 0 if self.number is None else K.PIPS[self.number]

    def __str__(self) -> str:
        if self.is_desert:
            return "deserto"
        return f"{self.number}-{K.RESOURCE_LABEL_IT[self.resource]}"


@dataclass(frozen=True)
class Port:
    """A trading port, attached to the coastal edge it sits on."""

    edge_id: str
    ratio: int                      # 2 or 3
    resource: str | None = None     # None for a 3:1 generic port

    @property
    def is_generic(self) -> bool:
        return self.resource is None

    def __str__(self) -> str:
        if self.is_generic:
            return "porto 3:1"
        return f"porto 2:1 {K.RESOURCE_LABEL_IT[self.resource]}"


@dataclass(frozen=True)
class Placement:
    """A settlement already placed, ours or an opponent's."""

    player: int
    vertex: str
    road_edge: str | None = None
    order: int | None = None        # pick number in the snake draft


@dataclass
class Board:
    hexes: dict[str, Hex]
    ports: tuple[Port, ...] = ()
    placements: tuple[Placement, ...] = ()
    n_players: int = 4
    my_position: int = 1
    geometry: Geometry = field(default=GEOMETRY, repr=False)

    # ------------------------------------------------------------------
    # validation
    # ------------------------------------------------------------------
    def validate(self, strict: bool = True) -> list[str]:
        """Return a list of problems. With strict=True, raise instead.

        The strict checks are what turn a board read off a photo into a board
        we know is legal: wrong tile counts or a wrong token multiset almost
        always mean the vision step misread a tile.
        """
        problems: list[str] = []
        geo_ids = set(self.geometry.hex_ids)

        missing = geo_ids - set(self.hexes)
        extra = set(self.hexes) - geo_ids
        if missing:
            problems.append(f"tessere mancanti: {sorted(missing)}")
        if extra:
            problems.append(f"id di tessera sconosciuti: {sorted(extra)}")

        if not missing and not extra:
            counts: dict[str, int] = {}
            for h in self.hexes.values():
                if h.resource not in K.TERRAINS:
                    problems.append(f"{h.id}: terreno sconosciuto {h.resource!r}")
                counts[h.resource] = counts.get(h.resource, 0) + 1
            if counts != K.TILE_COUNTS:
                problems.append(
                    f"conteggio terreni {counts} diverso da quello del gioco base {K.TILE_COUNTS}"
                )

            tokens = sorted(h.number for h in self.hexes.values() if h.number is not None)
            if tuple(tokens) != K.NUMBER_TOKENS:
                problems.append(
                    f"gettoni numerici {tokens} diversi da quelli del gioco base "
                    f"{list(K.NUMBER_TOKENS)}"
                )
            for h in self.hexes.values():
                if h.is_desert and h.number is not None:
                    problems.append(f"{h.id}: il deserto non porta gettone")
                if not h.is_desert and h.number is None:
                    problems.append(f"{h.id}: manca il gettone numerico")
                if h.number == 7:
                    problems.append(f"{h.id}: il 7 non esiste come gettone")

            if self.total_pips != K.TOTAL_PIPS:
                problems.append(f"pip totali {self.total_pips}, attesi {K.TOTAL_PIPS}")

        for p in self.ports:
            if p.edge_id not in self.geometry.coastal_edges:
                problems.append(f"porto su {p.edge_id}: non e un lato costiero")
            if p.ratio not in (2, 3):
                problems.append(f"porto su {p.edge_id}: rapporto {p.ratio} non valido")
            if p.ratio == 2 and p.resource not in K.RESOURCES:
                problems.append(f"porto 2:1 su {p.edge_id}: risorsa mancante o ignota")

        port_vertices: list[str] = []
        for p in self.ports:
            port_vertices.extend(self.geometry.edge_vertices.get(p.edge_id, ()))
        duplicated = {v for v in port_vertices if port_vertices.count(v) > 1}
        if duplicated:
            problems.append(f"piu porti sullo stesso incrocio: {sorted(duplicated)}")

        seen: set[str] = set()
        for pl in self.placements:
            if pl.vertex not in self.geometry.vertex_ids:
                problems.append(f"piazzamento su vertice sconosciuto {pl.vertex}")
                continue
            if pl.vertex in seen:
                problems.append(f"due colonie sullo stesso incrocio {pl.vertex}")
            seen.add(pl.vertex)
        # Report each offending pair once, not once per endpoint.
        for a in sorted(seen):
            for b in self.geometry.vertex_neighbours[a]:
                if b in seen and a < b:
                    problems.append(f"distance rule violata: {a} e {b} sono adiacenti")

        if strict and problems:
            raise BoardError("; ".join(problems))
        return problems

    def warnings(self) -> list[str]:
        """Non-fatal oddities worth telling the user about.

        Must stay safe on an incomplete board: it is called by the validate
        command precisely when the board may be broken.
        """
        out = []
        for a, b in self._adjacent_hex_pairs():
            if self.hexes[a].number in K.HIGH_NUMBERS and self.hexes[b].number in K.HIGH_NUMBERS:
                out.append(
                    f"{a} ({self.hexes[a]}) e {b} ({self.hexes[b]}) sono adiacenti: "
                    "il setup bilanciato ufficiale lo vieta, verifica la lettura"
                )
        n_generic = sum(1 for p in self.ports if p.is_generic)
        n_specific = len(self.ports) - n_generic
        if self.ports and (n_generic != K.N_PORTS_GENERIC or n_specific != K.N_PORTS_SPECIFIC):
            out.append(
                f"porti: {n_generic} generici e {n_specific} specifici, "
                f"attesi {K.N_PORTS_GENERIC} e {K.N_PORTS_SPECIFIC}"
            )
        return out

    def _adjacent_hex_pairs(self) -> list[tuple[str, str]]:
        pairs = []
        for eid, hs in self.geometry.edge_hexes.items():
            if len(hs) == 2 and hs[0] in self.hexes and hs[1] in self.hexes:
                pairs.append((hs[0], hs[1]))
        return pairs

    # ------------------------------------------------------------------
    # production
    # ------------------------------------------------------------------
    @property
    def total_pips(self) -> int:
        return sum(h.pips for h in self.hexes.values())

    def vertex_hexes(self, vertex_id: str) -> tuple[Hex, ...]:
        return tuple(self.hexes[h] for h in self.geometry.vertex_hexes[vertex_id])

    def vertex_pips(self, vertex_id: str) -> int:
        """Raw pip count -- the plain counter, always shown next to the score."""
        return sum(h.pips for h in self.vertex_hexes(vertex_id))

    def vertex_production(self, vertex_id: str) -> dict[str, int]:
        """Pips per resource produced by a settlement on this vertex."""
        out: dict[str, int] = {}
        for h in self.vertex_hexes(vertex_id):
            if h.is_desert or h.number is None:
                continue
            out[h.resource] = out.get(h.resource, 0) + h.pips
        return out

    def vertex_resources(self, vertex_id: str) -> tuple[str, ...]:
        return tuple(sorted(self.vertex_production(vertex_id)))

    def vertex_numbers(self, vertex_id: str) -> tuple[int, ...]:
        return tuple(
            sorted(h.number for h in self.vertex_hexes(vertex_id) if h.number is not None)
        )

    @cached_property
    def pips_by_resource(self) -> dict[str, int]:
        out = {r: 0 for r in K.RESOURCES}
        for h in self.hexes.values():
            if not h.is_desert:
                out[h.resource] += h.pips
        return out

    # ------------------------------------------------------------------
    # ports
    # ------------------------------------------------------------------
    @cached_property
    def port_by_vertex(self) -> dict[str, Port]:
        out = {}
        for p in self.ports:
            for v in self.geometry.edge_vertices[p.edge_id]:
                out[v] = p
        return out

    def vertex_port(self, vertex_id: str) -> Port | None:
        return self.port_by_vertex.get(vertex_id)

    # ------------------------------------------------------------------
    # legality
    # ------------------------------------------------------------------
    @cached_property
    def occupied(self) -> frozenset[str]:
        return frozenset(p.vertex for p in self.placements)

    @cached_property
    def blocked(self) -> frozenset[str]:
        """Vertices burned by the distance rule (neighbours of a settlement)."""
        out: set[str] = set()
        for v in self.occupied:
            out.update(self.geometry.vertex_neighbours[v])
        return frozenset(out - self.occupied)

    def is_legal(self, vertex_id: str) -> bool:
        return vertex_id not in self.occupied and vertex_id not in self.blocked

    @cached_property
    def legal_vertices(self) -> tuple[str, ...]:
        return tuple(v for v in self.geometry.vertex_ids if self.is_legal(v))

    def with_placement(self, placement: Placement) -> "Board":
        """A copy of the board with one more settlement. Used to simulate picks."""
        return Board(
            hexes=self.hexes,
            ports=self.ports,
            placements=self.placements + (placement,),
            n_players=self.n_players,
            my_position=self.my_position,
            geometry=self.geometry,
        )

    def vertex_label(self, vertex_id: str) -> str:
        """Just the tiles and port, e.g. '9-minerale / 6-legno / porto 3:1'."""
        parts = [str(h) for h in self.vertex_hexes(vertex_id)]
        port = self.vertex_port(vertex_id)
        if port:
            parts.append(str(port))
        return " / ".join(parts)

    def describe_vertex(self, vertex_id: str) -> str:
        return f"{vertex_id} [{self.vertex_label(vertex_id)}]"
