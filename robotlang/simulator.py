"""Virtual robot VM, execution trace recorder, and matplotlib trajectory visualizer."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from robotlang.codegen import generate_commands
from robotlang.ir import IRInstr
from robotlang.semantic import ArenaConfig


@dataclass
class RobotState:
    x: float = 0.0
    y: float = 0.0
    heading: float = 0.0  # degrees clockwise from north (0 = +y, 90 = +x)


@dataclass(frozen=True)
class Segment:
    x1: float
    y1: float
    x2: float
    y2: float


@dataclass(frozen=True)
class TraceStep:
    step: int
    command: str
    x: float
    y: float
    heading: float


@dataclass
class SimulationResult:
    final_state: RobotState
    segments: list[Segment]
    trace: list[TraceStep]

    def format_trace(self) -> str:
        lines = [
            f"{'Step':>4} | {'Command':<16} | {'Position (x, y)':<20} | {'Heading':>7}",
            "-" * 58,
        ]
        for t in self.trace:
            pos_str = f"({t.x:>7.2f}, {t.y:>7.2f})"
            lines.append(
                f"{t.step:>4} | {t.command:<16} | {pos_str:<20} | {t.heading:>6.1f}°"
            )
        return "\n".join(lines)


def simulate_commands(commands: list[str] | str) -> SimulationResult:
    """Execute low-level robot commands in the virtual robot simulator."""
    if isinstance(commands, str):
        cmd_list = [line.strip() for line in commands.splitlines() if line.strip()]
    else:
        cmd_list = [cmd.strip() for cmd in commands if cmd.strip()]

    state = RobotState()
    segments: list[Segment] = []
    trace: list[TraceStep] = []

    for idx, cmd in enumerate(cmd_list, start=1):
        parts = cmd.split()
        op = parts[0].upper()

        if op == "MOVE" and len(parts) == 2:
            d = float(parts[1])
            rad = math.radians(state.heading)
            nx = state.x + d * math.sin(rad)
            ny = state.y + d * math.cos(rad)
            segments.append(Segment(state.x, state.y, nx, ny))
            state.x = nx
            state.y = ny
        elif op == "ROTATE" and len(parts) == 2:
            deg = float(parts[1])
            state.heading = (state.heading + deg) % 360.0
        else:
            raise ValueError(f"Invalid robot command: {cmd!r}")

        trace.append(
            TraceStep(
                step=idx,
                command=cmd,
                x=0.0 if abs(state.x) < 1e-12 else state.x,
                y=0.0 if abs(state.y) < 1e-12 else state.y,
                heading=0.0 if abs(state.heading) < 1e-12 else state.heading,
            )
        )

    if abs(state.x) < 1e-12:
        state.x = 0.0
    if abs(state.y) < 1e-12:
        state.y = 0.0
    if abs(state.heading) < 1e-12:
        state.heading = 0.0

    return SimulationResult(final_state=state, segments=segments, trace=trace)


def simulate_ir(instructions: list[IRInstr]) -> SimulationResult:
    """Lower IR to robot commands and execute them in the simulator."""
    return simulate_commands(generate_commands(instructions))


def render_matplotlib(
    sim: SimulationResult,
    arena: ArenaConfig | None = None,
    output_path: str | Path | None = None,
    show: bool = False,
    title: str = "RobotLang Trajectory",
) -> Path | None:
    """Render the arena boundary and robot trajectory using matplotlib."""
    import matplotlib

    if not show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    arena = arena or ArenaConfig()
    fig, ax = plt.subplots(figsize=(7, 7))

    # Draw arena boundary
    width = arena.max_x - arena.min_x
    height = arena.max_y - arena.min_y
    arena_rect = Rectangle(
        (arena.min_x, arena.min_y),
        width,
        height,
        fill=False,
        edgecolor="#dc2626",
        linewidth=1.8,
        linestyle="--",
        label="Arena boundary",
    )
    ax.add_patch(arena_rect)

    # Draw trajectory segments
    path_label_used = False
    for seg in sim.segments:
        ax.plot(
            [seg.x1, seg.x2],
            [seg.y1, seg.y2],
            color="#2563eb",
            linewidth=2.2,
            label="Robot path" if not path_label_used else None,
        )
        path_label_used = True

    # Start and end markers
    ax.scatter([0.0], [0.0], color="#16a34a", s=60, zorder=5, label="Start (0, 0)")
    fx, fy = sim.final_state.x, sim.final_state.y
    ax.scatter([fx], [fy], color="#ea580c", s=70, marker="D", zorder=6, label="End")

    # Heading arrow at final position
    arrow_len = max(width, height) * 0.04
    rad = math.radians(sim.final_state.heading)
    ax.annotate(
        "",
        xy=(fx + arrow_len * math.sin(rad), fy + arrow_len * math.cos(rad)),
        xytext=(fx, fy),
        arrowprops={"arrowstyle": "->", "color": "#ea580c", "lw": 2.0},
    )

    margin = max(width, height) * 0.08
    ax.set_xlim(arena.min_x - margin, arena.max_x + margin)
    ax.set_ylim(arena.min_y - margin, arena.max_y + margin)
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, linestyle=":", alpha=0.5)
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.set_title(title)
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()

    saved: Path | None = None
    if output_path is not None:
        saved = Path(output_path)
        saved.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(saved, dpi=150)

    if show:
        plt.show()
    plt.close(fig)
    return saved
