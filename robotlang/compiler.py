"""End-to-end compilation pipeline orchestrating lex -> parse -> semantic -> IR -> opt -> codegen."""

from __future__ import annotations

from dataclasses import dataclass

from robotlang.ast_nodes import Program
from robotlang.codegen import generate_commands
from robotlang.errors import Diagnostic, Severity
from robotlang.ir import IRInstr, generate_ir, unroll_ir
from robotlang.lexer import Token, lex
from robotlang.optimizer import OptimizationStats, optimize_ir
from robotlang.parser import parse
from robotlang.semantic import ArenaConfig, SemanticResult, analyze


@dataclass
class CompileResult:
    source: str
    tokens: list[Token]
    ast: Program | None
    diagnostics: list[Diagnostic]
    semantic: SemanticResult | None
    structured_ir: list[IRInstr]
    unrolled_ir: list[IRInstr]
    optimized_ir: list[IRInstr]
    opt_stats: OptimizationStats | None
    commands: list[str]

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == Severity.WARNING]

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


def compile_source(
    source: str,
    optimize: bool = True,
    arena: ArenaConfig | None = None,
    max_steps: int = 10_000,
) -> CompileResult:
    """Run all compiler stages on RobotLang source text."""
    diagnostics: list[Diagnostic] = []

    tokens, lex_diags = lex(source)
    diagnostics.extend(lex_diags)

    ast, parse_diags = parse(tokens)
    diagnostics.extend(parse_diags)

    if any(d.severity == Severity.ERROR for d in diagnostics):
        return CompileResult(
            source=source,
            tokens=tokens,
            ast=ast,
            diagnostics=diagnostics,
            semantic=None,
            structured_ir=[],
            unrolled_ir=[],
            optimized_ir=[],
            opt_stats=None,
            commands=[],
        )

    sem_result = analyze(ast, arena=arena, max_steps=max_steps)
    diagnostics.extend(sem_result.diagnostics)

    if sem_result.has_errors:
        return CompileResult(
            source=source,
            tokens=tokens,
            ast=ast,
            diagnostics=diagnostics,
            semantic=sem_result,
            structured_ir=[],
            unrolled_ir=[],
            optimized_ir=[],
            opt_stats=None,
            commands=[],
        )

    structured_ir = generate_ir(ast, unroll=False)
    flat_ir = unroll_ir(structured_ir)
    if optimize:
        final_ir, opt_stats = optimize_ir(flat_ir)
    else:
        final_ir = flat_ir
        opt_stats = OptimizationStats(
            before_count=len(flat_ir),
            after_count=len(flat_ir),
            merged_moves=0,
            merged_turns=0,
            removed_noops=0,
        )

    commands = generate_commands(final_ir)

    return CompileResult(
        source=source,
        tokens=tokens,
        ast=ast,
        diagnostics=diagnostics,
        semantic=sem_result,
        structured_ir=structured_ir,
        unrolled_ir=flat_ir,
        optimized_ir=final_ir,
        opt_stats=opt_stats,
        commands=commands,
    )

