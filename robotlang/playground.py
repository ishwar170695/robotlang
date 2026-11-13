"""Interactive Tkinter playground wired directly to the RobotLang compiler pipeline."""

from __future__ import annotations

import math
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from robotlang.ast_nodes import format_ast
from robotlang.compiler import CompileResult, compile_source
from robotlang.ir import format_ir
from robotlang.semantic import ArenaConfig
from robotlang.simulator import RobotState, Segment, simulate_commands

DEFAULT_SCRIPT = "# Write RobotLang here, choose an Example above, or use the Drive Pad.\n"


class RobotPlaygroundApp:
    """Interactive Tkinter GUI over compile_source() and simulate_commands()."""

    def __init__(
        self,
        root: tk.Tk,
        initial_source: str | None = None,
        arena: ArenaConfig | None = None,
    ) -> None:
        self.root = root
        self.arena = arena or ArenaConfig()
        self.root.title("RobotLang Interactive Playground")
        self.root.geometry("1180x760")

        self.examples = self._discover_examples()
        self.segments: list[Segment] = []
        self.robot_state = RobotState()
        self.pending_commands: list[str] = []
        self.compiled_source: str | None = None
        self.step_index = 0
        self.anim_job: str | None = None

        self._build_ui()
        self.editor.insert("1.0", initial_source if initial_source is not None else DEFAULT_SCRIPT)
        self._redraw_canvas()
        self._update_hud("Ready — click 'Compile & Play' or use the Drive Pad.")

    def _discover_examples(self) -> dict[str, Path]:
        examples_root = Path(__file__).resolve().parent.parent / "examples"
        found: dict[str, Path] = {}
        for folder in ("valid", "invalid"):
            d = examples_root / folder
            if d.is_dir():
                for p in sorted(d.glob("*.rbt")):
                    found[f"{folder}/{p.name}"] = p
        return found

    def _build_ui(self) -> None:
        main_pane = ttk.PanedWindow(self.root, orient=tk.VERTICAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        top_pane = ttk.PanedWindow(main_pane, orient=tk.HORIZONTAL)
        main_pane.add(top_pane, weight=3)

        # ---- Left: Editor + Controls + Drive Pad ----
        left_frame = ttk.Frame(top_pane, padding=4)
        top_pane.add(left_frame, weight=1)

        ex_bar = ttk.Frame(left_frame)
        ex_bar.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(ex_bar, text="Example:").pack(side=tk.LEFT)
        self.example_var = tk.StringVar()
        ex_combo = ttk.Combobox(
            ex_bar,
            textvariable=self.example_var,
            values=list(self.examples.keys()),
            state="readonly",
            width=28,
        )
        ex_combo.pack(side=tk.LEFT, padx=6)
        ex_combo.bind("<<ComboboxSelected>>", self._on_load_example)

        self.editor = tk.Text(
            left_frame,
            wrap=tk.NONE,
            font=("Consolas", 11),
            width=46,
            height=18,
            undo=True,
        )
        self.editor.pack(fill=tk.BOTH, expand=True)

        run_bar = ttk.Frame(left_frame)
        run_bar.pack(fill=tk.X, pady=6)
        ttk.Button(run_bar, text="Compile & Play", command=self.compile_and_play).pack(side=tk.LEFT, padx=2)
        ttk.Button(run_bar, text="Run Instant", command=self.run_instant).pack(side=tk.LEFT, padx=2)
        ttk.Button(run_bar, text="Step", command=self.step_once).pack(side=tk.LEFT, padx=2)
        ttk.Button(run_bar, text="Reset Pose", command=self.reset_robot).pack(side=tk.LEFT, padx=2)
        ttk.Button(run_bar, text="Clear All", command=self.clear_all).pack(side=tk.LEFT, padx=2)

        speed_bar = ttk.Frame(left_frame)
        speed_bar.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(speed_bar, text="Step Delay (ms):").pack(side=tk.LEFT)
        self.delay_var = tk.IntVar(value=200)
        ttk.Scale(speed_bar, from_=40, to=600, variable=self.delay_var, orient=tk.HORIZONTAL).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=6
        )

        pad = ttk.LabelFrame(left_frame, text="Interactive Drive Pad (appends & runs)", padding=6)
        pad.pack(fill=tk.X)

        ttk.Button(pad, text="▲ Forward 10", command=lambda: self.drive_command("FORWARD 10;")).grid(
            row=0, column=1, padx=3, pady=2
        )
        ttk.Button(pad, text="↺ Left 45°", command=lambda: self.drive_command("LEFT 45;")).grid(
            row=1, column=0, padx=3, pady=2
        )
        ttk.Label(pad, text="⊕", foreground="#64748b").grid(row=1, column=1, padx=3, pady=2)
        ttk.Button(pad, text="↻ Right 45°", command=lambda: self.drive_command("RIGHT 45;")).grid(
            row=1, column=2, padx=3, pady=2
        )
        ttk.Button(pad, text="▼ Back 10", command=lambda: self.drive_command("BACKWARD 10;")).grid(
            row=2, column=1, padx=3, pady=2
        )
        for col in range(3):
            pad.columnconfigure(col, weight=1)

        # ---- Right: Arena Canvas + HUD ----
        right_frame = ttk.Frame(top_pane, padding=4)
        top_pane.add(right_frame, weight=1)

        self.hud_var = tk.StringVar()
        ttk.Label(right_frame, textvariable=self.hud_var, font=("Consolas", 10)).pack(
            anchor=tk.W, pady=(0, 4)
        )

        self.canvas = tk.Canvas(
            right_frame,
            width=480,
            height=480,
            bg="#ffffff",
            highlightthickness=1,
            highlightbackground="#94a3b8",
            takefocus=True,
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", lambda _e: self._redraw_canvas())
        self.canvas.bind("<Button-1>", lambda _e: self.canvas.focus_set())
        self.canvas.bind("<Up>", lambda _e: self.drive_command("FORWARD 10;"))
        self.canvas.bind("<Down>", lambda _e: self.drive_command("BACKWARD 10;"))
        self.canvas.bind("<Left>", lambda _e: self.drive_command("LEFT 45;"))
        self.canvas.bind("<Right>", lambda _e: self.drive_command("RIGHT 45;"))

        # ---- Bottom: Inspector Notebook ----
        bottom_frame = ttk.Frame(main_pane, padding=2)
        main_pane.add(bottom_frame, weight=1)

        self.notebook = ttk.Notebook(bottom_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.tab_diag = self._add_tab("Diagnostics & Trace")
        self.tab_tokens = self._add_tab("Tokens")
        self.tab_ast = self._add_tab("AST")
        self.tab_ir = self._add_tab("IR & Optimizer")
        self.tab_asm = self._add_tab("Robot Commands")

    def _add_tab(self, title: str) -> tk.Text:
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text=title)
        text = tk.Text(frame, font=("Consolas", 10), height=9, state=tk.DISABLED)
        scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        return text

    def _set_text(self, widget: tk.Text, content: str) -> None:
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert("1.0", content)
        widget.configure(state=tk.DISABLED)

    def _on_load_example(self, _event: object) -> None:
        key = self.example_var.get()
        path = self.examples.get(key)
        if path and path.is_file():
            self.editor.delete("1.0", tk.END)
            self.editor.insert("1.0", path.read_text(encoding="utf-8"))
            self.reset_robot()

    def _cancel_animation(self) -> None:
        if self.anim_job is not None:
            self.root.after_cancel(self.anim_job)
            self.anim_job = None

    def reset_robot(self) -> None:
        self._cancel_animation()
        self.segments = []
        self.robot_state = RobotState()
        self.pending_commands = []
        self.compiled_source = None
        self.step_index = 0
        self._redraw_canvas()
        self._update_hud("Reset to (0.00, 0.00), heading 0.0°")

    def clear_all(self) -> None:
        """Clear the editor, inspector tabs, and reset the robot to (0, 0)."""
        self.editor.delete("1.0", tk.END)
        self.example_var.set("")
        for tab in (self.tab_diag, self.tab_tokens, self.tab_ast, self.tab_ir, self.tab_asm):
            self._set_text(tab, "")
        self.reset_robot()
        self._update_hud("Cleared editor and reset to (0.00, 0.00), heading 0.0°")

    def _compile_source_to_tabs(self, source: str) -> CompileResult | None:
        result = compile_source(source, optimize=True, arena=self.arena)
        self._set_text(self.tab_tokens, "\n".join(str(t) for t in result.tokens))
        self._set_text(self.tab_ast, format_ast(result.ast) if result.ast else "(no AST)")

        src_lines = source.splitlines()
        diag_text = "\n".join(d.format(src_lines) for d in result.diagnostics)

        if not result.success:
            self._set_text(self.tab_diag, diag_text)
            self._set_text(self.tab_ir, "(compilation failed)")
            self._set_text(self.tab_asm, "(compilation failed)")
            self.notebook.select(0)
            self._update_hud(f"Compilation failed with {len(result.errors)} error(s)")
            return None

        ir_sections = [
            "=== Structured IR ===",
            format_ir(result.structured_ir) or "(empty)",
            "",
            f"=== Optimized Flat IR ({result.opt_stats.summary() if result.opt_stats else ''}) ===",
            format_ir(result.optimized_ir) or "(empty)",
        ]
        self._set_text(self.tab_ir, "\n".join(ir_sections))
        self._set_text(self.tab_asm, "\n".join(result.commands) or "(no commands)")

        sim = simulate_commands(result.commands)
        trace_header = (diag_text + "\n\n") if diag_text else ""
        self._set_text(self.tab_diag, trace_header + (sim.format_trace() or "(empty program)"))
        return result

    def compile_and_play(self) -> None:
        source = self.editor.get("1.0", tk.END)
        result = self._compile_source_to_tabs(source)
        if result is None:
            return
        self.reset_robot()
        self.pending_commands = list(result.commands)
        self.compiled_source = source
        self.step_index = 0
        self._animate_next()

    def run_instant(self) -> None:
        result = self._compile_source_to_tabs(self.editor.get("1.0", tk.END))
        if result is None:
            return
        self.reset_robot()
        sim = simulate_commands(result.commands)
        self.segments = sim.segments
        self.robot_state = sim.final_state
        self._redraw_canvas()
        opt_info = result.opt_stats.summary() if result.opt_stats else ""
        self._update_hud(opt_info)

    def step_once(self) -> None:
        self._cancel_animation()
        source = self.editor.get("1.0", tk.END)
        if not self.pending_commands or source != self.compiled_source:
            result = self._compile_source_to_tabs(source)
            if result is None:
                return
            self.reset_robot()
            self.pending_commands = list(result.commands)
            self.compiled_source = source
            self.step_index = 0

        if self.step_index >= len(self.pending_commands):
            self.pending_commands = []
            self.compiled_source = None
            self.step_index = 0
            self._update_hud("Program finished.")
            return

        cmd = self.pending_commands[self.step_index]
        self.step_index += 1
        self._apply_robot_command(cmd)
        self._redraw_canvas()
        self._update_hud(f"Step {self.step_index}/{len(self.pending_commands)}: {cmd}")

    def _animate_next(self) -> None:
        if self.step_index >= len(self.pending_commands):
            self.anim_job = None
            self.pending_commands = []
            self.compiled_source = None
            self.step_index = 0
            self._update_hud("Finished.")
            return
        cmd = self.pending_commands[self.step_index]
        self.step_index += 1
        self._apply_robot_command(cmd)
        self._redraw_canvas()
        self._update_hud(f"Running {self.step_index}/{len(self.pending_commands)}: {cmd}")
        self.anim_job = self.root.after(max(20, int(self.delay_var.get())), self._animate_next)

    def _apply_robot_command(self, cmd: str) -> None:
        parts = cmd.split()
        op = parts[0].upper()
        if op == "MOVE":
            d = float(parts[1])
            rad = math.radians(self.robot_state.heading)
            nx = self.robot_state.x + d * math.sin(rad)
            ny = self.robot_state.y + d * math.cos(rad)
            self.segments.append(
                Segment(self.robot_state.x, self.robot_state.y, nx, ny)
            )
            self.robot_state.x = nx
            self.robot_state.y = ny
        elif op == "ROTATE":
            self.robot_state.heading = (self.robot_state.heading + float(parts[1])) % 360.0

    def drive_command(self, stmt: str) -> None:
        """Append a statement, compile via compile_source(), and update the canvas if valid."""
        self._cancel_animation()
        prev_text = self.editor.get("1.0", tk.END).rstrip("\n")
        candidate = (prev_text + "\n" + stmt + "\n") if prev_text.strip() else (stmt + "\n")

        result = self._compile_source_to_tabs(candidate)
        if result is None:
            bad = compile_source(candidate, optimize=True, arena=self.arena)
            msg = "\n".join(d.format(candidate.splitlines()) for d in bad.errors)
            messagebox.showwarning("Blocked by Compiler", msg, parent=self.root)
            return

        self.editor.delete("1.0", tk.END)
        self.editor.insert("1.0", candidate)
        self.editor.see(tk.END)

        sim = simulate_commands(result.commands)
        self.segments = sim.segments
        self.robot_state = sim.final_state
        self.pending_commands = []
        self.compiled_source = None
        self.step_index = 0
        self._redraw_canvas()
        self._update_hud(f"Executed: {stmt}")

    def _to_canvas(self, x: float, y: float) -> tuple[float, float]:
        w = max(200, self.canvas.winfo_width())
        h = max(200, self.canvas.winfo_height())
        size = min(w, h)
        arena_w = self.arena.max_x - self.arena.min_x
        arena_h = self.arena.max_y - self.arena.min_y
        pad = 30.0
        scale = (size - 2 * pad) / max(arena_w, arena_h)
        cx = w / 2.0 + (x - (self.arena.min_x + self.arena.max_x) / 2.0) * scale
        cy = h / 2.0 - (y - (self.arena.min_y + self.arena.max_y) / 2.0) * scale
        return cx, cy

    def _redraw_canvas(self) -> None:
        self.canvas.delete("all")

        gx = int(self.arena.min_x)
        while gx <= int(self.arena.max_x):
            x1, y1 = self._to_canvas(gx, self.arena.min_y)
            x2, y2 = self._to_canvas(gx, self.arena.max_y)
            self.canvas.create_line(x1, y1, x2, y2, fill="#cbd5e1" if gx == 0 else "#f1f5f9")
            gx += 10

        gy = int(self.arena.min_y)
        while gy <= int(self.arena.max_y):
            x1, y1 = self._to_canvas(self.arena.min_x, gy)
            x2, y2 = self._to_canvas(self.arena.max_x, gy)
            self.canvas.create_line(x1, y1, x2, y2, fill="#cbd5e1" if gy == 0 else "#f1f5f9")
            gy += 10

        ax1, ay1 = self._to_canvas(self.arena.min_x, self.arena.max_y)
        ax2, ay2 = self._to_canvas(self.arena.max_x, self.arena.min_y)
        self.canvas.create_rectangle(ax1, ay1, ax2, ay2, outline="#dc2626", width=2, dash=(6, 4))

        sx, sy = self._to_canvas(0.0, 0.0)
        self.canvas.create_oval(sx - 4, sy - 4, sx + 4, sy + 4, fill="#16a34a", outline="")

        for seg in self.segments:
            p1x, p1y = self._to_canvas(seg.x1, seg.y1)
            p2x, p2y = self._to_canvas(seg.x2, seg.y2)
            self.canvas.create_line(p1x, p1y, p2x, p2y, fill="#2563eb", width=2.5)

        rx, ry = self._to_canvas(self.robot_state.x, self.robot_state.y)
        rad = math.radians(self.robot_state.heading)
        nose = (rx + 12 * math.sin(rad), ry - 12 * math.cos(rad))
        left_wing = (rx + 8 * math.sin(rad - 2.4), ry - 8 * math.cos(rad - 2.4))
        right_wing = (rx + 8 * math.sin(rad + 2.4), ry - 8 * math.cos(rad + 2.4))
        self.canvas.create_polygon(
            nose[0],
            nose[1],
            left_wing[0],
            left_wing[1],
            right_wing[0],
            right_wing[1],
            fill="#ea580c",
            outline="#1e293b",
            width=1.5,
        )

    def _update_hud(self, status: str) -> None:
        st = self.robot_state
        fx = 0.0 if abs(st.x) < 1e-9 else st.x
        fy = 0.0 if abs(st.y) < 1e-9 else st.y
        fh = 0.0 if abs(st.heading) < 1e-9 else st.heading
        self.hud_var.set(f"Pose: ({fx:.2f}, {fy:.2f}) | Heading: {fh:.1f}° | {status}")


def launch_playground(initial_file: str | Path | None = None, arena: ArenaConfig | None = None) -> int:
    """Launch the interactive Tkinter playground window."""
    initial_source: str | None = None
    if initial_file is not None:
        path = Path(initial_file)
        if path.is_file():
            initial_source = path.read_text(encoding="utf-8")

    root = tk.Tk()
    RobotPlaygroundApp(root, initial_source=initial_source, arena=arena)
    root.mainloop()
    return 0

