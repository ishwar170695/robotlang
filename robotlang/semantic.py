"""Semantic analyzer, symbol table, and arena boundary validator for RobotLang."""

from __future__ import annotations

import math
from dataclasses import dataclass

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
from robotlang.errors import Diagnostic, Pos, Severity


@dataclass(frozen=True)
class ArenaConfig:
    """2D rectangular arena bounds."""

    min_x: float = -50.0
    max_x: float = 50.0
    min_y: float = -50.0
    max_y: float = 50.0

    @classmethod
    def from_size(cls, size: float = 100.0) -> ArenaConfig:
        half = size / 2.0
        return cls(min_x=-half, max_x=half, min_y=-half, max_y=half)

    def contains(self, x: float, y: float, eps: float = 1e-9) -> bool:
        return (
            self.min_x - eps <= x <= self.max_x + eps
            and self.min_y - eps <= y <= self.max_y + eps
        )

    def describe(self) -> str:
        return f"[{self.min_x:g}, {self.max_x:g}] x [{self.min_y:g}, {self.max_y:g}]"


class SymbolTable:
    """Scoped symbol table mapping variable names to numeric values (or None if symbolic)."""

    def __init__(self) -> None:
        self._scopes: list[dict[str, int | float | None]] = [{}]

    def push_scope(self, initial: dict[str, int | float | None] | None = None) -> None:
        self._scopes.append(dict(initial) if initial else {})

    def pop_scope(self) -> None:
        if len(self._scopes) > 1:
            self._scopes.pop()

    def lookup(self, name: str) -> tuple[bool, int | float | None]:
        for scope in reversed(self._scopes):
            if name in scope:
                return True, scope[name]
        return False, None

    def assign(self, name: str, value: int | float | None) -> None:
        # Update existing binding in enclosing scope if present (allows loop mutations),
        # otherwise declare in the current innermost scope.
        for scope in reversed(self._scopes):
            if name in scope:
                scope[name] = value
                return
        self._scopes[-1][name] = value

    def all_globals(self) -> dict[str, int | float | None]:
        return dict(self._scopes[0])


@dataclass
class SemanticResult:
    diagnostics: list[Diagnostic]
    expanded_steps: int
    final_x: float
    final_y: float
    final_heading: float
    variables: dict[str, int | float | None]
    procedures: list[str]

    @property
    def has_errors(self) -> bool:
        return any(d.severity == Severity.ERROR for d in self.diagnostics)


class _StepLimitExceeded(Exception):
    """Raised internally when loop/recursion expansion hits the safety cap."""


class SemanticAnalyzer:
    """Walks the AST to enforce domain rules, scopes, loop bounds, and arena boundaries."""

    def __init__(
        self,
        arena: ArenaConfig | None = None,
        max_steps: int = 10_000,
        max_call_depth: int = 64,
    ) -> None:
        self.arena = arena or ArenaConfig()
        self.max_steps = max_steps
        self.max_call_depth = max_call_depth
        self.symbols = SymbolTable()
        self.procedures: dict[str, ProcDef] = {}
        self.called_procs: set[str] = set()
        self.diagnostics: list[Diagnostic] = []
        self._seen_diags: set[tuple[int, str, str]] = set()

        # Simulated robot state for static boundary validation
        self.x = 0.0
        self.y = 0.0
        self.heading = 0.0
        self.expanded_steps = 0
        self.call_depth = 0

    def _emit(
        self,
        severity: Severity,
        message: str,
        pos: Pos,
        node: object | None = None,
        dedupe_key: str | None = None,
    ) -> None:
        key = (id(node) if node is not None else 0, severity.value, dedupe_key or message)
        if node is not None and key in self._seen_diags:
            return
        if node is not None:
            self._seen_diags.add(key)
        self.diagnostics.append(Diagnostic(severity, "semantic", message, pos))

    def _count_step(self, pos: Pos) -> None:
        self.expanded_steps += 1
        if self.expanded_steps > self.max_steps:
            self._emit(
                Severity.ERROR,
                f"Expanded program exceeds maximum step limit ({self.max_steps}); possible infinite or oversized loop",
                pos,
            )
            raise _StepLimitExceeded()

    def analyze(self, program: Program) -> SemanticResult:
        try:
            for stmt in program.statements:
                self._visit_stmt(stmt)
        except _StepLimitExceeded:
            pass

        # Statically check any procedures that were defined but never called.
        for name, proc in self.procedures.items():
            if name not in self.called_procs:
                self._check_uncalled_proc(proc)

        return SemanticResult(
            diagnostics=self.diagnostics,
            expanded_steps=self.expanded_steps,
            final_x=self.x,
            final_y=self.y,
            final_heading=self.heading,
            variables=self.symbols.all_globals(),
            procedures=sorted(self.procedures.keys()),
        )

    def _check_uncalled_proc(self, proc: ProcDef) -> None:
        saved_scopes = [dict(scope) for scope in self.symbols._scopes]
        saved_called = set(self.called_procs)
        saved_state = (self.x, self.y, self.heading)
        self.symbols.push_scope({p: None for p in proc.params})
        try:
            for stmt in proc.body:
                self._visit_stmt(stmt, symbolic_mode=True)
        except _StepLimitExceeded:
            pass
        finally:
            self.x, self.y, self.heading = saved_state
            self.symbols._scopes = saved_scopes
            self.called_procs = saved_called

    def _eval_expr(self, expr: Expr) -> int | float | None:
        if isinstance(expr, NumberLit):
            return expr.value

        if isinstance(expr, VarRef):
            found, val = self.symbols.lookup(expr.name)
            if not found:
                self._emit(
                    Severity.ERROR,
                    f"Undefined variable '{expr.name}'",
                    expr.pos,
                    expr,
                )
                return None
            return val

        if isinstance(expr, UnaryOp):
            operand = self._eval_expr(expr.operand)
            if operand is None:
                return None
            return -operand if expr.op == "-" else +operand

        if isinstance(expr, BinaryOp):
            left = self._eval_expr(expr.left)
            right = self._eval_expr(expr.right)
            if left is None or right is None:
                return None
            if expr.op == "+":
                return left + right
            if expr.op == "-":
                return left - right
            if expr.op == "*":
                return left * right
            if expr.op == "/":
                if right == 0:
                    self._emit(Severity.ERROR, "Division by zero", expr.pos, expr)
                    return None
                res = left / right
                return int(res) if isinstance(left, int) and isinstance(right, int) and res.is_integer() else res
        return None

    def _visit_stmt(self, stmt: Stmt, symbolic_mode: bool = False) -> None:
        if not symbolic_mode:
            self._count_step(stmt.pos)

        if isinstance(stmt, Move):
            val = self._eval_expr(stmt.amount)
            if val is None:
                return
            if val < 0:
                self._emit(
                    Severity.ERROR,
                    f"Move distance must be >= 0, got {val:g}",
                    stmt.pos,
                    stmt,
                )
                return
            if not symbolic_mode:
                d = float(val) if stmt.direction == "FORWARD" else -float(val)
                rad = math.radians(self.heading)
                new_x = self.x + d * math.sin(rad)
                new_y = self.y + d * math.cos(rad)
                if not self.arena.contains(new_x, new_y):
                    self._emit(
                        Severity.ERROR,
                        f"Robot leaves arena {self.arena.describe()} at ({new_x:.2f}, {new_y:.2f})",
                        stmt.pos,
                        stmt,
                        dedupe_key="arena_oob",
                    )
                self.x = new_x
                self.y = new_y
            return

        if isinstance(stmt, Turn):
            val = self._eval_expr(stmt.angle)
            if val is None:
                return
            if val < 0 or val > 360:
                self._emit(
                    Severity.ERROR,
                    f"Turn angle must be between 0 and 360 degrees, got {val:g}",
                    stmt.pos,
                    stmt,
                )
                return
            if not symbolic_mode:
                delta = float(val) if stmt.direction == "RIGHT" else -float(val)
                self.heading = (self.heading + delta) % 360.0
            return

        if isinstance(stmt, SetVar):
            val = self._eval_expr(stmt.value)
            self.symbols.assign(stmt.name, val)
            return

        if isinstance(stmt, Repeat):
            if not stmt.body:
                self._emit(
                    Severity.WARNING,
                    "Empty REPEAT block has no effect",
                    stmt.pos,
                    stmt,
                )
            count = self._eval_expr(stmt.count)
            if count is None:
                return
            if isinstance(count, float) and not count.is_integer():
                self._emit(
                    Severity.ERROR,
                    f"REPEAT count must be a positive integer, got {count}",
                    stmt.pos,
                    stmt,
                )
                return
            int_count = int(count)
            if int_count <= 0:
                self._emit(
                    Severity.ERROR,
                    f"REPEAT count must be a positive integer (> 0), got {int_count}",
                    stmt.pos,
                    stmt,
                )
                return
            if int_count > self.max_steps:
                self._emit(
                    Severity.ERROR,
                    f"Expanded program exceeds maximum step limit ({self.max_steps}); REPEAT count {int_count} is too large",
                    stmt.pos,
                    stmt,
                )
                raise _StepLimitExceeded()
            if symbolic_mode:
                for child in stmt.body:
                    self._visit_stmt(child, symbolic_mode=True)
                return
            for _ in range(int_count):
                for child in stmt.body:
                    self._visit_stmt(child)
            return

        if isinstance(stmt, ProcDef):
            if stmt.name in self.procedures:
                self._emit(
                    Severity.ERROR,
                    f"Procedure '{stmt.name}' is already defined",
                    stmt.pos,
                    stmt,
                )
                return
            seen_params: set[str] = set()
            for p in stmt.params:
                if p in seen_params:
                    self._emit(
                        Severity.ERROR,
                        f"Duplicate parameter '{p}' in procedure '{stmt.name}'",
                        stmt.pos,
                        stmt,
                    )
                seen_params.add(p)
            self.procedures[stmt.name] = stmt
            return

        if isinstance(stmt, ProcCall):
            if stmt.name not in self.procedures:
                self._emit(
                    Severity.ERROR,
                    f"Undefined procedure '{stmt.name}'",
                    stmt.pos,
                    stmt,
                )
                return
            proc = self.procedures[stmt.name]
            self.called_procs.add(stmt.name)
            if len(stmt.args) != len(proc.params):
                self._emit(
                    Severity.ERROR,
                    f"Procedure '{stmt.name}' expects {len(proc.params)} argument(s), got {len(stmt.args)}",
                    stmt.pos,
                    stmt,
                )
                return
            arg_vals = [self._eval_expr(arg) for arg in stmt.args]
            if self.call_depth >= self.max_call_depth:
                self._emit(
                    Severity.ERROR,
                    f"Maximum procedure call depth ({self.max_call_depth}) exceeded in '{stmt.name}'",
                    stmt.pos,
                    stmt,
                )
                raise _StepLimitExceeded()
            self.call_depth += 1
            self.symbols.push_scope(dict(zip(proc.params, arg_vals)))
            try:
                for child in proc.body:
                    self._visit_stmt(child, symbolic_mode=symbolic_mode)
            finally:
                self.symbols.pop_scope()
                self.call_depth -= 1
            return

        if isinstance(stmt, IfStmt):
            if not stmt.then_body:
                self._emit(Severity.WARNING, "Empty IF block has no effect", stmt.pos, stmt)
            left = self._eval_expr(stmt.left)
            right = self._eval_expr(stmt.right)
            if left is None or right is None:
                if symbolic_mode:
                    for child in stmt.then_body:
                        self._visit_stmt(child, symbolic_mode=True)
                    if stmt.else_body:
                        for child in stmt.else_body:
                            self._visit_stmt(child, symbolic_mode=True)
                return
            cond = _eval_comparison(stmt.op, left, right)
            branch = stmt.then_body if cond else (stmt.else_body or [])
            for child in branch:
                self._visit_stmt(child, symbolic_mode=symbolic_mode)


def _eval_comparison(op: str, left: int | float, right: int | float) -> bool:
    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    if op == "<":
        return left < right
    if op == "<=":
        return left <= right
    if op == ">":
        return left > right
    if op == ">=":
        return left >= right
    return False


def analyze(
    program: Program,
    arena: ArenaConfig | None = None,
    max_steps: int = 10_000,
) -> SemanticResult:
    """Convenience helper to semantically analyze a parsed Program."""
    return SemanticAnalyzer(arena=arena, max_steps=max_steps).analyze(program)
