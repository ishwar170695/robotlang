"""Unit tests for the RobotLang semantic analyzer, symbol table, and arena checks."""

from robotlang.errors import Severity
from robotlang.lexer import lex
from robotlang.parser import parse
from robotlang.semantic import ArenaConfig, analyze


def _analyze_src(src: str, arena_size: float = 100.0, max_steps: int = 10_000):
    tokens, lex_diags = lex(src)
    assert lex_diags == []
    ast, parse_diags = parse(tokens)
    assert parse_diags == []
    return analyze(ast, arena=ArenaConfig.from_size(arena_size), max_steps=max_steps)


def test_semantic_negative_distance_and_bad_angle():
    res = _analyze_src("FORWARD -5; RIGHT 400;")
    errors = [d for d in res.diagnostics if d.severity == Severity.ERROR]
    assert len(errors) == 2
    assert ">= 0" in errors[0].message
    assert "between 0 and 360" in errors[1].message


def test_semantic_repeat_validation_and_step_cap():
    res_zero = _analyze_src("REPEAT 0 { FORWARD 1; }")
    assert res_zero.has_errors
    assert "positive integer" in res_zero.diagnostics[0].message

    res_float = _analyze_src("REPEAT 2.5 { FORWARD 1; }")
    assert res_float.has_errors
    assert "positive integer" in res_float.diagnostics[0].message

    res_huge = _analyze_src("REPEAT 99999999 { FORWARD 1; }")
    assert res_huge.has_errors
    assert "maximum step limit" in res_huge.diagnostics[0].message


def test_semantic_arena_boundary_violation():
    res = _analyze_src("FORWARD 30; FORWARD 30;", arena_size=100.0)
    assert res.has_errors
    assert any("leaves arena" in d.message for d in res.diagnostics)


def test_semantic_variables_and_procedure_scopes():
    res_undef = _analyze_src("FORWARD unknown;")
    assert res_undef.has_errors
    assert "Undefined variable 'unknown'" in res_undef.diagnostics[0].message

    res_proc = _analyze_src(
        "DEF sq(s) { REPEAT 4 { FORWARD s; RIGHT 90; } } CALL sq(10); FORWARD s;"
    )
    # Parameter 's' must not leak outside procedure scope
    assert res_proc.has_errors
    assert any("Undefined variable 's'" in d.message for d in res_proc.diagnostics)


def test_semantic_warnings_empty_blocks():
    res = _analyze_src("REPEAT 3 {} IF 1 > 0 {} ELSE {}")
    assert not res.has_errors
    warnings = [d for d in res.diagnostics if d.severity == Severity.WARNING]
    assert len(warnings) == 3
    assert any("Empty REPEAT" in w.message for w in warnings)
    assert any("Empty IF" in w.message for w in warnings)
    assert any("Empty ELSE" in w.message for w in warnings)


def test_semantic_fractional_move_and_turn_warn():
    res = _analyze_src("FORWARD 2.5; RIGHT 45.5;")
    assert not res.has_errors
    warnings = [d for d in res.diagnostics if d.severity == Severity.WARNING]
    assert len(warnings) == 2
    assert any("Fractional move distance" in w.message for w in warnings)
    assert any("Fractional turn angle" in w.message for w in warnings)


def test_semantic_loop_arena_violation_deduplicated():
    res = _analyze_src("REPEAT 4 { FORWARD 30; }", arena_size=100.0)
    errors = [d for d in res.diagnostics if d.severity == Severity.ERROR]
    assert len(errors) == 1
    assert "leaves arena" in errors[0].message
    assert "(0.00, 60.00)" in errors[0].message


def test_semantic_uncalled_proc_does_not_mutate_globals():
    res = _analyze_src(
        "SET x = 10;\n"
        "DEF helper() { FORWARD 5; }\n"
        "DEF unused() { SET x = 999; CALL helper(); }\n"
    )
    assert not res.has_errors
    assert res.variables["x"] == 10

