# RobotLang Grammar Specification

## Lexical Elements

- **Whitespace**: spaces, tabs, carriage returns, newlines (ignored between tokens).
- **Comments**: `#` through end of line.
- **Keywords**: `FORWARD`, `BACKWARD`, `LEFT`, `RIGHT`, `REPEAT`, `SET`, `DEF`, `CALL`, `IF`, `ELSE`.
- **Numbers**: integer (`[0-9]+`) or floating-point (`[0-9]+\.[0-9]+`).
- **Identifiers**: `[A-Za-z_][A-Za-z0-9_]*` (excluding keywords).
- **Operators & Punctuation**: `+`, `-`, `*`, `/`, `=`, `==`, `!=`, `<`, `<=`, `>`, `>=`, `{`, `}`, `(`, `)`, `;`, `,`.

## EBNF Grammar

```ebnf
program    = { statement } ;

statement  = move
           | turn
           | repeat
           | set_var
           | proc_def
           | proc_call
           | if_stmt ;

move       = ("FORWARD" | "BACKWARD") expr ";" ;
turn       = ("LEFT" | "RIGHT") expr ";" ;
repeat     = "REPEAT" expr block ;
set_var    = "SET" IDENT "=" expr ";" ;
proc_def   = "DEF" IDENT "(" [ IDENT { "," IDENT } ] ")" block ;
proc_call  = "CALL" IDENT "(" [ expr { "," expr } ] ")" ";" ;
if_stmt    = "IF" expr comp_op expr block [ "ELSE" block ] ;

block      = "{" { statement } "}" ;

comp_op    = "==" | "!=" | "<" | "<=" | ">" | ">=" ;
expr       = term { ("+" | "-") term } ;
term       = factor { ("*" | "/") factor } ;
factor     = [ "-" | "+" ] ( NUMBER | IDENT | "(" expr ")" ) ;
```

## Why the Grammar is LL(1)

Every alternative of `statement` begins with a **pairwise-disjoint** single-token `FIRST` set:

| Production | `FIRST` set |
|---|---|
| `move` | `{ "FORWARD", "BACKWARD" }` |
| `turn` | `{ "LEFT", "RIGHT" }` |
| `repeat` | `{ "REPEAT" }` |
| `set_var` | `{ "SET" }` |
| `proc_def` | `{ "DEF" }` |
| `proc_call` | `{ "CALL" }` |
| `if_stmt` | `{ "IF" }` |

Expression grammar (`expr` -> `term` -> `factor`) uses left-factored EBNF iteration (`{ ... }`) rather than left recursion, so a predictive recursive-descent parser needs only **1 token of lookahead** and zero backtracking.

