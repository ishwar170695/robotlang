"""Recursive-descent parser for RobotLang with panic-mode error recovery."""

from __future__ import annotations

import difflib

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
    format_expr,
)
from robotlang.errors import Diagnostic, Pos, Severity
from robotlang.lexer import KEYWORDS, Token, TokenType

STATEMENT_STARTERS = {
    TokenType.FORWARD,
    TokenType.BACKWARD,
    TokenType.LEFT,
    TokenType.RIGHT,
    TokenType.REPEAT,
    TokenType.SET,
    TokenType.DEF,
    TokenType.CALL,
    TokenType.IF,
}

COMPARISON_OPS = {
    TokenType.EQ,
    TokenType.NEQ,
    TokenType.LT,
    TokenType.LE,
    TokenType.GT,
    TokenType.GE,
}


class _ParseError(Exception):
    """Internal sentinel raised to unwind to the nearest panic-mode synchronization point."""


class Parser:
    """LL(1) recursive-descent parser for RobotLang."""

    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.pos = 0
        self.diagnostics: list[Diagnostic] = []

    def _current(self) -> Token:
        return self.tokens[self.pos]

    def _previous(self) -> Token:
        return self.tokens[max(0, self.pos - 1)]

    def _at_end(self) -> bool:
        return self._current().type == TokenType.EOF

    def _advance(self) -> Token:
        tok = self._current()
        if tok.type != TokenType.EOF:
            self.pos += 1
        return tok

    def _check(self, tok_type: TokenType) -> bool:
        return self._current().type == tok_type

    def _match(self, *tok_types: TokenType) -> Token | None:
        if self._current().type in tok_types:
            return self._advance()
        return None

    def _error(self, message: str, pos: Pos | None = None) -> _ParseError:
        err_pos = pos or self._current().pos
        self.diagnostics.append(Diagnostic(Severity.ERROR, "parser", message, err_pos))
        return _ParseError(message)

    def _consume(self, tok_type: TokenType, message: str) -> Token:
        if self._check(tok_type):
            return self._advance()
        raise self._error(message)

    def _expect_semi(self, context: str) -> None:
        if self._match(TokenType.SEMI) is not None:
            return
        prev = self._previous()
        expected_pos = Pos(prev.pos.line, prev.pos.col + max(1, len(prev.lexeme)))
        self.diagnostics.append(
            Diagnostic(
                Severity.ERROR,
                "parser",
                f"Expected ';' after {context}",
                expected_pos,
            )
        )
        # If the next token is on a new line, is a statement starter, or closes a block,
        # leave it intact so parsing continues cleanly on the next statement.
        cur = self._current()
        if (
            cur.pos.line <= prev.pos.line
            and cur.type not in STATEMENT_STARTERS
            and cur.type not in (TokenType.RBRACE, TokenType.EOF)
        ):
            self._synchronize()

    def _synchronize(self) -> None:
        """Panic-mode recovery: advance until ';', '}', statement starter, or EOF."""
        while not self._at_end():
            tok = self._current()
            if tok.type == TokenType.SEMI:
                self._advance()
                return
            if tok.type == TokenType.RBRACE:
                return
            if tok.type in STATEMENT_STARTERS:
                return
            self._advance()

    # ------------------------------------------------------------------
    # Grammar rules
    # ------------------------------------------------------------------

    def parse_program(self) -> Program:
        """program = { statement } ;"""
        statements: list[Stmt] = []
        while not self._at_end():
            if self._check(TokenType.RBRACE):
                tok = self._advance()
                self.diagnostics.append(
                    Diagnostic(Severity.ERROR, "parser", "Unmatched '}'", tok.pos)
                )
                continue
            stmt = self.parse_statement()
            if stmt is not None:
                statements.append(stmt)
        return Program(statements=statements)

    def parse_statement(self) -> Stmt | None:
        """statement = move | turn | repeat | set | def | call | if ;"""
        tok = self._current()
        try:
            if tok.type in (TokenType.FORWARD, TokenType.BACKWARD):
                return self.parse_move()
            if tok.type in (TokenType.LEFT, TokenType.RIGHT):
                return self.parse_turn()
            if tok.type == TokenType.REPEAT:
                return self.parse_repeat()
            if tok.type == TokenType.SET:
                return self.parse_set()
            if tok.type == TokenType.DEF:
                return self.parse_def()
            if tok.type == TokenType.CALL:
                return self.parse_call()
            if tok.type == TokenType.IF:
                return self.parse_if()

            # Unknown token / command
            bad = self._advance()
            hint = ""
            if bad.type == TokenType.IDENT:
                matches = difflib.get_close_matches(
                    bad.lexeme.upper(), KEYWORDS.keys(), n=1, cutoff=0.6
                )
                if matches:
                    hint = f" (did you mean '{matches[0]}'?)"
                msg = f"Unknown command '{bad.lexeme}'{hint}"
            else:
                msg = f"Unexpected token {bad.lexeme!r} at start of statement"
            raise self._error(msg, bad.pos)
        except _ParseError:
            self._synchronize()
            return None

    def parse_move(self) -> Move:
        """move = ("FORWARD" | "BACKWARD") expr ";" ;"""
        kw = self._advance()
        amount = self.parse_expr()
        self._expect_semi(f"{kw.lexeme} {format_expr(amount)}")
        return Move(direction=kw.lexeme, amount=amount, pos=kw.pos)

    def parse_turn(self) -> Turn:
        """turn = ("LEFT" | "RIGHT") expr ";" ;"""
        kw = self._advance()
        angle = self.parse_expr()
        self._expect_semi(f"{kw.lexeme} {format_expr(angle)}")
        return Turn(direction=kw.lexeme, angle=angle, pos=kw.pos)

    def parse_block(self, open_context: str) -> list[Stmt]:
        """block = "{" { statement } "}" ;"""
        lbrace = self._consume(TokenType.LBRACE, f"Expected '{{' {open_context}")
        body: list[Stmt] = []
        while not self._at_end() and not self._check(TokenType.RBRACE):
            stmt = self.parse_statement()
            if stmt is not None:
                body.append(stmt)
        if not self._match(TokenType.RBRACE):
            self.diagnostics.append(
                Diagnostic(
                    Severity.ERROR,
                    "parser",
                    f"Expected '}}' to close block opened at {lbrace.pos}",
                    self._current().pos,
                )
            )
        return body

    def parse_repeat(self) -> Repeat:
        """repeat = "REPEAT" expr "{" { statement } "}" ;"""
        kw = self._advance()
        count = self.parse_expr()
        body = self.parse_block(f"after REPEAT {format_expr(count)}")
        return Repeat(count=count, body=body, pos=kw.pos)

    def parse_set(self) -> SetVar:
        """set = "SET" IDENT "=" expr ";" ;"""
        kw = self._advance()
        ident = self._consume(TokenType.IDENT, "Expected variable name after 'SET'")
        self._consume(TokenType.ASSIGN, f"Expected '=' after variable '{ident.lexeme}'")
        value = self.parse_expr()
        self._expect_semi(f"SET {ident.lexeme} = {format_expr(value)}")
        return SetVar(name=ident.lexeme, value=value, pos=kw.pos)

    def parse_def(self) -> ProcDef:
        """def = "DEF" IDENT "(" [ IDENT { "," IDENT } ] ")" "{" { statement } "}" ;"""
        kw = self._advance()
        name_tok = self._consume(TokenType.IDENT, "Expected procedure name after 'DEF'")
        self._consume(TokenType.LPAREN, f"Expected '(' after procedure name '{name_tok.lexeme}'")
        params: list[str] = []
        if not self._check(TokenType.RPAREN):
            first = self._consume(TokenType.IDENT, "Expected parameter name")
            params.append(first.lexeme)
            while self._match(TokenType.COMMA) is not None:
                if self._check(TokenType.RPAREN):
                    self.diagnostics.append(
                        Diagnostic(
                            Severity.ERROR,
                            "parser",
                            "Expected parameter name after ','",
                            self._current().pos,
                        )
                    )
                    break
                param = self._consume(TokenType.IDENT, "Expected parameter name after ','")
                params.append(param.lexeme)
        self._consume(TokenType.RPAREN, "Expected ')' after procedure parameters")
        body = self.parse_block(f"in definition of '{name_tok.lexeme}'")
        return ProcDef(name=name_tok.lexeme, params=params, body=body, pos=kw.pos)

    def parse_call(self) -> ProcCall:
        """call = "CALL" IDENT "(" [ expr { "," expr } ] ")" ";" ;"""
        kw = self._advance()
        name_tok = self._consume(TokenType.IDENT, "Expected procedure name after 'CALL'")
        self._consume(TokenType.LPAREN, f"Expected '(' after procedure name '{name_tok.lexeme}'")
        args: list[Expr] = []
        if not self._check(TokenType.RPAREN):
            args.append(self.parse_expr())
            while self._match(TokenType.COMMA) is not None:
                args.append(self.parse_expr())
        self._consume(TokenType.RPAREN, "Expected ')' after call arguments")
        self._expect_semi(f"CALL {name_tok.lexeme}(...)")
        return ProcCall(name=name_tok.lexeme, args=args, pos=kw.pos)

    def parse_if(self) -> IfStmt:
        """if = "IF" expr comp_op expr block [ "ELSE" block ] ;"""
        kw = self._advance()
        left = self.parse_expr()
        if self._current().type not in COMPARISON_OPS:
            raise self._error(
                f"Expected comparison operator (==, !=, <, <=, >, >=), got {self._current().lexeme!r}"
            )
        op_tok = self._advance()
        right = self.parse_expr()
        then_body = self.parse_block("after IF condition")
        else_body: list[Stmt] | None = None
        if self._match(TokenType.ELSE) is not None:
            else_body = self.parse_block("after ELSE")
        return IfStmt(
            left=left,
            op=op_tok.lexeme,
            right=right,
            then_body=then_body,
            else_body=else_body,
            pos=kw.pos,
        )

    def parse_expr(self) -> Expr:
        """expr = term { ("+" | "-") term } ;"""
        node = self.parse_term()
        while (op := self._match(TokenType.PLUS, TokenType.MINUS)) is not None:
            right = self.parse_term()
            node = BinaryOp(op=op.lexeme, left=node, right=right, pos=op.pos)
        return node

    def parse_term(self) -> Expr:
        """term = factor { ("*" | "/") factor } ;"""
        node = self.parse_factor()
        while (op := self._match(TokenType.STAR, TokenType.SLASH)) is not None:
            right = self.parse_factor()
            node = BinaryOp(op=op.lexeme, left=node, right=right, pos=op.pos)
        return node

    def parse_factor(self) -> Expr:
        """factor = [ "-" | "+" ] ( NUMBER | IDENT | "(" expr ")" ) ;"""
        if (op := self._match(TokenType.MINUS, TokenType.PLUS)) is not None:
            operand = self.parse_factor()
            return UnaryOp(op=op.lexeme, operand=operand, pos=op.pos)

        tok = self._current()
        if self._match(TokenType.NUMBER) is not None:
            assert isinstance(tok.value, (int, float))
            return NumberLit(value=tok.value, pos=tok.pos)

        if self._match(TokenType.IDENT) is not None:
            return VarRef(name=tok.lexeme, pos=tok.pos)

        if self._match(TokenType.LPAREN) is not None:
            expr = self.parse_expr()
            self._consume(TokenType.RPAREN, "Expected ')' after expression")
            return expr

        raise self._error(f"Expected number, variable, or '(', got {tok.lexeme!r}")


def parse(tokens: list[Token]) -> tuple[Program, list[Diagnostic]]:
    """Convenience helper returning (Program, diagnostics)."""
    parser = Parser(tokens)
    program = parser.parse_program()
    return program, parser.diagnostics
