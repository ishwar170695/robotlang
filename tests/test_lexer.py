"""Unit tests for the RobotLang hand-written lexer."""

from robotlang.errors import Severity
from robotlang.lexer import TokenType, lex


def test_lex_basic_tokens_and_positions():
    src = "FORWARD 5; # comment\nRIGHT 90;"
    tokens, diags = lex(src)
    assert diags == []
    types = [t.type for t in tokens]
    assert types == [
        TokenType.FORWARD,
        TokenType.NUMBER,
        TokenType.SEMI,
        TokenType.RIGHT,
        TokenType.NUMBER,
        TokenType.SEMI,
        TokenType.EOF,
    ]
    assert tokens[0].pos.line == 1 and tokens[0].pos.col == 1
    assert tokens[1].value == 5 and tokens[1].pos.col == 9
    assert tokens[3].pos.line == 2 and tokens[3].pos.col == 1


def test_lex_floats_operators_and_comparisons():
    src = "SET x = 2.5 * (1 + 3); IF x >= 10 { FORWARD 5; }"
    tokens, diags = lex(src)
    assert diags == []
    assert [t.type for t in tokens[:-1]] == [
        TokenType.SET,
        TokenType.IDENT,
        TokenType.ASSIGN,
        TokenType.NUMBER,
        TokenType.STAR,
        TokenType.LPAREN,
        TokenType.NUMBER,
        TokenType.PLUS,
        TokenType.NUMBER,
        TokenType.RPAREN,
        TokenType.SEMI,
        TokenType.IF,
        TokenType.IDENT,
        TokenType.GE,
        TokenType.NUMBER,
        TokenType.LBRACE,
        TokenType.FORWARD,
        TokenType.NUMBER,
        TokenType.SEMI,
        TokenType.RBRACE,
    ]
    assert tokens[3].value == 2.5


def test_lex_invalid_characters_recover():
    src = "FORWARD @ 5;\n$RIGHT 90;"
    tokens, diags = lex(src)
    assert len(diags) == 2
    assert all(d.severity == Severity.ERROR and d.phase == "lexer" for d in diags)
    assert diags[0].pos.line == 1 and diags[0].pos.col == 9
    assert diags[1].pos.line == 2 and diags[1].pos.col == 1
    # Valid tokens around invalid characters are still produced
    assert any(t.type == TokenType.RIGHT for t in tokens)

