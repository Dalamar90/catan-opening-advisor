"""The CLI must behave on broken input, not just on good input."""

import json

import pytest

from catan_advisor.boardio import board_to_dict, random_board
from catan_advisor.cli import main


@pytest.fixture
def board_file(tmp_path):
    path = tmp_path / "board.json"
    path.write_text(json.dumps(board_to_dict(random_board(seed=7))), encoding="utf-8")
    return str(path)


@pytest.fixture
def broken_file(tmp_path):
    data = board_to_dict(random_board(seed=7))
    data["hexes"].pop()
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def test_newboard_writes_a_valid_file(tmp_path, capsys):
    out = tmp_path / "new.json"
    assert main(["newboard", "--seed", "3", "-o", str(out)]) == 0
    assert main(["validate", str(out)]) == 0
    assert "tabellone valido" in capsys.readouterr().out


def test_validate_accepts_a_good_board(board_file):
    assert main(["validate", board_file]) == 0


def test_validate_lists_problems_instead_of_crashing(broken_file, capsys):
    assert main(["validate", broken_file]) == 1
    out = capsys.readouterr().out
    assert "TABELLONE NON VALIDO" in out
    assert "mancanti" in out


def test_map_prints_the_five_rows(board_file, capsys):
    assert main(["map", board_file]) == 0
    body = capsys.readouterr().out.splitlines()
    rows = [line for line in body if line.strip().startswith("h")]
    assert len(rows) == 5


def test_precompute_runs_for_three_and_four_players(board_file, capsys):
    assert main(["precompute", board_file, "--players", "4", "--position", "2"]) == 0
    assert "Pick: #2 e #7" in capsys.readouterr().out
    assert main(["precompute", board_file, "--players", "3", "--position", "3"]) == 0
    assert "Pick di attesa k = 0" in capsys.readouterr().out


def test_impossible_position_is_refused(board_file, capsys):
    assert main(["precompute", board_file, "--players", "3", "--position", "4"]) == 2
    assert "impossibile" in capsys.readouterr().err


def test_missing_file_is_reported(tmp_path, capsys):
    assert main(["validate", str(tmp_path / "nope.json")]) == 2
    assert "errore" in capsys.readouterr().err


# --- M4: the draft command --------------------------------------------------


@pytest.fixture
def midraft_file(tmp_path):
    """A board with six settlements down, so it is P2's second pick."""
    from catan_advisor.board import Placement
    from catan_advisor.scoring.draft import snake_order

    board = random_board(seed=7)
    for pick, player in enumerate(snake_order(4)[:6], start=1):
        choice = max(board.legal_vertices, key=lambda v: (board.vertex_pips(v), v))
        board = board.with_placement(Placement(player, choice, order=pick))
    board.my_position = 2
    path = tmp_path / "midraft.json"
    path.write_text(json.dumps(board_to_dict(board)), encoding="utf-8")
    return str(path)


def test_draft_advises_a_first_pick(board_file, capsys):
    assert main(["draft", board_file, "--position", "1", "--samples", "6"]) == 0
    out = capsys.readouterr().out
    assert "primo pick" in out
    assert "PRIMO PICK" in out
    assert "STRADA INIZIALE" in out
    assert "archetipo" in out


def test_draft_advises_a_second_pick(midraft_file, capsys):
    assert main(["draft", midraft_file, "--samples", "6"]) == 0
    out = capsys.readouterr().out
    assert "secondo pick" in out
    assert "SECONDO PICK" in out
    assert "AVVERSARI GIA PIAZZATI" in out


def test_draft_says_nothing_to_do_when_the_phase_is_over(tmp_path, capsys):
    from catan_advisor.board import Placement
    from catan_advisor.scoring.draft import snake_order

    board = random_board(seed=7)
    for pick, player in enumerate(snake_order(4), start=1):
        choice = max(board.legal_vertices, key=lambda v: (board.vertex_pips(v), v))
        board = board.with_placement(Placement(player, choice, order=pick))
    board.my_position = 3
    path = tmp_path / "done.json"
    path.write_text(json.dumps(board_to_dict(board)), encoding="utf-8")
    assert main(["draft", str(path)]) == 0
    assert "entrambe le colonie" in capsys.readouterr().out
