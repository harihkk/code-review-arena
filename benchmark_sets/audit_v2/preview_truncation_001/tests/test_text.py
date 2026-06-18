from app.text import preview


def test_short_text_is_unchanged():
    assert preview("hello", 10) == "hello"


def test_long_text_keeps_limit_characters():
    assert preview("hello world", 5) == "hello..."


def test_text_at_limit_is_unchanged():
    assert preview("hello", 5) == "hello"
