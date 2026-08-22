"""Command line entry point.

`advise` is the command that matters: it produces the full recommendation of
KB D.3. The others expose one layer each, which is what makes the model
inspectable -- precompute (B.6), score (B.3), pair (B.4), draft (C.1 to C.4).
"""

from __future__ import annotations

import argparse
import sys

from .advisor import advise
from .board import Board, BoardError
from .boardio import board_to_dict, load_board, random_board, save_board
from .config import load_config
from .explain import render_advice
from .render_html import render_advice_html
from .precompute import precompute
from .report import (
    render_board_map,
    render_precompute,
    render_vertex_explanation,
    render_vertex_scores,
    render_pair_explanation,
    render_pair_scores,
    render_draft_header,
    render_first_pick_options,
    render_opponents,
    render_roads,
)
from .roads import best_roads
from .scoring import best_pairs, score_all, score_pair, score_vertex
from .scoring.draft import (
    draft_context,
    erosion_estimate,
    evaluate_first_pick,
    simulate_opponents,
)
from .scoring.market import my_placements, profile_opponents


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", help="percorso di un config.yaml alternativo")
    parser.add_argument("--players", type=int, choices=(3, 4), help="numero di giocatori")
    parser.add_argument("--position", type=int, help="la tua posizione nel giro (1-based)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="catan-advisor",
        description="Advisor per la fase di apertura di Catan (gioco base, 3-4 giocatori).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_new = sub.add_parser("newboard", help="genera un tabellone casuale legale")
    p_new.add_argument("--seed", type=int, help="seme per la generazione")
    p_new.add_argument("--unbalanced", action="store_true", help="permetti 6 e 8 adiacenti")
    p_new.add_argument("-o", "--output", help="scrivi il JSON su file")
    _add_common(p_new)

    p_val = sub.add_parser("validate", help="verifica che un tabellone sia legale")
    p_val.add_argument("board", help="file JSON del tabellone")
    _add_common(p_val)

    p_map = sub.add_parser("map", help="stampa il tabellone in righe 3-4-5-4-3")
    p_map.add_argument("board", help="file JSON del tabellone")
    _add_common(p_map)

    p_pre = sub.add_parser("precompute", help="pre-calcolo obbligatorio (KB B.6)")
    p_pre.add_argument("board", help="file JSON del tabellone")
    p_pre.add_argument("--top", type=int, default=10, help="quanti incroci mostrare")
    _add_common(p_pre)

    p_score = sub.add_parser("score", help="punteggio S(v) dei singoli incroci (KB B.3)")
    p_score.add_argument("board", help="file JSON del tabellone")
    p_score.add_argument("--top", type=int, default=10, help="quanti incroci mostrare")
    p_score.add_argument(
        "--explain", metavar="VERTICE",
        help="mostra il breakdown completo di un incrocio, es. v26",
    )
    p_score.add_argument(
        "--all", action="store_true",
        help="includi anche gli incroci gia occupati o bloccati",
    )
    _add_common(p_score)

    p_pair = sub.add_parser("pair", help="valutazione della coppia di colonie (KB B.4)")
    p_pair.add_argument("board", help="file JSON del tabellone")
    p_pair.add_argument("--top", type=int, default=5, help="quante coppie mostrare")
    p_pair.add_argument(
        "--first", metavar="VERTICE",
        help="fissa la prima colonia e cerca il partner migliore (secondo pick)",
    )
    p_pair.add_argument(
        "--explain", metavar="A,B",
        help="breakdown completo di una coppia, es. v18,v26",
    )
    _add_common(p_pair)

    p_draft = sub.add_parser(
        "draft", help="consiglio nel contesto del draft: avversari, attesa, strada (KB C)"
    )
    p_draft.add_argument("board", help="file JSON del tabellone")
    p_draft.add_argument("--top", type=int, default=3, help="quante opzioni mostrare")
    p_draft.add_argument("--samples", type=int, help="campioni di simulazione")
    _add_common(p_draft)

    p_advise = sub.add_parser(
        "advise", help="il consiglio completo nel formato della KB D.3"
    )
    p_advise.add_argument("board", help="file JSON del tabellone")
    p_advise.add_argument(
        "--options", type=int, default=3, help="quante raccomandazioni (minimo 3)"
    )
    p_advise.add_argument("--samples", type=int, help="campioni di simulazione")
    p_advise.add_argument(
        "--html", metavar="FILE",
        help="scrivi anche una pagina HTML con il tabellone disegnato",
    )
    _add_common(p_advise)

    return parser


def _load(args) -> Board:
    if getattr(args, "command", None) == "newboard":
        board = random_board(seed=args.seed, balanced=not args.unbalanced)
    else:
        board = load_board(args.board, strict=args.command != "validate")
    if args.players:
        board.n_players = args.players
    if args.position:
        board.my_position = args.position
    if board.my_position > board.n_players:
        raise BoardError(
            f"posizione {board.my_position} impossibile con {board.n_players} giocatori"
        )
    return board


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        board = _load(args)
    except (BoardError, OSError) as exc:
        print(f"errore: {exc}", file=sys.stderr)
        return 2

    if args.command == "newboard":
        if args.output:
            save_board(board, args.output)
            print(f"tabellone scritto in {args.output}")
        else:
            import json

            print(json.dumps(board_to_dict(board), indent=2, ensure_ascii=False))
        return 0

    if args.command == "validate":
        problems = board.validate(strict=False)
        if problems:
            print("TABELLONE NON VALIDO")
            for p in problems:
                print(f"  - {p}")
            return 1
        print(
            f"tabellone valido: {len(board.hexes)} tessere, {board.total_pips} pip, "
            f"{len(board.ports)} porti, {len(board.placements)} colonie piazzate"
        )
        for w in board.warnings():
            print(f"  avviso: {w}")
        return 0

    if args.command == "map":
        print(render_board_map(board))
        return 0

    if args.command == "score":
        cfg = load_config(args.config)
        if args.explain:
            if args.explain not in board.geometry.vertex_ids:
                print(f"errore: incrocio sconosciuto {args.explain}", file=sys.stderr)
                return 2
            print(render_vertex_explanation(score_vertex(board, args.explain, cfg)))
            return 0
        scores = score_all(board, cfg, legal_only=not args.all)
        print(render_vertex_scores(scores, args.top))
        return 0

    if args.command == "pair":
        cfg = load_config(args.config)
        if args.explain:
            try:
                a, b = [v.strip() for v in args.explain.split(",")]
            except ValueError:
                print("errore: usa --explain v18,v26", file=sys.stderr)
                return 2
            unknown = [v for v in (a, b) if v not in board.geometry.vertex_ids]
            if unknown:
                print(f"errore: incroci sconosciuti {unknown}", file=sys.stderr)
                return 2
            if b in board.geometry.vertex_neighbours[a]:
                print(
                    f"errore: {a} e {b} sono adiacenti, la distance rule vieta la coppia",
                    file=sys.stderr,
                )
                return 2
            print(render_pair_explanation(score_pair(board, a, b, cfg)))
            return 0
        if args.first and args.first not in board.geometry.vertex_ids:
            print(f"errore: incrocio sconosciuto {args.first}", file=sys.stderr)
            return 2
        pairs = best_pairs(board, cfg, first=args.first)
        title = (
            f"MIGLIORI PARTNER PER {args.first}" if args.first else f"TOP {args.top} COPPIE"
        )
        print(render_pair_scores(pairs, args.top, title))
        return 0

    if args.command == "advise":
        cfg = load_config(args.config)
        advice = advise(board, cfg, limit=args.options, samples=args.samples)
        print(render_advice(advice))
        if args.html:
            with open(args.html, "w", encoding="utf-8") as fh:
                fh.write(render_advice_html(advice))
            print(f"pagina scritta in {args.html}")
        return 0

    if args.command == "draft":
        cfg = load_config(args.config)
        context = draft_context(board)
        profiles = profile_opponents(board)
        mine = my_placements(board)
        blocks = []

        if context.next_pick is None:
            print("Hai gia piazzato entrambe le colonie: non c'e nessun pick da consigliare.")
            return 0

        if context.is_first_pick:
            options = evaluate_first_pick(board, cfg, samples=args.samples)
            if not options:
                print("errore: nessun incrocio disponibile", file=sys.stderr)
                return 2
            best = options[0]
            # The wait that matters starts *after* I take my pick: simulating the
            # board as it stands now would simulate zero opponent picks.
            simulation = simulate_opponents(
                board, cfg, my_choice=best.vertex, samples=args.samples
            )
            blocks.append(
                render_draft_header(
                    context,
                    simulation,
                    erosion_estimate(board, cfg),
                    board,
                    int(cfg.get('report.strong_vertex_pips', 10)),
                )
            )
            blocks.append(render_opponents(profiles))
            blocks.append(render_first_pick_options(options, board, args.top))
            roads = best_roads(
                board, best.vertex, best.plan.production, cfg, simulation.survival
            )
            blocks.append(
                render_roads(roads, board, args.top)
                + f"\n\n   (strade calcolate per {best.vertex}, la raccomandazione #1;"
                + f" la sopravvivenza e stimata sui {context.waiting_picks} pick di attesa)"
            )
        else:
            blocks.append(render_draft_header(context))
            blocks.append(render_opponents(profiles))
            first = mine[0] if mine else None
            if first is None:
                print(
                    "errore: e il tuo secondo pick ma non trovo la tua prima colonia. "
                    f"Aggiungi un placement con player={board.my_position}.",
                    file=sys.stderr,
                )
                return 2
            pairs = best_pairs(board, cfg, first=first)
            blocks.append(
                render_pair_scores(
                    pairs, args.top, f"SECONDO PICK: migliori partner per {first}"
                )
            )
            if pairs:
                best = pairs[0]
                second = best.b if best.a == first else best.a
                # No opponent picks left before the game starts, so nothing to
                # discount: the road is judged on the target alone.
                roads = best_roads(board, second, best.production, cfg)
                blocks.append(
                    render_roads(roads, board, args.top)
                    + f"\n\n   (strade calcolate per {second}, la nuova colonia)"
                )
        print("\n\n".join(blocks))
        return 0

    if args.command == "precompute":
        cfg = load_config(args.config)
        print(render_precompute(precompute(board, cfg), top_n=args.top))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
