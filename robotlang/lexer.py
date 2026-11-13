"""Hand-written lexical analyzer for RobotLang."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from robotlang.errors import Diagnostic, Pos, Severity


class TokenType(str, Enum):
    # Keywords
    FORWARD = "FORWARD"
    BACKWARD = "BACKWARD"
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    REPEAT = "REPEAT"
    SET = "SET"
    DEF = "DEF"
    CALL = "CALL"
    IF = "IF"
    ELSE = "ELSE"

    # Literals & identifiers
    NUMBER = "NUMBER"
    IDENT = "IDENT"

    # Delimiters
    LBRACE = "LBRACE"
    RBRACE = "RBRACE"
    LPAREN = "LPAREN"
    RPAREN = "RPAREN"
    SEMI = "SEMI"
    COMMA = "COMMA"
    ASSIGN = "ASSIGN"

    # Arithmetic operators
    PLUS = "PLUS"
    MINUS = "MINUS"
    STAR = "STAR"
    SLASH = "SLASH"

    # Comparison operators
    EQ = "EQ"
    NEQ = "NEQ"
    LT = "LT"
    LE = "LE"
    GT = "GT"
    GE = "GE"

    EOF = "EOF"


KEYWORDS: dict[str, TokenType] = {
    "FORWARD": TokenType.FORWARD,
    "BACKWARD": TokenType.BACKWARD,
    "LEFT": TokenType.LEFT,
    "RIGHT": TokenType.RIGHT,
    "REPEAT": TokenType.REPEAT,
    "SET": TokenType.SET,
    "DEF": TokenType.DEF,
    "CALL": TokenType.CALL,
    "IF": TokenType.IF,
    "ELSE": TokenType.ELSE,
}

SINGLE_CHAR_TOKENS: dict[str, TokenType] = {
    "{": TokenType.LBRACE,
    "}": TokenType.RBRACE,
    "(": TokenType.LPAREN,
    ")": TokenType.RPAREN,
    ";": TokenType.SEMI,
    ",": TokenType.COMMA,
    "+": TokenType.PLUS,
    "-": TokenType.MINUS,
    "*": TokenType.STAR,
    "/": TokenType.SLASH,
}


@dataclass(frozen=True)
class Token:
    type: TokenType
    lexeme: str
    value: int | float | str | None
    pos: Pos

    def __str__(self) -> str:
        return f"{self.pos.line:>3}:{self.pos.col:<3} {self.type.value:<10} {self.lexeme!r}"


class Lexer:
    """Character-cursor lexer producing tokens with 1-based line and column positions."""

    def __init__(self, source: str) -> None:
        self.source = source
        self.length = len(source)
        self.index = 0
        self.line = 1
        self.col = 1
        self.diagnostics: list[Diagnostic] = []

    def _peek(self, offset: int = 0) -> str:
        idx = self.index + offset
        if idx >= self.length:
            return "\0"
        return self.source[idx]

    def _advance(self) -> str:
        ch = self.source[self.index]
        self.index += 1
        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def _skip_whitespace_and_comments(self) -> None:
        while self.index < self.length:
            ch = self._peek()
            if ch in (" ", "\t", "\r", "\n"):
                self._advance()
            elif ch == "#":
                while self.index < self.length and self._peek() != "\n":
                    self._advance()
            else:
                break

    def _read_number(self, start_pos: Pos) -> Token:
        chars: list[str] = []
        while self._peek().isdigit():
            chars.append(self._advance())

        is_float = False
        if self._peek() == "." and self._peek(1).isdigit():
            is_float = True
            chars.append(self._advance())  # consume '.'
            while self._peek().isdigit():
                chars.append(self._advance())
        elif self._peek() == "." and not self._peek(1).isdigit():
            # Trailing dot like `5.` — report error and consume dot to recover cleanly.
            dot_pos = Pos(self.line, self.col)
            self._advance()
            self.diagnostics.append(
                Diagnostic(
                    Severity.ERROR,
                    "lexer",
                    "Malformed number: expected digits after '.'",
                    dot_pos,
                )
            )

        lexeme = "".join(chars)
        value: int | float = float(lexeme) if is_float else int(lexeme)
        return Token(TokenType.NUMBER, lexeme, value, start_pos)

    def _read_ident_or_keyword(self, start_pos: Pos) -> Token:
        chars: list[str] = []
        while self._peek().isalnum() or self._peek() == "_":
            chars.append(self._advance())
        lexeme = "".join(chars)
        tok_type = KEYWORDS.get(lexeme, TokenType.IDENT)
        return Token(tok_type, lexeme, lexeme, start_pos)

    def tokenize(self) -> list[Token]:
        """Scan the entire source string into a list of Tokens ending with EOF."""
        tokens: list[Token] = []

        while True:
            self._skip_whitespace_and_comments()
            if self.index >= self.length:
                tokens.append(Token(TokenType.EOF, "", None, Pos(self.line, self.col)))
                break

            start_pos = Pos(self.line, self.col)
            ch = self._peek()

            if ch.isdigit():
                tokens.append(self._read_number(start_pos))
                continue

            if ch.isalpha() or ch == "_":
                tokens.append(self._read_ident_or_keyword(start_pos))
                continue

            if ch in SINGLE_CHAR_TOKENS:
                self._advance()
                tokens.append(Token(SINGLE_CHAR_TOKENS[ch], ch, ch, start_pos))
                continue

            if ch == "=":
                self._advance()
                if self._peek() == "=":
                    self._advance()
                    tokens.append(Token(TokenType.EQ, "==", "==", start_pos))
                else:
                    tokens.append(Token(TokenType.ASSIGN, "=", "=", start_pos))
                continue

            if ch == "!":
                self._advance()
                if self._peek() == "=":
                    self._advance()
                    tokens.append(Token(TokenType.NEQ, "!=", "!=", start_pos))
                else:
                    self.diagnostics.append(
                        Diagnostic(
                            Severity.ERROR,
                            "lexer",
                            "Unexpected '!'; did you mean '!='?",
                            start_pos,
                        )
                    )
                continue

            if ch == "<":
                self._advance()
                if self._peek() == "=":
                    self._advance()
                    tokens.append(Token(TokenType.LE, "<=", "<=", start_pos))
                else:
                    tokens.append(Token(TokenType.LT, "<", "<", start_pos))
                continue

            if ch == ">":
                self._advance()
                if self._peek() == "=":
                    self._advance()
                    tokens.append(Token(TokenType.GE, ">=", ">=", start_pos))
                else:
                    tokens.append(Token(TokenType.GT, ">", ">", start_pos))
                continue

            # Unrecognized character: emit diagnostic and advance to continue scanning.
            self._advance()
            self.diagnostics.append(
                Diagnostic(
                    Severity.ERROR,
                    "lexer",
                    f"Unexpected character {ch!r}",
                    start_pos,
                )
            )

        return tokens


def lex(source: str) -> tuple[list[Token], list[Diagnostic]]:
    """Convenience helper returning (tokens, diagnostics)."""
    lexer = Lexer(source)
    return lexer.tokenize(), lexer.diagnostics

