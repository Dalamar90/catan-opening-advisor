"""Read and write the board JSON of KB D.1.

The schema is deliberately forgiving on input (Italian or English resource
names, ports given either by edge or by the two vertices they touch) and strict
on validation, because the main producer of these files is a vision pass over a
photo and we want misreadings to fail loudly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .. import constants as K
from ..board import Board, BoardError, Hex, Placement, Port
from ..geometry import GEOMETRY, Geometry

# Accepted spellings for each terrain, so the JSON can be written in Italian.
_TERRAIN_ALIASES: dict[str, str] = {
    "wood": K.WOOD, "lumber": K.WOOD, "forest": K.WOOD, "legno": K.WOOD, "bosco": K.WOOD,
    "brick": K.BRICK, "clay": K.BRICK, "mattone": K.BRICK, "argilla": K.BRICK,
    "collina": K.BRICK,
    "wheat": K.WHEAT, "grain": K.WHEAT, "grano": K.WHEAT, "campo": K.WHEAT,
    "sheep": K.SHEEP, "wool": K.SHEEP, "pecora": K.SHEEP, "pascolo": K.SHEEP,
    "lana": K.SHEEP,
    "ore": K.ORE, "minerale": K.ORE, "montagna": K.ORE, "roccia": K.ORE,
    "desert": K.DESERT, "deserto": K.DESERT,
}


def normalise_resource(name: str | None) -> str | None:
    if name is None:
        return None
    key = str(name).strip().lower()
    if key in _TERRAIN_ALIASES:
        return _TERRAIN_ALIASES[key]
    raise BoardError(f"risorsa sconosciuta: {name!r}")


def load_board(path: str | Path, strict: bool = True) -> Board:
    with open(path, "r", encoding="utf-8") as fh:
        return board_from_dict(json.load(fh), strict=strict)


def board_from_dict(
    data: dict[str, Any], geometry: Geometry = GEOMETRY, strict: bool = True
) -> Board:
    hexes: dict[str, Hex] = {}
    raw_hexes = data.get("hexes")
    if not raw_hexes:
        raise BoardError("il tabellone non contiene la chiave 'hexes'")

    for i, raw in enumerate(raw_hexes):
        hid = raw.get("id") or _id_from_axial(raw, geometry)
        if hid is None:
            raise BoardError(f"tessera #{i + 1}: manca sia 'id' sia le coordinate (q, r)")
        resource = normalise_resource(raw.get("resource") or raw.get("terrain"))
        number = raw.get("number")
        if number is not None:
            number = int(number)
        if hid in hexes:
            raise BoardError(f"tessera {hid} ripetuta")
        hexes[hid] = Hex(id=hid, resource=resource, number=number)

    ports = tuple(_port_from_dict(raw, geometry) for raw in data.get("ports", []))
    if not ports:
        ports = tuple(_ports_from_vertices(data, geometry))

    placements = tuple(
        Placement(
            player=int(raw["player"]),
            vertex=raw["vertex"],
            road_edge=raw.get("road_edge"),
            order=raw.get("order"),
        )
        for raw in data.get("placements", [])
    )

    board = Board(
        hexes=hexes,
        ports=ports,
        placements=placements,
        n_players=int(data.get("players", 4)),
        my_position=int(data.get("my_position", 1)),
        geometry=geometry,
    )
    board.validate(strict=strict)
    return board


def _id_from_axial(raw: dict[str, Any], geometry: Geometry) -> str | None:
    if "q" not in raw or "r" not in raw:
        return None
    from ..geometry import Axial

    coord = Axial(int(raw["q"]), int(raw["r"]))
    hid = geometry.hex_of_coord.get(coord)
    if hid is None:
        raise BoardError(f"coordinate ({coord.q}, {coord.r}) fuori dal tabellone")
    return hid


def _port_from_dict(raw: dict[str, Any], geometry: Geometry) -> Port:
    ratio = raw.get("ratio")
    if ratio is None and "type" in raw:
        ratio = 2 if str(raw["type"]).startswith("2") else 3
    ratio = int(ratio or 3)
    resource = normalise_resource(raw.get("resource")) if ratio == 2 else None

    edge_id = raw.get("edge") or raw.get("edge_id")
    if edge_id is None:
        vertices = raw.get("vertices")
        if not vertices or len(vertices) != 2:
            raise BoardError(f"porto senza 'edge' e senza coppia di vertici: {raw}")
        edge_id = geometry.edge_of_key.get(frozenset(vertices))
        if edge_id is None:
            raise BoardError(f"i vertici {vertices} non formano un lato")
    return Port(edge_id=edge_id, ratio=ratio, resource=resource)


def _ports_from_vertices(data: dict[str, Any], geometry: Geometry) -> list[Port]:
    """Fallback: ports declared inline on the vertices, as in KB D.1.

    A port occupies one coastal *edge*, so it shows up on two vertices. The
    coast is a closed ring, so every coastal vertex touches exactly two coastal
    edges: a port declared on a single vertex is therefore always ambiguous, and
    we refuse to guess. Declare it on both vertices of the edge, or use "edge".
    """
    declared: dict[str, dict[str, Any]] = {}
    for raw in data.get("vertices", []):
        port = raw.get("port")
        if port:
            declared[raw["id"]] = port
    if not declared:
        return []

    ports: list[Port] = []
    used: set[str] = set()

    for eid in geometry.coastal_edges:
        a, b = geometry.edge_vertices[eid]
        if a in declared and b in declared and _same_port(declared[a], declared[b]):
            ports.append(_port_from_dict(dict(declared[a], edge=eid), geometry))
            used.update((a, b))

    unpaired = sorted(set(declared) - used)
    if unpaired:
        raise BoardError(
            f"porto ambiguo su {unpaired}: ogni incrocio costiero tocca due lati "
            "costieri, quindi non si puo dedurre su quale sta il porto. Dichiaralo "
            "sul lato ('edge') oppure anche sull'incrocio gemello."
        )
    return ports


def _same_port(a: dict[str, Any], b: dict[str, Any]) -> bool:
    def key(spec: dict[str, Any]) -> tuple[Any, Any]:
        ratio = spec.get("ratio")
        if ratio is None and "type" in spec:
            ratio = 2 if str(spec["type"]).startswith("2") else 3
        return (int(ratio or 3), normalise_resource(spec.get("resource")))

    return key(a) == key(b)


def board_to_dict(board: Board) -> dict[str, Any]:
    geo = board.geometry
    return {
        "players": board.n_players,
        "my_position": board.my_position,
        "hexes": [
            {
                "id": hid,
                "q": geo.coord_of_hex[hid].q,
                "r": geo.coord_of_hex[hid].r,
                "resource": board.hexes[hid].resource,
                "number": board.hexes[hid].number,
            }
            for hid in geo.hex_ids
        ],
        "ports": [
            {
                "edge": p.edge_id,
                "ratio": p.ratio,
                "resource": p.resource,
                "vertices": list(geo.edge_vertices[p.edge_id]),
            }
            for p in board.ports
        ],
        "placements": [
            {
                "player": p.player,
                "vertex": p.vertex,
                "road_edge": p.road_edge,
                "order": p.order,
            }
            for p in board.placements
        ],
    }


def save_board(board: Board, path: str | Path) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(board_to_dict(board), fh, indent=2, ensure_ascii=False)
        fh.write("\n")
