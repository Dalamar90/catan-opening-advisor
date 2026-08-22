"""The mandatory pre-computation of KB B.6, run before any advice is given.

Five things, in the order the KB asks for them:
  1. pips per resource and the gap from the expected share -> what is scarce here
  2. the strongest junctions
  3. hot zones -- where the pips cluster geographically
  4. the port map, with the tiles that naturally feed each port
  5. how many strong junctions exist, which is the input to the draft theory of C.1

Plus the spatial concentration index of KB E.6: a scarce resource that is also
clustered means whoever takes that corner owns it for the whole game.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import constants as K
from .board import Board
from .config import Config, load_config


@dataclass
class VertexSummary:
    vertex: str
    pips: int
    weighted_pips: float
    resources: tuple[str, ...]
    numbers: tuple[int, ...]
    production: dict[str, int]
    port: str | None
    legal: bool

    def cards_per_roll(self) -> float:
        return K.expected_cards_per_roll(self.pips)

    def cards_per_round(self, n_players: int) -> float:
        return K.expected_cards_per_round(self.pips, n_players)


@dataclass
class HotZone:
    center_hex: str
    hexes: tuple[str, ...]
    pips: int
    best_vertex: str
    best_vertex_pips: int


@dataclass
class PortInfo:
    edge: str
    label: str
    ratio: int
    resource: str | None
    vertices: tuple[str, str]
    served_pips: int                    # pips reachable from the two port vertices
    self_served: int                    # pips of its own resource on those vertices
    natural: bool                       # a 2:1 port fed by its own resource


@dataclass
class Precompute:
    board: Board
    config: Config
    scarcity: dict[str, dict[str, float]]
    weights: dict[str, float]
    vertices: list[VertexSummary]
    hot_zones: list[HotZone]
    ports: list[PortInfo]
    concentration: dict[str, float]
    strong_vertex_count: int
    strong_threshold: int
    warnings: list[str] = field(default_factory=list)

    def top(self, n: int = 10, legal_only: bool = True) -> list[VertexSummary]:
        pool = [v for v in self.vertices if v.legal or not legal_only]
        return sorted(pool, key=lambda v: (-v.pips, -v.weighted_pips, v.vertex))[:n]

    def top_weighted(self, n: int = 10, legal_only: bool = True) -> list[VertexSummary]:
        pool = [v for v in self.vertices if v.legal or not legal_only]
        return sorted(pool, key=lambda v: (-v.weighted_pips, -v.pips, v.vertex))[:n]

    def by_vertex(self, vertex_id: str) -> VertexSummary:
        return next(v for v in self.vertices if v.vertex == vertex_id)


def precompute(board: Board, config: Config | None = None) -> Precompute:
    cfg = config or load_config()
    pips_by_resource = board.pips_by_resource
    scarcity = cfg.scarcity_report(pips_by_resource, board.n_players)
    weights = cfg.resource_weights(pips_by_resource, board.n_players)

    summaries = [_summarise_vertex(board, v, weights) for v in board.geometry.vertex_ids]

    threshold = int(cfg.get("report.strong_vertex_pips", 10))
    strong = sum(1 for s in summaries if s.legal and s.pips >= threshold)

    return Precompute(
        board=board,
        config=cfg,
        scarcity=scarcity,
        weights=weights,
        vertices=summaries,
        hot_zones=_hot_zones(board, summaries),
        ports=_port_map(board),
        concentration=_concentration(board),
        strong_vertex_count=strong,
        strong_threshold=threshold,
        warnings=board.warnings(),
    )


def _summarise_vertex(board: Board, vertex_id: str, weights: dict[str, float]) -> VertexSummary:
    production = board.vertex_production(vertex_id)
    port = board.vertex_port(vertex_id)
    return VertexSummary(
        vertex=vertex_id,
        pips=board.vertex_pips(vertex_id),
        weighted_pips=sum(p * weights[r] for r, p in production.items()),
        resources=tuple(sorted(production)),
        numbers=board.vertex_numbers(vertex_id),
        production=production,
        port=str(port) if port else None,
        legal=board.is_legal(vertex_id),
    )


def _hot_zones(board: Board, summaries: list[VertexSummary], top: int = 3) -> list[HotZone]:
    """Neighbourhood pip density: a hex plus its direct neighbours."""
    geo = board.geometry
    adjacency: dict[str, set[str]] = {h: set() for h in geo.hex_ids}
    for hs in geo.edge_hexes.values():
        if len(hs) == 2:
            adjacency[hs[0]].add(hs[1])
            adjacency[hs[1]].add(hs[0])

    by_vertex = {s.vertex: s for s in summaries}
    zones = []
    for hid in geo.hex_ids:
        cluster = tuple(sorted({hid} | adjacency[hid]))
        pips = sum(board.hexes[h].pips for h in cluster)
        vertices = {v for h in cluster for v in geo.hex_vertices[h]}
        best = max(vertices, key=lambda v: (by_vertex[v].pips, v))
        zones.append(
            HotZone(
                center_hex=hid,
                hexes=cluster,
                pips=pips,
                best_vertex=best,
                best_vertex_pips=by_vertex[best].pips,
            )
        )

    zones.sort(key=lambda z: (-z.pips, z.center_hex))
    # Keep zones that do not overlap too much, so the report shows real alternatives.
    chosen: list[HotZone] = []
    for zone in zones:
        if all(len(set(zone.hexes) & set(c.hexes)) <= 2 for c in chosen):
            chosen.append(zone)
        if len(chosen) == top:
            break
    return chosen


def _port_map(board: Board) -> list[PortInfo]:
    geo = board.geometry
    out = []
    for port in board.ports:
        a, b = geo.edge_vertices[port.edge_id]
        tiles = {h.id: h for v in (a, b) for h in board.vertex_hexes(v)}
        served = sum(h.pips for h in tiles.values())
        self_served = sum(
            h.pips for h in tiles.values() if port.resource and h.resource == port.resource
        )
        out.append(
            PortInfo(
                edge=port.edge_id,
                label=str(port),
                ratio=port.ratio,
                resource=port.resource,
                vertices=(a, b),
                served_pips=served,
                self_served=self_served,
                natural=bool(port.resource) and self_served >= 3,
            )
        )
    return out


def _concentration(board: Board) -> dict[str, float]:
    """KB E.6: how spatially clustered each resource is, in [-1, 1].

    Positive means the tiles of that resource sit together, so whoever takes
    that corner of the board has a monopoly nobody can route around.
    """
    geo = board.geometry
    baseline = _mean_pairwise_distance(geo, list(geo.hex_ids))
    out = {}
    for resource in K.RESOURCES:
        tiles = [h.id for h in board.hexes.values() if h.resource == resource]
        if len(tiles) < 2 or baseline == 0:
            out[resource] = 0.0
            continue
        out[resource] = 1.0 - _mean_pairwise_distance(geo, tiles) / baseline
    return out


def _mean_pairwise_distance(geo, hex_ids: list[str]) -> float:
    pairs = [
        geo.hex_distance(a, b)
        for i, a in enumerate(hex_ids)
        for b in hex_ids[i + 1 :]
    ]
    return sum(pairs) / len(pairs) if pairs else 0.0
