"""Diagnostic and source-location primitives for the RobotLang compiler."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class Pos:
    """1-based source position."""

    line: int
    col: int

    def __str__(self) -> str:
        return f"Line {self.line}, col {self.col}"


@dataclass(frozen=True)
class Diagnostic:
    """Compiler error or warning with source location and phase."""

    severity: Severity
    phase: str
    message: str
    pos: Pos

    def format(self, source_lines: list[str] | None = None) -> str:
        header = f"[{self.phase}] {self.severity.value}: {self.pos}: {self.message}"
        if source_lines and 1 <= self.pos.line <= len(source_lines):
            line_text = source_lines[self.pos.line - 1].rstrip("\r\n")
            pointer = " " * max(0, self.pos.col - 1) + "^"
            return f"{header}\n  {self.pos.line:>4} | {line_text}\n       | {pointer}"
        return header

    def __str__(self) -> str:
        return self.format()

