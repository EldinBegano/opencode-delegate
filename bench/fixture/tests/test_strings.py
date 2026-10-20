import pytest

from textkit.strings import count_words, normalize_whitespace, slugify, title_case, truncate


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Hello World", "hello-world"),
        ("  Crème brûlée!  ", "creme-brulee"),
        ("a--b", "a-b"),
    ],
)
def test_slugify(text, expected):
    assert slugify(text) == expected


def test_slugify_custom_separator():
    assert slugify("Hello World", sep="_") == "hello_world"


@pytest.mark.parametrize(
    ("text", "width", "expected"),
    [
        ("short", 10, "short"),
        ("hello world", 8, "hello..."),
        ("hello", 2, ".."),
    ],
)
def test_truncate(text, width, expected):
    assert truncate(text, width) == expected


def test_title_case_keeps_minor_words_lower():
    assert title_case("the lord OF the rings") == "The Lord of the Rings"


def test_count_words():
    assert count_words("one, two  three") == 3


def test_normalize_whitespace():
    assert normalize_whitespace(" a \t b\n c ") == "a b c"
