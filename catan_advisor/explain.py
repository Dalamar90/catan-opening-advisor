"""The output format of KB D.3.

Always at least three options, each with reasons, risks, a road, a pair plan and
a fallback -- because in a draft plan A falls through often.
"""

from __future__ import annotations

from . import constants as K
from .advisor import Advice, Recommendation
from .report import render_opponents

_RES = K.RESOURCE_LABEL_IT
_MEDALS = ["1)", "2)", "3)", "4)", "5)"]


def render_advice(advice: Advice, width: int = 78) -> str:
    board = advice.board
    context = advice.context

    if context.next_pick is None:
        return "Hai gia piazzato entrambe le colonie: non c'e nessun pick da consigliare."
    if not advice.recommendations:
        return "Nessun incrocio disponibile su cui dare un consiglio."

    header = [
        "=" * width,
        f"CONSIGLIO DI APERTURA -- {board.n_players} giocatori, tu sei P{board.my_position}",
        f"{context.describe()}",
    ]
    if advice.existing:
        header.append(
            "Le tue colonie: "
            + ", ".join(f"{v} [{board.vertex_label(v)}]" for v in advice.existing)
        )
    header.append("=" * width)

    blocks = ["\n".join(header)]
    if advice.turn_not_reached:
        n = advice.pending_opponent_picks
        blocks.append(
            "ATTENZIONE: NON E ANCORA IL TUO TURNO\n\n"
            f"   Mancano {n} piazzamenti avversari prima del tuo pick "
            f"#{advice.context.next_pick}, e non sono stati inseriti.\n"
            "   Quello che segue e quindi un PIANO, non una decisione: gli incroci\n"
            "   consigliati potrebbero essere gia presi quando tocchera a te.\n"
            "   Per ogni opzione trovi la probabilita che sia ancora libera.\n"
            "   Appena i tuoi avversari piazzano, aggiungili in 'placements' e\n"
            "   rilancia: il consiglio diventa affidabile."
        )
    blocks.append(_render_board_state(advice))
    if advice.profiles:
        blocks.append(render_opponents(advice.profiles, _market_of(advice)))
    for rec in advice.recommendations:
        blocks.append(_render_recommendation(advice, rec, width))
    blocks.append(_render_closing(advice))
    return "\n\n".join(blocks) + "\n"


def _market_of(advice: Advice):
    if advice.recommendations:
        return advice.recommendations[0].pair.market
    return None


def _render_board_state(advice: Advice) -> str:
    pre = advice.precomputed
    scarce = sorted(K.RESOURCES, key=lambda r: pre.scarcity[r]["ratio"])
    lines = ["QUESTO TABELLONE", ""]
    lines.append(
        "   Scarse: "
        + ", ".join(
            f"{_RES[r]} ({int(pre.scarcity[r]['pips'])} pip, "
            f"{pre.scarcity[r]['ratio']:.2f}x l'atteso)"
            for r in scarce[:2]
        )
    )
    lines.append(
        "   Abbondanti: "
        + ", ".join(
            f"{_RES[r]} ({int(pre.scarcity[r]['pips'])} pip, "
            f"{pre.scarcity[r]['ratio']:.2f}x)"
            for r in scarce[-2:]
        )
    )
    if advice.simulation is not None:
        gone = [v for v, p in advice.simulation.survival.items() if p < 0.5]
        contested = ", ".join(
            f"{v} ({n / advice.simulation.samples:.0%})"
            for v, n in advice.simulation.opponent_picks.most_common(4)
        )
        lines.append(
            f"   Attesa simulata: ~{len(gone)} incroci spariranno prima del tuo "
            f"prossimo pick. Piu contesi: {contested}"
        )
    return "\n".join(lines)


def _render_recommendation(advice: Advice, rec: Recommendation, width: int) -> str:
    board = advice.board
    pair = rec.pair
    medal = _MEDALS[rec.rank - 1] if rec.rank <= len(_MEDALS) else f"{rec.rank})"

    lines = [
        f"{medal} RACCOMANDAZIONE #{rec.rank} -- {rec.vertex} "
        f"[{board.vertex_label(rec.vertex)}]",
        f"   Pip: {rec.vertex_score.pips} (pesati {rec.vertex_score.weighted_pips:.1f})"
        f"  |  S(v) {rec.vertex_score.score:.2f}"
        f"  |  {rec.vertex_score.cards_per_round:.2f} carte/giro"
        f"  |  risorse: {_names(rec.vertex_score.resources)}",
        "",
    ]
    if advice.turn_not_reached:
        verdict = (
            "molto probabile" if rec.availability >= 0.7
            else "a rischio" if rec.availability >= 0.35
            else "difficile che regga"
        )
        lines.append(
            f"   DISPONIBILE AL TUO TURNO: {rec.availability:.0%} ({verdict})"
        )
        lines.append("")
    lines.append("   PERCHE:")
    lines += [f"   - {reason}" for reason in rec.reasons]

    if rec.risks:
        lines += ["", "   RISCHI:"]
        lines += [f"   - {risk}" for risk in rec.risks]

    if rec.road:
        lines += ["", f"   STRADA CONSIGLIATA: {rec.road.edge}, verso {rec.road.towards}"]
        best = rec.road.best
        if best:
            lines.append(
                f"      prenota {best.vertex} [{board.vertex_label(best.vertex)}], "
                f"{best.pips} pip, sopravvivenza stimata {best.survival:.0%}"
            )
            lines.append(
                f"      quell'incrocio varrebbe {best.marginal:.1f} per questo "
                f"portafoglio (pip pesati piu la copertura che sblocca)"
            )
        for contribution in rec.road.breakdown.contributions:
            if contribution.key == "reservation":
                continue  # already said, one line above
            lines.append(f"      {contribution}")
        if rec.road_alternative and rec.road_alternative.best:
            alt = rec.road_alternative
            lines.append(
                f"      alternativa: {alt.edge} verso {alt.towards} "
                f"(prenota {alt.best.vertex}, {alt.best.pips} pip)"
            )

    lines += ["", "   PIANO DI COPPIA:"]
    if advice.is_first_pick:
        lines.append(
            f"      partner previsto {rec.partner} [{board.vertex_label(rec.partner)}], "
            f"libero nel {rec.plan_probability:.0%} delle simulazioni"
        )
    else:
        lines.append(
            f"      insieme alla tua {rec.partner} [{board.vertex_label(rec.partner)}]"
        )
    lines.append(
        f"      coppia: {pair.pips} pip ({pair.verdict()}), "
        f"{pair.resources_covered}/5 risorse, "
        f"{pair.cards_per_round:.2f} carte a giro, S={pair.score:.2f}"
    )
    lines.append(f"      produzione: {_production_table(pair.production)}")
    if rec.fallbacks:
        lines.append(
            "      fallback: "
            + ", ".join(
                f"{v} [{board.vertex_label(v)}] {w:.0%}" for v, w in rec.fallbacks[:3]
            )
        )
    elif advice.is_first_pick:
        lines.append("      fallback: nessuna alternativa credibile, piano fragile")

    lines += ["", f"   ARCHETIPO ABILITATO: {rec.archetype}"]
    return "\n".join(lines)


def _render_closing(advice: Advice) -> str:
    lines = ["NOTE", ""]
    lines.append(
        "   I punteggi sono in pip-equivalenti: 1 punto = 1 pip = 1/36 di carta "
        "per tiro. Il pip grezzo e sempre indicato accanto, per il controllo a occhio."
    )
    if advice.is_first_pick and advice.context.waiting_picks:
        lines.append(
            f"   Le probabilita del piano vengono dalla simulazione dei "
            f"{advice.context.waiting_picks} pick avversari di attesa, non da una stima fissa."
        )
    if not advice.profiles:
        lines.append(
            "   Nessun piazzamento avversario inserito: il mercato degli scambi "
            "(KB C.3) non e stato considerato. Aggiungili in 'placements' per "
            "avere anche monopoli e risorse sature."
        )
    return "\n".join(lines)


def _names(resources) -> str:
    return ", ".join(_RES[r] for r in resources) if resources else "nessuna"


def _production_table(production: dict[str, int]) -> str:
    return "  ".join(f"{_RES[r]} {production.get(r, 0)}" for r in K.RESOURCES)
