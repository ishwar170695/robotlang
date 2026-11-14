"""Unit tests for the RobotLang recursive-descent parser and panic-mode recovery."""

from robotlang.ast_nodes import BinaryOp, Move, NumberLit, Repeat, Turn
from robotlang.lexer import lex
from robotlang.parser import parse


def test_parse_ast_shape_and_precedence():
    src = "FORWARD 2 + 3 * 4; REPEAT 4 { RIGHT 90; }"
    tokens, lex_diags = lex(src)
    assert lex_diags == []
    ast, parse_diags = parse(tokens)
    assert parse_diags == []
    assert len(ast.statements) == 2

    move = ast.statements[0]
    assert isinstance(move, Move)
    assert move.direction == "FORWARD"
    # 2 + (3 * 4)
    assert isinstance(move.amount, BinaryOp) and move.amount.op == "+"
    assert isinstance(move.amount.left, NumberLit) and move.amount.left.value == 2
    assert isinstance(move.amount.right, BinaryOp) and move.amount.right.op == "*"

    rep = ast.statements[1]
    assert isinstance(rep, Repeat)
    assert len(rep.body) == 1
    assert isinstance(rep.body[0], Turn)


def test_parse_panic_mode_reports_multiple_errors():
    src = (
        "FORWARD 5\n"
        "FORWRD 10;\n"
        "RIGHT 90;\n"
        "}\n"
        "FORWARD 3\n"
    )
    tokens, _ = lex(src)
    ast, diags = parse(tokens)
    # Expect: missing ';' on line 1, unknown command on line 2, unmatched '}' on line 4, missing ';' on line 5
    assert len(diags) == 4
    assert "Expected ';'" in diags[0].message and diags[0].pos.line == 1
    assert "FORWRD" in diags[1].message and "FORWARD" in diags[1].message
    assert "Unmatched '}'" in diags[2].message and diags[2].pos.line == 4
    assert "Expected ';'" in diags[3].message and diags[3].pos.line == 5
    # Valid RIGHT 90; was still recovered into AST
    assert any(isinstance(s, Turn) and s.direction == "RIGHT" for s in ast.statements)


def test_parse_unclosed_brace():
    src = "REPEAT 3 {\n  FORWARD 5;\n"
    tokens, _ = lex(src)
    _, diags = parse(tokens)
    assert len(diags) == 1
    assert "Expected '}'" in diags[0].message


def test_parse_def_trailing_comma_recovers_cleanly():
    src = "DEF f(a, ) { FORWARD a; }\nFORWARD 2;"
    tokens, _ = lex(src)
    ast, diags = parse(tokens)
    assert len(diags) == 1
    assert "Expected parameter name after ','" in diags[0].message
    assert len(ast.statements) == 2


