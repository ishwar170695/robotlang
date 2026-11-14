"""Command-line interface for the RobotLang compiler and simulator."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from robotlang.ast_nodes import format_ast
from robotlang.compiler import compile_source
from robotlang.errors import Diagnostic
from robotlang.ir import format_ir
from robotlang.lexer import lex
from robotlang.parser import parse
from robotlang.semantic import ArenaConfig
from robotlang.simulator import render_matplotlib, simulate_commands


def _read_source(file_path: str) -> tuple[Path, str]:
    path = Path(file_path)
    if not path.is_file():
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(2)
    return path, path.read_text(encoding="utf-8")


def _print_diagnostics(diagnostics: list[Diagnostic], source: str) -> None:
    lines = source.splitlines()
    for diag in diagnostics:
        print(diag.format(lines), file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="robotlang",
        description="Robot Movement Language Compiler, Optimizer, and Simulator",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # Common arguments helper
    def add_file_arg(p: argparse.ArgumentParser) -> None:
        p.add_argument("file", help="Path to .rbt RobotLang source file")

    p_tokens = sub.add_parser("tokens", help="Print lexer tokens")
    add_file_arg(p_tokens)

    p_ast = sub.add_parser("ast", help="Print parsed AST")
    add_file_arg(p_ast)

    p_check = sub.add_parser("check", help="Lex, parse, and semantically validate")
    add_file_arg(p_check)
    p_check.add_argument("--arena", type=float, default=100.0, help="Square arena size (default: 100)")

    p_ir = sub.add_parser("ir", help="Print IR (structured, unrolled, and optimized)")
    add_file_arg(p_ir)
    p_ir.add_argument("--unrolled", action="store_true", help="Show unrolled flat IR only")
    p_ir.add_argument("--no-opt", action="store_true", help="Disable optimization")
    p_ir.add_argument("--arena", type=float, default=100.0, help="Square arena size (default: 100)")

    p_asm = sub.add_parser("asm", help="Print generated PIC16F877A assembly")
    add_file_arg(p_asm)
    p_asm.add_argument("--no-opt", action="store_true", help="Disable optimization")
    p_asm.add_argument("--arena", type=float, default=100.0, help="Square arena size (default: 100)")

    p_run = sub.add_parser("run", help="Compile and run in the virtual robot simulator")
    add_file_arg(p_run)
    p_run.add_argument("--no-opt", action="store_true", help="Disable optimization")
    p_run.add_argument("--no-trace", action="store_true", help="Hide execution trace table")
    p_run.add_argument("--show", action="store_true", help="Display matplotlib plot interactively")
    p_run.add_argument("--save", type=str, default=None, help="Save trajectory image (PNG/SVG)")
    p_run.add_argument("--arena", type=float, default=100.0, help="Square arena size (default: 100)")

    p_play = sub.add_parser("play", help="Launch interactive GUI playground & live robot arena")
    p_play.add_argument("file", nargs="?", default=None, help="Optional .rbt file to preload")
    p_play.add_argument("--arena", type=float, default=100.0, help="Square arena size (default: 100)")

    args = parser.parse_args(argv)

    if args.command == "play":
        if args.file is not None:
            _read_source(args.file)
        from robotlang.playground import launch_playground

        return launch_playground(initial_file=args.file, arena=ArenaConfig.from_size(args.arena))

    path, source = _read_source(args.file)

    if args.command == "tokens":
        tokens, lex_diags = lex(source)
        for tok in tokens:
            print(tok)
        if lex_diags:
            _print_diagnostics(lex_diags, source)
            return 1
        return 0

    if args.command == "ast":
        tokens, lex_diags = lex(source)
        ast, parse_diags = parse(tokens)
        diags = lex_diags + parse_diags
        print(format_ast(ast))
        if diags:
            _print_diagnostics(diags, source)
            return 1
        return 0

    arena = ArenaConfig.from_size(args.arena)
    optimize = not getattr(args, "no_opt", False) and not (
        args.command == "ir" and args.unrolled
    )
    result = compile_source(source, optimize=optimize, arena=arena)

    if result.diagnostics:
        _print_diagnostics(result.diagnostics, source)

    if not result.success:
        return 1

    if args.command == "check":
        assert result.semantic is not None
        print(
            f"OK: 0 errors, {len(result.warnings)} warning(s). "
            f"Expanded steps: {result.semantic.expanded_steps}, "
            f"Final pose: ({result.semantic.final_x:.2f}, {result.semantic.final_y:.2f}) "
            f"heading {result.semantic.final_heading:.1f}°"
        )
        return 0

    if args.command == "ir":
        if args.unrolled:
            print(format_ir(result.unrolled_ir) or "(empty)")
        else:
            print("=== Structured IR ===")
            print(format_ir(result.structured_ir) or "(empty)")
            print("\n=== Unrolled Flat IR ===")
            print(format_ir(result.unrolled_ir) or "(empty)")
            if optimize and result.opt_stats is not None:
                print(f"\n=== Optimized IR ({result.opt_stats.before_count} -> {result.opt_stats.after_count}) ===")
                print(format_ir(result.optimized_ir) or "(empty)")
        return 0

    if args.command == "asm":
        if result.opt_stats is not None:
            print(f"; {result.opt_stats.summary()}")
        print("\n".join(result.commands))
        return 0

    if args.command == "run":
        if result.opt_stats is not None:
            print(result.opt_stats.summary())
        print("\n--- Generated PIC16F877A Assembly ---")
        print("\n".join(result.commands) if result.commands else "(no commands)")

        sim = simulate_commands(result.commands)
        if not args.no_trace:
            print("\n--- Execution Trace ---")
            print(sim.format_trace() if sim.trace else "(empty program)")

        st = sim.final_state
        fx = 0.0 if abs(st.x) < 1e-9 else st.x
        fy = 0.0 if abs(st.y) < 1e-9 else st.y
        fh = 0.0 if abs(st.heading) < 1e-9 else st.heading
        print(
            f"\nFinal state: x={fx:.2f}, y={fy:.2f}, heading={fh:.1f}°"
        )

        if args.save or args.show:
            saved = render_matplotlib(
                sim,
                arena=arena,
                output_path=args.save,
                show=args.show,
                title=f"RobotLang: {path.name}",
            )
            if saved is not None:
                print(f"Saved trajectory plot to {saved}")

        return 0

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
