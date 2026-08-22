"""A visual version of the advice: the board drawn, with the picks marked.

Text output is precise but slow to read across a table. This renders the same
Advice object as a self-contained HTML page: the board as an SVG, the
recommended junctions as numbered badges, the suggested roads as thick strokes,
and the planned partner as a dashed ring.

Terrain colours come from the physical board, so the drawing can be matched to
what is actually on the table without a legend lookup.
"""

from __future__ import annotations

import html

from . import constants as K
from .advisor import Advice, Recommendation
from .board import Board
from .geometry import hex_center, vertex_center

_RES = K.RESOURCE_LABEL_IT

TERRAIN = {
    K.WHEAT: "#E5B948",
    K.WOOD: "#2E6B3E",
    K.SHEEP: "#A9CE70",
    K.BRICK: "#C0632F",
    K.ORE: "#8892A0",
    K.DESERT: "#E0D2AC",
}
TERRAIN_INK = {
    K.WHEAT: "#4A3708",
    K.WOOD: "#EAF3EC",
    K.SHEEP: "#2A3B15",
    K.BRICK: "#FBEDE4",
    K.ORE: "#171C24",
    K.DESERT: "#4A3D1D",
}

SCALE = 56.0
PAD = 1.35


def _pt(model: tuple[float, float]) -> tuple[float, float]:
    return (model[0] * SCALE, model[1] * SCALE)


def _hex_points(board: Board, hex_id: str) -> str:
    geo = board.geometry
    pts = [_pt(vertex_center(geo.key_of_vertex[v])) for v in geo.hex_vertices[hex_id]]
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)


def _vertex_xy(board: Board, vertex_id: str) -> tuple[float, float]:
    return _pt(vertex_center(board.geometry.key_of_vertex[vertex_id]))


def _pip_dots(pips: int) -> str:
    return "·" * pips


def _board_svg(advice: Advice) -> str:
    board = advice.board
    geo = board.geometry
    parts: list[str] = []

    xs, ys = [], []
    for v in geo.vertex_ids:
        x, y = _vertex_xy(board, v)
        xs.append(x)
        ys.append(y)
    pad = PAD * SCALE
    minx, maxx = min(xs) - pad, max(xs) + pad
    miny, maxy = min(ys) - pad, max(ys) + pad

    # sea
    parts.append(
        f'<rect x="{minx:.0f}" y="{miny:.0f}" width="{maxx - minx:.0f}" '
        f'height="{maxy - miny:.0f}" rx="18" fill="var(--sea)"/>'
    )

    # tiles
    for hid in geo.hex_ids:
        tile = board.hexes[hid]
        fill = TERRAIN[tile.resource]
        ink = TERRAIN_INK[tile.resource]
        parts.append(
            f'<polygon points="{_hex_points(board, hid)}" fill="{fill}" '
            f'stroke="var(--coast)" stroke-width="2.5" stroke-linejoin="round"/>'
        )
        cx, cy = _pt(hex_center(geo.coord_of_hex[hid]))
        if tile.number is None:
            parts.append(
                f'<text class="tile-name" x="{cx:.1f}" y="{cy + 5:.1f}" '
                f'fill="{ink}">deserto</text>'
            )
            continue
        hot = tile.number in K.HIGH_NUMBERS
        parts.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="19" fill="var(--token)" '
            f'stroke="var(--token-edge)" stroke-width="1.5"/>'
        )
        parts.append(
            f'<text class="token-num{" hot" if hot else ""}" x="{cx:.1f}" '
            f'y="{cy + 1:.1f}">{tile.number}</text>'
        )
        parts.append(
            f'<text class="token-pips{" hot" if hot else ""}" x="{cx:.1f}" '
            f'y="{cy + 12:.1f}">{_pip_dots(tile.pips)}</text>'
        )
        parts.append(
            f'<text class="tile-name" x="{cx:.1f}" y="{cy + 30:.1f}" fill="{ink}">'
            f'{_RES[tile.resource]}</text>'
        )

    # ports
    for port in board.ports:
        a, b = geo.edge_vertices[port.edge_id]
        (ax, ay), (bx, by) = _vertex_xy(board, a), _vertex_xy(board, b)
        mx, my = (ax + bx) / 2, (ay + by) / 2
        nx, ny = mx, my
        length = (mx ** 2 + my ** 2) ** 0.5 or 1.0
        ox, oy = mx + nx / length * 30, my + ny / length * 30
        label = "3:1" if port.is_generic else "2:1"
        colour = "var(--port-generic)" if port.is_generic else TERRAIN[port.resource]
        parts.append(
            f'<line x1="{mx:.1f}" y1="{my:.1f}" x2="{ox:.1f}" y2="{oy:.1f}" '
            f'stroke="var(--port-line)" stroke-width="2"/>'
        )
        parts.append(
            f'<circle cx="{ox:.1f}" cy="{oy:.1f}" r="15" fill="{colour}" '
            f'stroke="var(--port-line)" stroke-width="1.5"/>'
        )
        parts.append(f'<text class="port-label" x="{ox:.1f}" y="{oy + 4:.1f}">{label}</text>')

    # roads and partner rings, drawn under the badges
    for rec in advice.recommendations:
        if rec.road:
            a, b = geo.edge_vertices[rec.road.edge]
            (ax, ay), (bx, by) = _vertex_xy(board, a), _vertex_xy(board, b)
            parts.append(
                f'<line class="road rank{rec.rank}" x1="{ax:.1f}" y1="{ay:.1f}" '
                f'x2="{bx:.1f}" y2="{by:.1f}"/>'
            )
        px, py = _vertex_xy(board, rec.partner)
        parts.append(
            f'<circle class="partner rank{rec.rank}" cx="{px:.1f}" cy="{py:.1f}" r="13"/>'
        )

    for rec in advice.recommendations:
        x, y = _vertex_xy(board, rec.vertex)
        parts.append(f'<circle class="badge rank{rec.rank}" cx="{x:.1f}" cy="{y:.1f}" r="16"/>')
        parts.append(f'<text class="badge-num" x="{x:.1f}" y="{y + 6:.1f}">{rec.rank}</text>')

    return (
        f'<svg viewBox="{minx:.0f} {miny:.0f} {maxx - minx:.0f} {maxy - miny:.0f}" '
        f'role="img" aria-label="Tabellone con le colonie consigliate">'
        + "".join(parts)
        + "</svg>"
    )


def _availability_meter(value: float) -> str:
    tone = "ok" if value >= 0.7 else "warn" if value >= 0.35 else "bad"
    return (
        f'<div class="meter {tone}"><span style="width:{value * 100:.0f}%"></span></div>'
        f'<span class="meter-value">{value * 100:.0f}%</span>'
    )


def _card(advice: Advice, rec: Recommendation) -> str:
    board = advice.board
    pair = rec.pair
    e = html.escape

    production = "".join(
        f'<div class="prod"><span class="dot" style="background:{TERRAIN[r]}"></span>'
        f"<span>{_RES[r]}</span><b>{pair.production.get(r, 0)}</b></div>"
        for r in K.RESOURCES
    )
    reasons = "".join(f"<li>{e(reason)}</li>" for reason in rec.reasons[:4])
    risks = "".join(f"<li>{e(risk)}</li>" for risk in rec.risks[:3])

    availability = ""
    if advice.turn_not_reached:
        availability = (
            '<div class="availability"><span class="k">Libero al tuo turno</span>'
            f"{_availability_meter(rec.availability)}</div>"
            '<div class="availability"><span class="k">Finisci qui</span>'
            f'<div class="meter neutral"><span style="width:{rec.landing * 100:.0f}%">'
            f'</span></div><span class="meter-value">{rec.landing * 100:.0f}%</span></div>'
        )

    road = ""
    if rec.road and rec.road.best:
        target = rec.road.best
        road = (
            '<div class="row"><span class="k">Strada</span>'
            f"<span class=\"v\">verso {e(board.vertex_label(target.vertex))} "
            f"<em>{target.pips} pip</em></span></div>"
        )

    fallback = ""
    if rec.fallbacks:
        items = ", ".join(
            f"{e(board.vertex_label(v))} ({w * 100:.0f}%)" for v, w in rec.fallbacks[:2]
        )
        fallback = f'<div class="row"><span class="k">Se salta</span><span class="v">{items}</span></div>'

    return f"""
<article class="card rank{rec.rank}">
  <header>
    <span class="rank-badge">{rec.rank}</span>
    <div>
      <h3>{e(board.vertex_label(rec.vertex))}</h3>
      <p class="sub">{rec.vertex_score.pips} pip &middot;
        {rec.vertex_score.cards_per_round:.2f} carte a giro &middot;
        S(v) {rec.vertex_score.score:.1f}</p>
    </div>
  </header>
  {availability}
  <div class="prods">{production}</div>
  <div class="rows">
    <div class="row"><span class="k">Coppia</span><span class="v">con
      {e(board.vertex_label(rec.partner))} &rarr; <em>{pair.pips} pip,
      {pair.resources_covered}/5 risorse</em></span></div>
    {road}
    {fallback}
    <div class="row"><span class="k">Archetipo</span><span class="v">{e(rec.archetype)}</span></div>
  </div>
  <div class="why"><h4>Perche</h4><ul>{reasons}</ul></div>
  {f'<div class="risk"><h4>Rischi</h4><ul>{risks}</ul></div>' if risks else ""}
</article>"""


def render_advice_html(advice: Advice, title: str | None = None) -> str:
    board = advice.board
    e = html.escape
    heading = title or f"Apertura, posizione {board.my_position}"

    warning = ""
    if advice.turn_not_reached:
        warning = (
            '<div class="notice"><b>Non e ancora il tuo turno.</b> '
            f"Mancano {advice.pending_opponent_picks} piazzamenti avversari prima del "
            f"tuo pick #{advice.context.next_pick}. Leggi la lista come un <b>ordine di "
            "priorita</b>: prendi la prima opzione ancora libera quando tocca a te. "
            "<i>Libero al tuo turno</i> e la probabilita che sopravviva; <i>finisci qui</i> "
            "e la probabilita che sia proprio quella che ti tocca.</div>"
        )

    scarcity = "".join(
        f'<div class="sc"><span class="dot" style="background:{TERRAIN[r]}"></span>'
        f"<span>{_RES[r]}</span><b>{int(advice.precomputed.scarcity[r]['pips'])}</b>"
        f"<i>{advice.precomputed.scarcity[r]['ratio']:.2f}&times;</i></div>"
        for r in sorted(K.RESOURCES, key=lambda x: advice.precomputed.scarcity[x]["ratio"])
    )

    cards = "".join(_card(advice, rec) for rec in advice.recommendations)

    return f"""<title>Apertura Catan</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700&family=Source+Sans+3:ital,wght@0,400;0,600;1,400&family=IBM+Plex+Mono:wght@500&display=swap">
<style>
:root {{
  --ground: #F7F5F0;
  --panel: #FFFFFF;
  --ink: #1C242C;
  --ink-soft: #5A6873;
  --line: #DDD8CE;
  --accent: #B3231D;
  --accent-soft: #F2DAD7;
  --sea: #2E7FB8;
  --coast: #F0E3C4;
  --token: #F6EFD9;
  --token-edge: #B9A87C;
  --token-ink: #26303A;
  --port-line: #E9DCBB;
  --port-generic: #EFE6CE;
  --ok: #2F7D4F;
  --warn: #B57515;
  --bad: #B3231D;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --ground: #131A21;
    --panel: #1B242D;
    --ink: #ECF1F5;
    --ink-soft: #93A3B0;
    --line: #2C3945;
    --accent: #F0655C;
    --accent-soft: #46201E;
    --sea: #17537C;
    --coast: #C7B78F;
    --token: #EDE4CB;
    --token-edge: #8A7A50;
    --token-ink: #26303A;
    --port-line: #A8996F;
    --port-generic: #D8CCAC;
    --ok: #5BB77E;
    --warn: #DDA43F;
    --bad: #F0655C;
  }}
}}
:root[data-theme="dark"] {{
  --ground: #131A21;
  --panel: #1B242D;
  --ink: #ECF1F5;
  --ink-soft: #93A3B0;
  --line: #2C3945;
  --accent: #F0655C;
  --accent-soft: #46201E;
  --sea: #17537C;
  --coast: #C7B78F;
  --token: #EDE4CB;
  --token-edge: #8A7A50;
  --token-ink: #26303A;
  --port-line: #A8996F;
  --port-generic: #D8CCAC;
  --ok: #5BB77E;
  --warn: #DDA43F;
  --bad: #F0655C;
}}

* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  background: var(--ground);
  color: var(--ink);
  font: 400 16px/1.55 "Source Sans 3", ui-sans-serif, system-ui, sans-serif;
  -webkit-font-smoothing: antialiased;
}}
.wrap {{ max-width: 1180px; margin: 0 auto; padding: 32px 20px 64px; }}

header.top {{ display: flex; flex-direction: column; gap: 6px; margin-bottom: 26px; }}
.eyebrow {{
  font: 600 12px/1 "IBM Plex Mono", ui-monospace, monospace;
  letter-spacing: .14em; text-transform: uppercase; color: var(--accent);
}}
h1 {{
  font: 700 clamp(28px, 4.4vw, 42px)/1.08 Archivo, ui-sans-serif, sans-serif;
  letter-spacing: -0.02em; margin: 0; text-wrap: balance;
}}
.lede {{ color: var(--ink-soft); margin: 0; max-width: 62ch; }}

.notice {{
  border-left: 3px solid var(--accent); background: var(--accent-soft);
  color: var(--ink); padding: 12px 16px; border-radius: 0 8px 8px 0;
  margin: 20px 0 6px; max-width: 72ch;
}}

.layout {{ display: grid; gap: 26px; grid-template-columns: 1fr; margin-top: 22px; }}
@media (min-width: 1000px) {{ .layout {{ grid-template-columns: minmax(0, 1.05fr) minmax(0, 1fr); align-items: start; }} }}

.boardpanel {{
  background: var(--panel); border: 1px solid var(--line);
  border-radius: 14px; padding: 14px; position: sticky; top: 18px;
}}
svg {{ width: 100%; height: auto; display: block; }}
.token-num {{
  font: 700 19px "Archivo", sans-serif; fill: var(--token-ink);
  text-anchor: middle; dominant-baseline: middle;
}}
.token-num.hot, .token-pips.hot {{ fill: #B3231D; }}
.token-pips {{
  font: 700 13px "IBM Plex Mono", monospace; fill: var(--token-ink);
  text-anchor: middle; letter-spacing: 1px;
}}
.tile-name {{
  font: 600 10px "Source Sans 3", sans-serif; text-anchor: middle;
  letter-spacing: .06em; text-transform: uppercase; opacity: .85;
}}
.port-label {{
  font: 600 11px "IBM Plex Mono", monospace; fill: #26303A; text-anchor: middle;
}}
.road {{ stroke: var(--accent); stroke-width: 9; stroke-linecap: round; opacity: .92; }}
.road.rank2 {{ stroke-width: 7; opacity: .6; }}
.road.rank3 {{ stroke-width: 6; opacity: .42; }}
.partner {{
  fill: none; stroke: var(--accent); stroke-width: 3; stroke-dasharray: 5 4; opacity: .85;
}}
.partner.rank2 {{ opacity: .55; }}
.partner.rank3 {{ opacity: .38; }}
.badge {{ fill: var(--accent); stroke: #FFF; stroke-width: 2.5; }}
.badge.rank2 {{ fill-opacity: .78; }}
.badge.rank3 {{ fill-opacity: .58; }}
.badge-num {{
  font: 700 16px Archivo, sans-serif; fill: #FFF; text-anchor: middle;
}}

.scarcity {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }}
.sc {{
  display: flex; align-items: center; gap: 6px; font-size: 13px;
  border: 1px solid var(--line); border-radius: 999px; padding: 4px 11px;
}}
.sc b {{ font-variant-numeric: tabular-nums; }}
.sc i {{ color: var(--ink-soft); font-style: normal; font-size: 12px;
        font-family: "IBM Plex Mono", monospace; }}
.dot {{ width: 9px; height: 9px; border-radius: 50%; display: inline-block; }}

.cards {{ display: flex; flex-direction: column; gap: 16px; }}
.card {{
  background: var(--panel); border: 1px solid var(--line); border-radius: 14px;
  padding: 18px 18px 16px;
}}
.card.rank1 {{ border-color: var(--accent); }}
.card header {{ display: flex; gap: 12px; align-items: flex-start; }}
.rank-badge {{
  flex: none; width: 30px; height: 30px; border-radius: 50%;
  background: var(--accent); color: #FFF; display: grid; place-items: center;
  font: 700 16px Archivo, sans-serif;
}}
.card.rank2 .rank-badge {{ opacity: .78; }}
.card.rank3 .rank-badge {{ opacity: .58; }}
.card h3 {{
  font: 600 19px/1.2 Archivo, sans-serif; margin: 2px 0 2px;
  letter-spacing: -0.01em; text-wrap: balance;
}}
.sub {{
  margin: 0; color: var(--ink-soft); font-size: 13px;
  font-family: "IBM Plex Mono", monospace; font-variant-numeric: tabular-nums;
}}

.availability {{ display: flex; align-items: center; gap: 10px; margin: 14px 0 4px; }}
.availability .k {{ font-size: 12px; text-transform: uppercase; letter-spacing: .08em;
                    color: var(--ink-soft); white-space: nowrap; }}
.meter {{ flex: 1; height: 7px; border-radius: 99px; background: var(--line); overflow: hidden; }}
.meter span {{ display: block; height: 100%; border-radius: 99px; background: var(--ok); }}
.meter.warn span {{ background: var(--warn); }}
.meter.bad span {{ background: var(--bad); }}
.meter.neutral span {{ background: var(--ink-soft); }}
.meter-value {{ font: 500 13px "IBM Plex Mono", monospace; font-variant-numeric: tabular-nums; }}

.prods {{ display: flex; flex-wrap: wrap; gap: 6px; margin: 12px 0 4px; }}
.prod {{
  display: flex; align-items: center; gap: 5px; font-size: 13px;
  background: var(--ground); border-radius: 7px; padding: 3px 9px;
}}
.prod b {{ font-variant-numeric: tabular-nums; }}

.rows {{ display: flex; flex-direction: column; gap: 6px; margin: 12px 0 4px; }}
.row {{ display: flex; gap: 10px; font-size: 14px; align-items: baseline; }}
.row .k {{
  flex: none; width: 84px; font-size: 11px; text-transform: uppercase;
  letter-spacing: .08em; color: var(--ink-soft);
}}
.row .v em {{ font-style: normal; font-weight: 600; }}

.why, .risk {{ margin-top: 12px; }}
.why h4, .risk h4 {{
  font: 600 11px "IBM Plex Mono", monospace; letter-spacing: .12em;
  text-transform: uppercase; margin: 0 0 5px; color: var(--ink-soft);
}}
.risk h4 {{ color: var(--accent); }}
.why ul, .risk ul {{ margin: 0; padding-left: 17px; font-size: 14px; }}
.why li, .risk li {{ margin-bottom: 3px; }}

footer {{
  margin-top: 34px; padding-top: 16px; border-top: 1px solid var(--line);
  color: var(--ink-soft); font-size: 13px; max-width: 74ch;
}}
</style>

<div class="wrap">
  <header class="top">
    <span class="eyebrow">{e(advice.context.describe())}</span>
    <h1>{e(heading)}</h1>
    <p class="lede">Le tre aperture migliori su questo tabellone. Il numero sul
      tabellone e la colonia da piazzare, il cerchio tratteggiato il partner
      previsto, la linea spessa la strada consigliata.</p>
  </header>
  {warning}
  <div class="layout">
    <div class="boardpanel">
      {_board_svg(advice)}
      <div class="scarcity">{scarcity}</div>
    </div>
    <div class="cards">{cards}</div>
  </div>
  <footer>
    I punteggi sono in pip-equivalenti: 1 punto = 1 pip = 1/36 di carta per tiro.
    Il pip grezzo resta sempre accanto al punteggio, per il controllo a occhio.
    Le percentuali vengono dalla simulazione dei pick avversari, non da una stima fissa.
  </footer>
</div>
"""
