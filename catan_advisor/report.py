"""Italian text rendering of the pre-computation.

Rule kept throughout the project: the plain pip count is always printed next to
any weighted or derived number. The weighted score is the model's opinion, the
pip count is the fact you can check by eye at the table.
"""

from __future__ import annotations

from . import constants as K
from .board import Board
from .precompute import Precompute, VertexSummary

_RES = K.RESOURCE_LABEL_IT


def render_board_map(board: Board) -> str:
    """The 3-4-5-4-3 rows, so the ids can be matched against a photo."""
    geo = board.geometry
    lines = ["TABELLONE (righe da nord a sud, id in ordine di lettura)", ""]
    width = 22
    for row in geo.hex_rows:
        cells = [f"{hid} {board.hexes[hid]}".ljust(width) for hid in row]
        pad = " " * (width // 2 * (5 - len(row)))
        lines.append(pad + " ".join(cells).rstrip())
    return "\n".join(lines)


def render_scarcity(pre: Precompute) -> str:
    lines = [
        "1. SCARSITA DELLE RISORSE SU QUESTO TABELLONE",
        "",
        f"   {'risorsa':<10} {'pip':>4} {'quota':>7} {'attesa':>7} {'scost.':>8} {'peso':>7}",
        f"   {'-' * 10} {'-' * 4} {'-' * 7} {'-' * 7} {'-' * 8} {'-' * 7}",
    ]
    for resource in K.RESOURCES:
        row = pre.scarcity[resource]
        lines.append(
            f"   {_RES[resource]:<10} {int(row['pips']):>4} "
            f"{row['quota'] * 100:>6.1f}% {row['expected'] * 100:>6.1f}% "
            f"{row['deviation'] * 100:>+7.1f}% {row['weight_final']:>7.2f}"
        )
    lines.append(f"   {'totale':<10} {sum(pre.board.pips_by_resource.values()):>4}")
    lines.append("")

    scarce = sorted(K.RESOURCES, key=lambda r: pre.scarcity[r]["ratio"])
    poor, rich = scarce[0], scarce[-1]
    lines.append(
        f"   Piu scarsa del previsto: {_RES[poor]} "
        f"({pre.scarcity[poor]['ratio']:.2f}x la quota attesa, peso {pre.scarcity[poor]['weight_final']:.2f})."
    )
    lines.append(
        f"   Piu abbondante: {_RES[rich]} "
        f"({pre.scarcity[rich]['ratio']:.2f}x, peso {pre.scarcity[rich]['weight_final']:.2f})."
    )

    clustered = [r for r, c in pre.concentration.items() if c >= 0.15]
    for resource in clustered:
        if pre.scarcity[resource]["ratio"] < 1.0:
            lines.append(
                f"   ATTENZIONE: {_RES[resource]} e scarso E concentrato "
                f"(indice {pre.concentration[resource]:+.2f}): chi occupa quella zona "
                "ne ha il monopolio per tutta la partita."
            )
    return "\n".join(lines)


def _vertex_line(pre: Precompute, rank: int, s: VertexSummary) -> str:
    tiles = pre.board.vertex_label(s.vertex)
    cards = s.cards_per_round(pre.board.n_players)
    flag = "" if s.legal else "  (occupato/bloccato)"
    return (
        f"   {rank:>2}. {s.vertex}  pip {s.pips:>2}  pesati {s.weighted_pips:>5.1f}  "
        f"{cards:.2f} carte/giro  [{tiles}]{flag}"
    )


def render_top_vertices(pre: Precompute, n: int = 10) -> str:
    lines = [f"2. TOP {n} INCROCI (pip grezzi; il punteggio S(v) completo arriva in M2)", ""]
    for i, s in enumerate(pre.top(n), start=1):
        lines.append(_vertex_line(pre, i, s))
    lines.append("")
    lines.append("   Stessa lista ordinata per pip PESATI (scarsita di questo tabellone):")
    for i, s in enumerate(pre.top_weighted(n), start=1):
        lines.append(_vertex_line(pre, i, s))
    return "\n".join(lines)


def render_hot_zones(pre: Precompute) -> str:
    lines = ["3. ZONE CALDE (densita di pip nel vicinato di una tessera)", ""]
    for i, zone in enumerate(pre.hot_zones, start=1):
        tiles = ", ".join(f"{h}({pre.board.hexes[h]})" for h in zone.hexes)
        lines.append(
            f"   {i}. attorno a {zone.center_hex}: {zone.pips} pip su "
            f"{len(zone.hexes)} tessere, miglior incrocio {zone.best_vertex} "
            f"({zone.best_vertex_pips} pip)"
        )
        lines.append(f"      {tiles}")
    return "\n".join(lines)


def render_ports(pre: Precompute) -> str:
    lines = ["4. MAPPA DEI PORTI", ""]
    for info in sorted(pre.ports, key=lambda p: (-p.served_pips, p.edge)):
        note = ""
        if info.resource:
            note = (
                f"  <- alimentato dalla sua risorsa ({info.self_served} pip)"
                if info.natural
                else f"  (solo {info.self_served} pip della sua risorsa qui accanto)"
            )
        lines.append(
            f"   {info.label:<20} {info.vertices[0]}/{info.vertices[1]}  "
            f"produzione sugli incroci: {info.served_pips:>2} pip{note}"
        )
    lines.append("")
    lines.append(
        "   Promemoria KB B.5: un porto senza produzione e una casella sprecata, "
        "e al primo pick non si prende quasi mai."
    )
    return "\n".join(lines)


def render_draft_context(pre: Precompute) -> str:
    board = pre.board
    first, second = K.pick_numbers(board.my_position, board.n_players)
    k = K.waiting_picks(board.my_position, board.n_players)
    erosion = pre.config.get("draft.erosion_rate", 2.5)
    burned = k * erosion

    lines = [
        "5. CONTESTO DI DRAFT",
        "",
        f"   Giocatori: {board.n_players}   Posizione: P{board.my_position}   "
        f"Pick: #{first} e #{second}   Pick di attesa k = {k}",
        f"   Incroci liberi con almeno {pre.strong_threshold} pip: {pre.strong_vertex_count}",
    ]
    if k == 0:
        lines.append(
            "   I tuoi due pick sono consecutivi: pianificali come un pacchetto unico, "
            "e punta alla copertura 5/5 (KB C.2)."
        )
    else:
        lines.append(
            f"   Stima grezza: ~{burned:.0f} incroci di qualita spariranno prima del tuo "
            f"pick #{second} (erosion_rate {erosion})."
        )
        if pre.strong_vertex_count > burned:
            lines.append(
                "   -> Puoi permetterti un primo pick egoista (massimo pip) e sistemare "
                "la complementarita dopo (KB C.1)."
            )
        else:
            lines.append(
                "   -> Gia adesso devi prendere un incrocio che funzioni come META di una "
                "coppia realistica: il meglio non tornera (KB C.1)."
            )
        lines.append(
            "   (in M4 questa stima verra sostituita dalla simulazione greedy dei pick avversari)"
        )
    return "\n".join(lines)


def render_precompute(pre: Precompute, top_n: int = 10) -> str:
    board = pre.board
    header = [
        "=" * 78,
        f"PRE-CALCOLO -- {board.n_players} giocatori, tu sei P{board.my_position}",
        f"pip totali {board.total_pips}   tessere {len(board.hexes)}   "
        f"incroci {len(board.geometry.vertex_ids)}   lati {len(board.geometry.edge_ids)}",
        "=" * 78,
    ]
    blocks = [
        "\n".join(header),
        render_board_map(board),
        render_scarcity(pre),
        render_top_vertices(pre, top_n),
        render_hot_zones(pre),
        render_ports(pre),
        render_draft_context(pre),
    ]
    if pre.warnings:
        blocks.append("AVVISI\n" + "\n".join(f"   - {w}" for w in pre.warnings))
    return "\n\n".join(blocks) + "\n"


# --- M2: single junction scores --------------------------------------------


def render_vertex_scores(scores: list, n: int = 10, title: str | None = None) -> str:
    lines = [title or f"TOP {n} INCROCI per S(v)", ""]
    for i, s in enumerate(scores[:n], start=1):
        lines.append(f"   {i:>2}. {s.headline()}")
    lines.append("")
    lines.append(
        "   S(v) e in pip-equivalenti: 1 punto = 1 pip = 1/36 di carta per tiro."
    )
    return "\n".join(lines)


def render_vertex_explanation(score) -> str:
    prod = ", ".join(
        f"{K.RESOURCE_LABEL_IT[r]} {p}" for r, p in sorted(score.production.items())
    )
    lines = [
        f"INCROCIO {score.vertex}  [{score.label}]",
        "",
        f"   S(v) = {score.score:.2f}",
        f"   pip grezzi {score.pips}   pesati {score.weighted_pips:.1f}   "
        f"{score.cards_per_roll:.3f} carte/tiro   {score.cards_per_round:.2f} carte/giro",
        f"   produzione: {prod or 'nessuna'}",
        f"   numeri: {', '.join(map(str, score.numbers)) or 'nessuno'}",
    ]
    if not score.legal:
        lines.append("   NON DISPONIBILE: occupato o bloccato dalla distance rule")
    lines += ["", "   DA DOVE VIENE IL PUNTEGGIO", score.breakdown.render()]
    if score.expansion_targets:
        lines += ["", "   BERSAGLI DI ESPANSIONE"]
        for vertex, distance, pips in score.expansion_targets:
            lines.append(f"      {vertex} a {distance} strade, {pips} pip")
    return "\n".join(lines)


# --- M3: pairs --------------------------------------------------------------


def render_pair_scores(pairs: list, n: int = 5, title: str | None = None) -> str:
    lines = [title or f"TOP {n} COPPIE", ""]
    for i, p in enumerate(pairs[:n], start=1):
        lines.append(f"   {i:>2}. {p.headline()}")
        lines.append(f"       {p.board.vertex_label(p.a)}")
        lines.append(f"       {p.board.vertex_label(p.b)}")
    lines.append("")
    lines.append("   [!] = almeno un vincolo hard violato (KB B.4)")
    return "\n".join(lines)


def render_pair_explanation(pair) -> str:
    prod = "  ".join(
        f"{K.RESOURCE_LABEL_IT[r]:<9}{pair.production.get(r, 0):>2} pip"
        for r in K.RESOURCES
    )
    lines = [
        f"COPPIA {pair.a} + {pair.b}",
        f"   {pair.a}: {pair.board.vertex_label(pair.a)}",
        f"   {pair.b}: {pair.board.vertex_label(pair.b)}",
        "",
        f"   S = {pair.score:.2f}   pip {pair.pips} ({pair.verdict()})",
        f"   {pair.cards_per_roll:.3f} carte/tiro   {pair.cards_per_round:.2f} carte/giro",
        f"   copertura {pair.resources_covered}/5   "
        f"{pair.distinct_tiles} tessere distinte   "
        f"{len(set(pair.numbers))} numeri distinti",
        "",
        "   PRODUZIONE",
        f"   {prod}",
    ]
    if pair.violations:
        lines += ["", "   VINCOLI HARD VIOLATI (KB B.4)"]
        lines += [f"      [!] {v}" for v in pair.violations]
    if pair.warnings:
        lines += ["", "   AVVISI (anti-pattern KB D.5)"]
        lines += [f"      - {w}" for w in pair.warnings]
    lines += ["", "   DA DOVE VIENE IL PUNTEGGIO", pair.breakdown.render()]
    if pair.expansion_targets:
        lines += ["", "   ESPANSIONE"]
        for t in pair.expansion_targets:
            lines.append(f"      {t.vertex} a {t.distance} strade, {t.pips} pip")
    return "\n".join(lines)
