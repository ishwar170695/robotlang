"""Tests for IR generation, loop expansion, optimization, codegen, simulator, and all examples."""

from pathlib import Path

import pytest

from robotlang.cli import main as cli_main
from robotlang.compiler import compile_source
from robotlang.ir import format_ir
from robotlang.semantic import ArenaConfig
from robotlang.simulator import extract_pic_actions, render_matplotlib, simulate_commands

ROOT = Path(__file__).resolve().parent.parent
VALID_DIR = ROOT / "examples" / "valid"
INVALID_DIR = ROOT / "examples" / "invalid"


def test_ir_structured_vs_unrolled():
    res = compile_source("FORWARD 5; RIGHT 90; REPEAT 4 { FORWARD 2; }", optimize=False)
    assert res.success
    structured_txt = format_ir(res.structured_ir)
    assert "LOOP_BEGIN 4" in structured_txt
    assert "LOOP_END" in structured_txt
    assert len(res.unrolled_ir) == 6  # MOVE 5, TURN 90, 4x MOVE 2


def test_optimizer_merges_and_drops_noops():
    src = (
        "FORWARD 2; FORWARD 3; FORWARD 0; "
        "RIGHT 90; RIGHT 90; RIGHT 360; "
        "LEFT 45; RIGHT 45;"
    )
    res = compile_source(src, optimize=True)
    assert res.success
    assert res.opt_stats is not None
    assert res.opt_stats.before_count == 8
    assert res.opt_stats.after_count == 2
    assert "PROCESSOR 16F877A" in "\n".join(res.commands)
    assert extract_pic_actions(res.commands) == [
        ("MOVE_FWD", 5.0, "MOVLW 5 -> CALL MOVE_FWD"),
        ("TURN_RIGHT", 180.0, "MOVLW 180 -> CALL TURN_RIGHT"),
    ]


def test_pic16_chunking_over_255_and_backward_left():
    src = "FORWARD 300; RIGHT 270; BACKWARD 50; LEFT 90;"
    res = compile_source(src, arena=ArenaConfig.from_size(800))
    assert res.success
    asm_text = "\n".join(res.commands)
    assert "PSECT resetVec,class=CODE,delta=2,abs" in asm_text
    assert "DECFSZ 0x20, 1" in asm_text
    actions = extract_pic_actions(res.commands)
    assert actions == [
        ("MOVE_FWD", 255.0, "MOVLW 255 -> CALL MOVE_FWD"),
        ("MOVE_FWD", 45.0, "MOVLW 45 -> CALL MOVE_FWD"),
        ("TURN_RIGHT", 255.0, "MOVLW 255 -> CALL TURN_RIGHT"),
        ("TURN_RIGHT", 15.0, "MOVLW 15 -> CALL TURN_RIGHT"),
        ("MOVE_BWD", 50.0, "MOVLW 50 -> CALL MOVE_BWD"),
        ("TURN_LEFT", 90.0, "MOVLW 90 -> CALL TURN_LEFT"),
    ]
    sim = simulate_commands(res.commands)
    assert sim.final_state.x == pytest.approx(50.0, abs=1e-9)
    assert sim.final_state.y == pytest.approx(300.0, abs=1e-9)
    assert sim.final_state.heading == pytest.approx(180.0, abs=1e-9)


def test_optimizer_reduces_merged_turns_mod_360():
    res = compile_source("RIGHT 200; RIGHT 200;", optimize=True)
    assert res.success
    assert extract_pic_actions(res.commands) == [
        ("TURN_RIGHT", 40.0, "MOVLW 40 -> CALL TURN_RIGHT"),
    ]


def test_square_returns_to_origin_heading_zero():
    src = (VALID_DIR / "square.rbt").read_text(encoding="utf-8")
    res = compile_source(src)
    assert res.success
    sim = simulate_commands(res.commands)
    assert sim.final_state.x == pytest.approx(0.0, abs=1e-9)
    assert sim.final_state.y == pytest.approx(0.0, abs=1e-9)
    assert sim.final_state.heading % 360.0 == pytest.approx(0.0, abs=1e-9)
    assert len(sim.segments) == 4


def test_triangle_returns_to_origin_heading_zero():
    src = (VALID_DIR / "triangle.rbt").read_text(encoding="utf-8")
    res = compile_source(src)
    assert res.success
    sim = simulate_commands(res.commands)
    assert sim.final_state.x == pytest.approx(0.0, abs=1e-9)
    assert sim.final_state.y == pytest.approx(0.0, abs=1e-9)
    assert sim.final_state.heading % 360.0 == pytest.approx(0.0, abs=1e-9)


def test_spiral_variables_and_trajectory():
    src = (VALID_DIR / "spiral.rbt").read_text(encoding="utf-8")
    res = compile_source(src)
    assert res.success
    sim = simulate_commands(res.commands)
    assert len(sim.segments) == 10
    assert sim.final_state.x == pytest.approx(24.0, abs=1e-9)
    assert sim.final_state.y == pytest.approx(20.0, abs=1e-9)


@pytest.mark.parametrize("rbt_file", sorted(VALID_DIR.glob("*.rbt")), ids=lambda p: p.name)
def test_all_valid_examples_compile_and_simulate(rbt_file: Path):
    src = rbt_file.read_text(encoding="utf-8")
    res = compile_source(src)
    assert res.success, f"{rbt_file.name} failed: {res.errors}"
    sim = simulate_commands(res.commands)
    assert sim.final_state is not None


@pytest.mark.parametrize("rbt_file", sorted(INVALID_DIR.glob("*.rbt")), ids=lambda p: p.name)
def test_all_invalid_examples_fail_with_diagnostics(rbt_file: Path):
    src = rbt_file.read_text(encoding="utf-8")
    res = compile_source(src)
    assert not res.success, f"Expected {rbt_file.name} to fail, but it succeeded"
    assert len(res.errors) >= 1


def test_matplotlib_png_export(tmp_path: Path):
    src = (VALID_DIR / "star.rbt").read_text(encoding="utf-8")
    res = compile_source(src)
    assert res.success
    sim = simulate_commands(res.commands)
    out_png = tmp_path / "star.png"
    saved = render_matplotlib(sim, output_path=out_png, show=False)
    assert saved is not None and saved.exists() and saved.stat().st_size > 0


def test_cli_subcommands(capsys):
    sq = str(VALID_DIR / "square.rbt")
    assert cli_main(["tokens", sq]) == 0
    assert "REPEAT" in capsys.readouterr().out

    assert cli_main(["ast", sq]) == 0
    assert "Repeat(" in capsys.readouterr().out

    assert cli_main(["ir", sq]) == 0
    ir_out = capsys.readouterr().out
    assert "LOOP_BEGIN 4" in ir_out and "Unrolled Flat IR" in ir_out

    assert cli_main(["asm", sq]) == 0
    asm_out = capsys.readouterr().out
    assert "PROCESSOR 16F877A" in asm_out
    assert "MOVLW 20" in asm_out
    assert "CALL MOVE_FWD" in asm_out

    assert cli_main(["run", sq]) == 0
    run_out = capsys.readouterr().out
    assert "Execution Trace" in run_out

    bad = str(INVALID_DIR / "missing_semi.rbt")
    assert cli_main(["check", bad]) == 1


def test_cli_ir_unrolled_shows_pre_optimization_ir(capsys):
    opt_case = str(VALID_DIR / "optimizer_case.rbt")
    assert cli_main(["ir", opt_case, "--unrolled"]) == 0
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 9
    assert lines[0] == "MOVE 2"
    assert lines[1] == "MOVE 3"
    assert lines[2] == "MOVE 0"
    assert lines[7] == "TURN -90"
    assert lines[8] == "TURN 90"


def test_playground_app_compiles_and_drives():
    import tkinter as tk

    from robotlang.playground import RobotPlaygroundApp

    try:
        root = tk.Tk()
        root.withdraw()
    except tk.TclError:
        pytest.skip("No display available for Tkinter")

    try:
        app = RobotPlaygroundApp(root, initial_source="FORWARD 10; RIGHT 90;")
        app.run_instant()
        assert app.robot_state.x == pytest.approx(0.0, abs=1e-9)
        assert app.robot_state.y == pytest.approx(10.0, abs=1e-9)
        assert app.robot_state.heading == pytest.approx(90.0, abs=1e-9)

        app.drive_command("FORWARD 10;")
        assert app.robot_state.x == pytest.approx(10.0, abs=1e-9)
        assert app.robot_state.y == pytest.approx(10.0, abs=1e-9)
        assert "FORWARD 10;" in app.editor.get("1.0", tk.END)
    finally:
        root.destroy()


def test_playground_step_once_recompiles_after_edit():
    import tkinter as tk

    from robotlang.playground import RobotPlaygroundApp

    try:
        root = tk.Tk()
        root.withdraw()
    except tk.TclError:
        pytest.skip("No display available for Tkinter")

    try:
        app = RobotPlaygroundApp(root, initial_source="FORWARD 10;")
        app.step_once()
        assert app.robot_state.y == pytest.approx(10.0, abs=1e-9)

        app.editor.delete("1.0", tk.END)
        app.editor.insert("1.0", "FORWARD 25;")
        app.step_once()
        assert app.robot_state.y == pytest.approx(25.0, abs=1e-9)
    finally:
        root.destroy()


def test_playground_default_start_drive_and_clear_all():
    import tkinter as tk

    from robotlang.playground import RobotPlaygroundApp

    try:
        root = tk.Tk()
        root.withdraw()
    except tk.TclError:
        pytest.skip("No display available for Tkinter")

    try:
        app = RobotPlaygroundApp(root)
        app.drive_command("FORWARD 10;")
        assert app.robot_state.x == pytest.approx(0.0, abs=1e-9)
        assert app.robot_state.y == pytest.approx(10.0, abs=1e-9)
        assert len(app.segments) == 1

        app.clear_all()
        assert app.editor.get("1.0", tk.END).strip() == ""
        assert app.robot_state.x == 0.0 and app.robot_state.y == 0.0
        assert app.segments == []
    finally:
        root.destroy()

