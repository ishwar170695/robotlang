"""Target code generator: lowers flat IR into Microchip PIC16F877A assembly (pic-as)."""

from __future__ import annotations

from robotlang.ir import IRInstr, IROp, unroll_ir

_PIC_HEADER = [
    "; ============================================================",
    "; Target: Microchip PIC16F877A (MPLAB X pic-as Assembler)",
    "; Port B Motor Pins: RB0=L_FWD, RB1=L_REV, RB2=R_FWD, RB3=R_REV",
    "; ============================================================",
    "    PROCESSOR 16F877A",
    "    #include <xc.inc>",
    "",
    "    PSECT resetVec,class=CODE,delta=2,abs",
    "    ORG 0x0000",
    "    GOTO START",
    "",
    "    PSECT code,class=CODE,delta=2",
    "START:",
    "    BANKSEL TRISB",
    "    CLRF TRISB",
    "    BANKSEL PORTB",
    "    CLRF PORTB",
    "",
    "    ; --- RobotLang Main Program ---",
]

_PIC_FOOTER = [
    "STOP:",
    "    GOTO STOP",
    "",
    "; --- Motor & Delay Subroutines (W = duration/angle units) ---",
    "MOVE_FWD:",
    "    MOVWF 0x20",
    "    MOVLW 0x05",
    "    MOVWF PORTB",
    "    CALL DELAY_W",
    "    CLRF PORTB",
    "    RETURN",
    "",
    "MOVE_BWD:",
    "    MOVWF 0x20",
    "    MOVLW 0x0A",
    "    MOVWF PORTB",
    "    CALL DELAY_W",
    "    CLRF PORTB",
    "    RETURN",
    "",
    "TURN_RIGHT:",
    "    MOVWF 0x20",
    "    MOVLW 0x09",
    "    MOVWF PORTB",
    "    CALL DELAY_W",
    "    CLRF PORTB",
    "    RETURN",
    "",
    "TURN_LEFT:",
    "    MOVWF 0x20",
    "    MOVLW 0x06",
    "    MOVWF PORTB",
    "    CALL DELAY_W",
    "    CLRF PORTB",
    "    RETURN",
    "",
    "DELAY_W:",
    "DELAY_LOOP:",
    "    NOP",
    "    DECFSZ 0x20, 1",
    "    GOTO DELAY_LOOP",
    "    RETURN",
    "",
    "    END",
]


def _emit_chunked_call(magnitude: int, subroutine: str) -> list[str]:
    """Emit MOVLW/CALL pairs in 8-bit (0..255) chunks for PIC16 MOVLW."""
    lines: list[str] = []
    remaining = magnitude
    while remaining > 0:
        chunk = min(255, remaining)
        lines.append(f"    MOVLW {chunk}")
        lines.append(f"    CALL {subroutine}")
        remaining -= chunk
    return lines


def generate_commands(instructions: list[IRInstr]) -> list[str]:
    """Convert IR (unrolling any remaining loops) into PIC16F877A assembly lines."""
    flat = unroll_ir(instructions)
    lines: list[str] = list(_PIC_HEADER)

    for instr in flat:
        if instr.op == IROp.MOVE:
            assert instr.arg is not None
            val = int(round(float(instr.arg)))
            if val > 0:
                lines.extend(_emit_chunked_call(val, "MOVE_FWD"))
            elif val < 0:
                lines.extend(_emit_chunked_call(-val, "MOVE_BWD"))
        elif instr.op == IROp.TURN:
            assert instr.arg is not None
            val = int(round(float(instr.arg)))
            if val > 0:
                lines.extend(_emit_chunked_call(val, "TURN_RIGHT"))
            elif val < 0:
                lines.extend(_emit_chunked_call(-val, "TURN_LEFT"))

    lines.extend(_PIC_FOOTER)
    return lines


def generate_code(instructions: list[IRInstr], separator: str = "\n") -> str:
    """Return generated PIC16F877A assembly joined by separator (default newline)."""
    return separator.join(generate_commands(instructions))
