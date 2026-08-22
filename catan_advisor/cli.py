"""Command line entry point.

M1 exposes only what M1 can honestly do: build or read a board, check it is
legal, and run the pre-computation of KB B.6. The advice commands arrive with
M2 to M5.
"""

from __future__ import annotations

import argparse
import sys

from .board import Board, BoardError
from .boardio import board_to_dict, load_board, random_board, save_board
from .config import load_config
from .precompute import precompute
from .report import (
    render_board_map,
    render_precompute,
    render_vertex_explanation,
    render_vertex_scores,
    render_pair_explanation,
    render_pair_scores,
)
from .scoring import best_pairs, score_all, score_pair, score_vertex


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

    if args.command == "precompute":
        cfg = load_config(args.config)
        print(render_precompute(precompute(board, cfg), top_n=args.top))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
