"""Target code generator: lowers flat IR into low-level robot command text."""

from __future__ import annotations

from robotlang.ir import IRInstr, IROp, unroll_ir


def _fmt_move(val: float) -> str:
    rounded = round(val, 6)
    if rounded == 0:
        rounded = 0.0
    if float(rounded).is_integer():
        return f"{rounded:.1f}"
    return f"{rounded:g}"


def _fmt_angle(val: float) -> str:
    rounded = round(val, 6)
    if rounded == 0:
        rounded = 0.0
    if float(rounded).is_integer():
        return str(int(rounded))
    return f"{rounded:g}"


def generate_commands(instructions: list[IRInstr]) -> list[str]:
    """Convert IR (unrolling any remaining loops) into low-level robot command strings."""
    flat = unroll_ir(instructions)
    commands: list[str] = []
    for instr in flat:
        if instr.op == IROp.MOVE:
            assert instr.arg is not None
            commands.append(f"MOVE {_fmt_move(float(instr.arg))}")
        elif instr.op == IROp.TURN:
            assert instr.arg is not None
            commands.append(f"ROTATE {_fmt_angle(float(instr.arg))}")
    return commands


def generate_code(instructions: list[IRInstr], separator: str = "\n") -> str:
    """Return generated robot commands joined by separator (default newline)."""
    return separator.join(generate_commands(instructions))

