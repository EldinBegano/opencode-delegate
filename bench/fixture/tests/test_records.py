import pytest

from textkit import cli
from textkit.records import format_row, parse_row, parse_rows_header
from textkit.report import load, oldest


def test_parse_row():
    assert parse_row("ada; 36 ;london") == {"name": "ada", "age": 36, "city": "london"}


def test_parse_row_wrong_field_count():
    with pytest.raises(ValueError):
        parse_row("ada;36")


def test_parse_rows_header():
    assert parse_rows_header("Name;AGE; City") == ["name", "age", "city"]


def test_round_trip():
    assert format_row(parse_row("bob;41;paris")) == "bob;41;paris"


def test_report():
    lines = ["name;age;city", "ada;36;london", "bob;41;paris", ""]
    assert len(load(lines)) == 2
    assert oldest(lines) == "bob"


def test_cli(capsys):
    assert cli.main(["ada;36;london"]) == 0
    assert "ada" in capsys.readouterr().out
