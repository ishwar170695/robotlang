"""Abstract Syntax Tree (AST) node definitions for RobotLang."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from robotlang.errors import Pos


@dataclass(frozen=True)
class NumberLit:
    value: int | float
    pos: Pos


@dataclass(frozen=True)
class VarRef:
    name: str
    pos: Pos


@dataclass(frozen=True)
class UnaryOp:
    op: str
    operand: Expr
    pos: Pos


@dataclass(frozen=True)
class BinaryOp:
    op: str
    left: Expr
    right: Expr
    pos: Pos


Expr = Union[NumberLit, VarRef, UnaryOp, BinaryOp]


@dataclass(frozen=True)
class Move:
    direction: str  # "FORWARD" | "BACKWARD"
    amount: Expr
    pos: Pos


@dataclass(frozen=True)
class Turn:
    direction: str  # "LEFT" | "RIGHT"
    angle: Expr
    pos: Pos


@dataclass(frozen=True)
class Repeat:
    count: Expr
    body: list[Stmt]
    pos: Pos


@dataclass(frozen=True)
class SetVar:
    name: str
    value: Expr
    pos: Pos


@dataclass(frozen=True)
class ProcDef:
    name: str
    params: list[str]
    body: list[Stmt]
    pos: Pos


@dataclass(frozen=True)
class ProcCall:
    name: str
    args: list[Expr]
    pos: Pos


@dataclass(frozen=True)
class IfStmt:
    left: Expr
    op: str
    right: Expr
    then_body: list[Stmt]
    else_body: list[Stmt] | None
    pos: Pos


Stmt = Union[Move, Turn, Repeat, SetVar, ProcDef, ProcCall, IfStmt]


@dataclass(frozen=True)
class Program:
    statements: list[Stmt]


def format_expr(expr: Expr) -> str:
    """Return a concise inline representation of an expression node."""
    if isinstance(expr, NumberLit):
        return repr(expr.value)
    if isinstance(expr, VarRef):
        return expr.name
    if isinstance(expr, UnaryOp):
        return f"({expr.op}{format_expr(expr.operand)})"
    if isinstance(expr, BinaryOp):
        return f"({format_expr(expr.left)} {expr.op} {format_expr(expr.right)})"
    return repr(expr)


def format_ast(program: Program) -> str:
    """Format a Program AST as a readable indented tree."""
    lines: list[str] = ["Program"]

    def _visit_stmt(stmt: Stmt, indent: int) -> None:
        pad = "  " * indent
        if isinstance(stmt, Move):
            lines.append(f"{pad}Move(dir={stmt.direction}, amount={format_expr(stmt.amount)}) @{stmt.pos}")
        elif isinstance(stmt, Turn):
            lines.append(f"{pad}Turn(dir={stmt.direction}, angle={format_expr(stmt.angle)}) @{stmt.pos}")
        elif isinstance(stmt, Repeat):
            lines.append(f"{pad}Repeat(count={format_expr(stmt.count)}) @{stmt.pos}")
            for child in stmt.body:
                _visit_stmt(child, indent + 1)
        elif isinstance(stmt, SetVar):
            lines.append(f"{pad}SetVar(name={stmt.name}, value={format_expr(stmt.value)}) @{stmt.pos}")
        elif isinstance(stmt, ProcDef):
            params = ", ".join(stmt.params)
            lines.append(f"{pad}ProcDef(name={stmt.name}, params=[{params}]) @{stmt.pos}")
            for child in stmt.body:
                _visit_stmt(child, indent + 1)
        elif isinstance(stmt, ProcCall):
            args = ", ".join(format_expr(a) for a in stmt.args)
            lines.append(f"{pad}ProcCall(name={stmt.name}, args=[{args}]) @{stmt.pos}")
        elif isinstance(stmt, IfStmt):
            cond = f"{format_expr(stmt.left)} {stmt.op} {format_expr(stmt.right)}"
            lines.append(f"{pad}IfStmt(cond={cond}) @{stmt.pos}")
            lines.append(f"{pad}  Then:")
            for child in stmt.then_body:
                _visit_stmt(child, indent + 2)
            if stmt.else_body is not None:
                lines.append(f"{pad}  Else:")
                for child in stmt.else_body:
                    _visit_stmt(child, indent + 2)

    for s in program.statements:
        _visit_stmt(s, 1)
    return "\n".join(lines)

