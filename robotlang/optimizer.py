"""Peephole optimizer for flat RobotLang IR."""

from __future__ import annotations

import math
from dataclasses import dataclass

from robotlang.ir import IRInstr, IROp, unroll_ir

EPS = 1e-9


@dataclass(frozen=True)
class OptimizationStats:
    before_count: int
    after_count: int
    merged_moves: int
    merged_turns: int
    removed_noops: int

    @property
    def removed_total(self) -> int:
        return self.before_count - self.after_count

    def summary(self) -> str:
        return (
            f"Optimizer: {self.before_count} -> {self.after_count} instructions "
            f"(merged_moves={self.merged_moves}, merged_turns={self.merged_turns}, "
            f"removed_noops={self.removed_noops})"
        )


def _is_noop_turn(angle: float) -> bool:
    rem = abs(angle) % 360.0
    return rem < EPS or abs(rem - 360.0) < EPS


def optimize_ir(instructions: list[IRInstr]) -> tuple[list[IRInstr], OptimizationStats]:
    """Optimize flat (or loop-containing, auto-unrolled) IR to a fixed point."""
    flat = unroll_ir(instructions)
    before_count = len(flat)
    merged_moves = 0
    merged_turns = 0
    removed_noops = 0

    current = list(flat)
    changed = True
    while changed:
        changed = False
        out: list[IRInstr] = []

        for instr in current:
            if instr.op == IROp.MOVE:
                assert instr.arg is not None
                d = float(instr.arg)
                if abs(d) < EPS:
                    removed_noops += 1
                    changed = True
                    continue
                if out and out[-1].op == IROp.MOVE:
                    prev_d = float(out[-1].arg or 0.0)
                    # Same-direction moves merge without hiding reversal excursions.
                    if (prev_d >= 0 and d >= 0) or (prev_d <= 0 and d <= 0):
                        out[-1] = IRInstr(IROp.MOVE, prev_d + d, out[-1].pos)
                        merged_moves += 1
                        changed = True
                        continue
                out.append(instr)

            elif instr.op == IROp.TURN:
                assert instr.arg is not None
                a = float(instr.arg)
                if _is_noop_turn(a):
                    removed_noops += 1
                    changed = True
                    continue
                if out and out[-1].op == IROp.TURN:
                    prev_a = float(out[-1].arg or 0.0)
                    out[-1] = IRInstr(IROp.TURN, math.fmod(prev_a + a, 360.0), out[-1].pos)
                    merged_turns += 1
                    changed = True
                    continue
                out.append(instr)

        current = out

    stats = OptimizationStats(
        before_count=before_count,
        after_count=len(current),
        merged_moves=merged_moves,
        merged_turns=merged_turns,
        removed_noops=removed_noops,
    )
    return current, stats

