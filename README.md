# RobotLang Compiler & Simulator

A complete compiler, peephole optimizer, target code generator, and 2D simulator for the **RobotLang** movement language.

## Pipeline

```
Source (.rbt) -> Lexer -> Parser -> Semantic Analyzer -> IR Generator -> Optimizer -> Codegen -> Simulator
```

## Setup

Requires Python 3.10+. Install dependencies (or editable package):

```bash
pip install -e ".[dev]"
```

Run the test suite:

```bash
python -m pytest -v
```

## CLI Commands & Flags

You can run via `python -m robotlang <command> ...` (or `robotlang <command> ...` after `pip install -e .`).

| Command | Purpose | Options |
|---|---|---|
| `tokens <file>` | Print lexer tokens with line/col | — |
| `ast <file>` | Print the parsed AST | — |
| `check <file>` | Lex, parse, and run semantic/arena checks | `--arena SIZE` |
| `ir <file>` | Print structured, unrolled, and optimized IR | `--unrolled`, `--no-opt`, `--arena SIZE` |
| `asm <file>` | Print generated PIC16F877A assembly (`pic-as`) | `--no-opt`, `--arena SIZE` |
| `run <file>` | Compile, execute in simulator, and print trace | `--no-opt`, `--no-trace`, `--show`, `--save PATH`, `--arena SIZE` |
| `play [file]` | Launch interactive Tkinter playground GUI | `--arena SIZE` |

**Flag details:**
- `--unrolled`: print only the pre-optimization unrolled flat IR (`ir` subcommand).
- `--no-opt`: disable the peephole optimizer.
- `--no-trace`: hide the step-by-step execution trace table (`run`).
- `--show` / `--save PATH`: open an interactive `matplotlib` plot or export PNG/SVG (`run`).
- `--arena SIZE`: set the square arena width/height (default `100`, i.e. `[-50, 50] x [-50, 50]`).

```bash
# Inspect tokens, AST, IR, loop expansion, and generated PIC16F877A assembly
python -m robotlang tokens examples/valid/square.rbt
python -m robotlang ast examples/valid/square.rbt
python -m robotlang ir examples/valid/square.rbt
python -m robotlang ir examples/valid/optimizer_case.rbt --unrolled
python -m robotlang asm examples/valid/optimizer_case.rbt

# Compile and run in the simulator (prints trace table + final pose)
python -m robotlang run examples/valid/square.rbt

# Export trajectory plot as PNG/SVG or open an interactive matplotlib window
python -m robotlang run examples/valid/spiral.rbt --save spiral.png
python -m robotlang run examples/valid/square.rbt --show

# Launch the interactive GUI playground (editor + Drive Pad + stage inspector)
python -m robotlang play
python -m robotlang play examples/valid/spiral.rbt

# Validate an invalid script to see line/col diagnostics
python -m robotlang check examples/invalid/missing_semi.rbt
```

## Language Reference

| Construct | Syntax | Meaning |
|---|---|---|
| Movement | `FORWARD expr;` / `BACKWARD expr;` | Move forward/backward by `expr` units (`>= 0`) |
| Rotation | `LEFT expr;` / `RIGHT expr;` | Turn counter-clockwise/clockwise by `expr` degrees (`0–360`) |
| Loop | `REPEAT expr { ... }` | Repeat block `expr` times (`> 0` integer; nestable, capped at 10,000 steps) |
| Variables | `SET name = expr;` | Bind/update variable with arithmetic `+`, `-`, `*`, `/`, unary `+/-`, `(...)` |
| Procedures | `DEF f(a, b) { ... }` / `CALL f(1, 2);` | Define and call reusable parameterized motion routines |
| Conditionals | `IF expr op expr { ... } [ELSE { ... }]` | Branch using `==`, `!=`, `<`, `<=`, `>`, `>=` |
| Comments | `# ...` | Single-line comment |

Generated target output emitted by the backend (`asm` / `run`): Microchip **PIC16F877A** assembly (`pic-as` syntax for MPLAB X Simulator), loading 8-bit integer chunks (`0–255`) into `W` via `MOVLW` and invoking `CALL MOVE_FWD`, `CALL MOVE_BWD`, `CALL TURN_RIGHT`, or `CALL TURN_LEFT` with `PORTB` motor-control subroutines.

See [docs/grammar.md](docs/grammar.md) and [docs/architecture.md](docs/architecture.md) for full specifications.

## Project Layout

```
robotlang/
├── robotlang/
│   ├── __main__.py
│   ├── ast_nodes.py    # AST dataclasses & tree printer
│   ├── cli.py          # CLI entrypoints (run, play, tokens, ast, ir, asm, check)
│   ├── codegen.py      # Flat IR -> PIC16F877A assembly (pic-as)
│   ├── compiler.py     # End-to-end compilation pipeline
│   ├── errors.py       # Pos, Severity, Diagnostic formatting
│   ├── ir.py           # Structured IR, loop unroller, formatter
│   ├── lexer.py        # Hand-written cursor lexer
│   ├── optimizer.py    # Fixed-point peephole optimizer
│   ├── parser.py       # Recursive-descent parser + panic-mode recovery
│   ├── playground.py   # Interactive Tkinter GUI + live Drive Pad
│   ├── semantic.py     # Symbol table, domain rules, arena bounds
│   └── simulator.py    # PIC16 assembly simulator, trace table, matplotlib plotter
├── examples/
│   ├── valid/          # 11 valid .rbt programs
│   └── invalid/        # 7 invalid .rbt programs (syntax & semantic errors)
├── tests/              # 46 pytest unit & end-to-end tests
└── docs/               # Grammar spec & architecture diagram
```

## Known Limitations & Future Work

- **Domain & language model**: 2D planar motion only; static expressions/variables resolved at compile time (no runtime sensor input); fixed rectangular arena without internal obstacles.
- **Static `IF`/`ELSE` branch checking**: Conditions are evaluated statically, so untaken dead branches are not analyzed (which also avoids false positives on guarded checks such as `IF size > 0 { FORWARD size; }`).
- **Formatting & 8-bit codegen precision**: IR formats floats with 6 significant digits (`:g`), while PIC16F877A code generation rounds fractional move/turn values to integers (emitting a compiler warning) and splits magnitudes greater than 255 into 8-bit `MOVLW` chunks.
- **Future work**: Obstacle collision polygons, runtime sensor conditionals, ROS / G-code backend targets.

