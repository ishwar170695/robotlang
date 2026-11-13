"""Intermediate Representation (IR) definitions, generator, and loop expander."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from robotlang.ast_nodes import (
    BinaryOp,
    Expr,
    IfStmt,
    Move,
    NumberLit,
    ProcCall,
    ProcDef,
    Program,
    Repeat,
    SetVar,
    Stmt,
    Turn,
    UnaryOp,
    VarRef,
)
from robotlang.errors import Pos
from robotlang.semantic import SymbolTable, _eval_comparison


class IROp(str, Enum):
    MOVE = "MOVE"
    TURN = "TURN"
    LOOP_BEGIN = "LOOP_BEGIN"
    LOOP_END = "LOOP_END"


@dataclass(frozen=True)
class IRInstr:
    op: IROp
    arg: int | float | None = None
    pos: Pos | None = None

    def format_line(self) -> str:
        if self.op == IROp.LOOP_END:
            return self.op.value
        if self.op == IROp.LOOP_BEGIN:
            return f"LOOP_BEGIN {int(self.arg or 0)}"
        assert self.arg is not None
        val = int(self.arg) if isinstance(self.arg, float) and self.arg.is_integer() else self.arg
        return f"{self.op.value} {val:g}"


def _body_mutates_vars(stmts: list[Stmt]) -> bool:
    """Return True if any statement in stmts (recursively) assigns a variable or calls a proc."""
    for s in stmts:
        if isinstance(s, (SetVar, ProcCall)):
            return True
        if isinstance(s, Repeat) and _body_mutates_vars(s.body):
            return True
        if isinstance(s, IfStmt):
            if _body_mutates_vars(s.then_body):
                return True
            if s.else_body and _body_mutates_vars(s.else_body):
                return True
    return False


class IRGenerator:
    """Lowers a semantically valid AST into linear IR (with optional loop preservation)."""

    def __init__(self, unroll_loops: bool = False) -> None:
        self.unroll_loops = unroll_loops
        self.symbols = SymbolTable()
        self.procedures: dict[str, ProcDef] = {}
        self.instructions: list[IRInstr] = []

    def generate(self, program: Program) -> list[IRInstr]:
        self.instructions = []
        for stmt in program.statements:
            self._emit_stmt(stmt)
        return self.instructions

    def _eval(self, expr: Expr) -> float:
        if isinstance(expr, NumberLit):
            return float(expr.value)
        if isinstance(expr, VarRef):
            found, val = self.symbols.lookup(expr.name)
            if not found or val is None:
                raise ValueError(f"Unresolved variable '{expr.name}' during IR generation")
            return float(val)
        if isinstance(expr, UnaryOp):
            v = self._eval(expr.operand)
            return -v if expr.op == "-" else v
        if isinstance(expr, BinaryOp):
            left = self._eval(expr.left)
            right = self._eval(expr.right)
            if expr.op == "+":
                return left + right
            if expr.op == "-":
                return left - right
            if expr.op == "*":
                return left * right
            if expr.op == "/":
                return left / right
        raise ValueError(f"Unsupported expression node: {expr!r}")

    def _emit_stmt(self, stmt: Stmt) -> None:
        if isinstance(stmt, Move):
            dist = self._eval(stmt.amount)
            signed = dist if stmt.direction == "FORWARD" else -dist
            self.instructions.append(IRInstr(IROp.MOVE, signed, stmt.pos))
            return

        if isinstance(stmt, Turn):
            angle = self._eval(stmt.angle)
            signed = angle if stmt.direction == "RIGHT" else -angle
            self.instructions.append(IRInstr(IROp.TURN, signed, stmt.pos))
            return

        if isinstance(stmt, SetVar):
            val = self._eval(stmt.value)
            self.symbols.assign(stmt.name, val)
            return

        if isinstance(stmt, ProcDef):
            self.procedures[stmt.name] = stmt
            return

        if isinstance(stmt, ProcCall):
            proc = self.procedures[stmt.name]
            arg_vals: list[int | float | None] = [self._eval(a) for a in stmt.args]
            self.symbols.push_scope(dict(zip(proc.params, arg_vals)))
            try:
                for child in proc.body:
                    self._emit_stmt(child)
            finally:
                self.symbols.pop_scope()
            return

        if isinstance(stmt, IfStmt):
            cond = _eval_comparison(stmt.op, self._eval(stmt.left), self._eval(stmt.right))
            branch = stmt.then_body if cond else (stmt.else_body or [])
            for child in branch:
                self._emit_stmt(child)
            return

        if isinstance(stmt, Repeat):
            count = int(self._eval(stmt.count))
            # If loops are kept structured AND body doesn't mutate state across iterations,
            # emit LOOP_BEGIN / LOOP_END; otherwise expand iterations with live variable state.
            if not self.unroll_loops and not _body_mutates_vars(stmt.body):
                self.instructions.append(IRInstr(IROp.LOOP_BEGIN, count, stmt.pos))
                for child in stmt.body:
                    self._emit_stmt(child)
                self.instructions.append(IRInstr(IROp.LOOP_END, None, stmt.pos))
            else:
                for _ in range(count):
                    for child in stmt.body:
                        self._emit_stmt(child)


def generate_ir(program: Program, unroll: bool = False) -> list[IRInstr]:
    """Generate IR from a Program AST."""
    return IRGenerator(unroll_loops=unroll).generate(program)


def unroll_ir(instructions: list[IRInstr]) -> list[IRInstr]:
    """Expand LOOP_BEGIN / LOOP_END blocks into a completely flat instruction list."""
    stack: list[tuple[int, list[IRInstr]]] = []
    flat: list[IRInstr] = []

    for instr in instructions:
        if instr.op == IROp.LOOP_BEGIN:
            count = int(instr.arg or 0)
            stack.append((count, []))
        elif instr.op == IROp.LOOP_END:
            count, body = stack.pop()
            expanded = body * count
            if stack:
                stack[-1][1].extend(expanded)
            else:
                flat.extend(expanded)
        else:
            if stack:
                stack[-1][1].append(instr)
            else:
                flat.append(instr)
    return flat


def format_ir(instructions: list[IRInstr]) -> str:
    """Format an IR instruction list with indentation for LOOP_BEGIN/LOOP_END."""
    lines: list[str] = []
    depth = 0
    for instr in instructions:
        if instr.op == IROp.LOOP_END:
            depth = max(0, depth - 1)
        lines.append(f"{'  ' * depth}{instr.format_line()}")
        if instr.op == IROp.LOOP_BEGIN:
            depth += 1
    return "\n".join(lines)

