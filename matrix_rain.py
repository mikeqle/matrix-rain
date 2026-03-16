#!/usr/bin/env python3
"""
Matrix Digital Rain — Terminal Effect

Usage:
    python matrix_rain.py                    # interactive menu
    python matrix_rain.py --preset classic   # quick start with a preset
    python matrix_rain.py --speed 1.2 --density 0.8 --color cyan

Press 'q' or ESC to quit while running.
"""

import argparse
import curses
import random
import sys
import time

# ── Character Set ────────────────────────────────────────────────────────────
# Half-width Katakana (U+FF66 – U+FF9D) + digits + latin + symbols
KATAKANA = [chr(c) for c in range(0xFF66, 0xFF9E)]
DIGITS = [chr(c) for c in range(0x30, 0x3A)]
LATIN = [chr(c) for c in range(0x41, 0x5B)]
SYMBOLS = list(":<>|{}[]()=*+-/\\!@#$%^&~")
CHARSET = KATAKANA + DIGITS + LATIN + SYMBOLS

# ── Color Definitions ────────────────────────────────────────────────────────
COLOR_NAMES = ["green", "red", "blue", "cyan", "yellow", "magenta", "white"]
RAINBOW_SEQUENCE = ["red", "yellow", "green", "cyan", "blue", "magenta"]

PRESETS = {
    "classic": {"speed": 1.0, "density": 0.7, "color": "green", "rainbow": False, "fps": 24, "trail_min": 0.25, "trail_max": 1.0},
    "dense":   {"speed": 1.2, "density": 1.5, "color": "green", "rainbow": False, "fps": 30, "trail_min": 0.3,  "trail_max": 1.0},
    "slow":    {"speed": 0.4, "density": 0.4, "color": "green", "rainbow": False, "fps": 20, "trail_min": 0.4,  "trail_max": 1.2},
    "rainbow": {"speed": 1.0, "density": 0.8, "color": "green", "rainbow": True,  "fps": 24, "trail_min": 0.25, "trail_max": 1.0},
    "storm":   {"speed": 2.0, "density": 2.0, "color": "green", "rainbow": False, "fps": 30, "trail_min": 0.15, "trail_max": 0.7},
}


# ── Stream ───────────────────────────────────────────────────────────────────
class Stream:
    """A single falling column of characters."""

    __slots__ = ("col", "head", "speed", "trail_length", "chars", "max_row",
                 "tick_acc", "mutate_chance")

    def __init__(self, col: int, max_row: int, speed: float, trail_length: int):
        self.col = col
        self.head = random.randint(-max_row, -1)
        self.speed = speed
        self.trail_length = trail_length
        self.chars: dict[int, str] = {}
        self.max_row = max_row
        self.tick_acc = 0.0
        self.mutate_chance = 0.04

    def update(self):
        self.tick_acc += self.speed
        while self.tick_acc >= 1.0:
            self.tick_acc -= 1.0
            self.head += 1
            if 0 <= self.head < self.max_row:
                self.chars[self.head] = random.choice(CHARSET)
            # Trim tail
            cutoff = self.head - self.trail_length
            self.chars = {r: c for r, c in self.chars.items() if r > cutoff}
        # Random character mutations (like in the film)
        for r in self.chars:
            if random.random() < self.mutate_chance:
                self.chars[r] = random.choice(CHARSET)

    def is_dead(self) -> bool:
        return self.head - self.trail_length >= self.max_row


# ── Matrix Rain Engine ───────────────────────────────────────────────────────
class MatrixRain:
    def __init__(self, stdscr, config: dict):
        self.stdscr = stdscr
        self.config = config
        self.streams: list[Stream] = []
        self.color_pairs: dict[str, int] = {}
        self.frame_count = 0
        self._setup_curses()
        self._resize()

    # ── Curses Setup ─────────────────────────────────────────────────────────
    def _setup_curses(self):
        curses.curs_set(0)
        curses.start_color()
        curses.use_default_colors()

        color_map = {
            "green":   curses.COLOR_GREEN,
            "red":     curses.COLOR_RED,
            "blue":    curses.COLOR_BLUE,
            "cyan":    curses.COLOR_CYAN,
            "yellow":  curses.COLOR_YELLOW,
            "magenta": curses.COLOR_MAGENTA,
            "white":   curses.COLOR_WHITE,
        }
        for i, (name, color) in enumerate(color_map.items(), start=1):
            curses.init_pair(i, color, -1)
            self.color_pairs[name] = i

        self.stdscr.timeout(0)
        self.stdscr.nodelay(True)

    def _resize(self):
        self.rows, self.cols = self.stdscr.getmaxyx()
        for s in self.streams:
            s.max_row = self.rows
        self.streams = [s for s in self.streams if s.col < self.cols]

    # ── Stream Spawning ──────────────────────────────────────────────────────
    def _spawn_streams(self):
        density = self.config["density"]
        base_speed = self.config["speed"]
        spawn_chance = density * 0.018

        for col in range(self.cols):
            if random.random() >= spawn_chance:
                continue
            # Don't stack too many streams in one column near the top
            if any(s.col == col and s.head < self.rows // 4 for s in self.streams):
                continue

            speed = random.uniform(base_speed * 0.5, base_speed * 1.5)
            trail_min = max(3, int(self.rows * self.config["trail_min"]))
            trail_max = max(trail_min + 2, int(self.rows * self.config["trail_max"]))
            trail = random.randint(trail_min, trail_max)
            self.streams.append(Stream(col, self.rows, speed, trail))

    # ── Color Helpers ────────────────────────────────────────────────────────
    def _get_color_pair(self, col_idx: int) -> int:
        if self.config["rainbow"]:
            # Slowly cycle rainbow offset over time + vary by column
            offset = (self.frame_count // 12) + col_idx
            name = RAINBOW_SEQUENCE[offset % len(RAINBOW_SEQUENCE)]
        else:
            name = self.config["color"]
        return self.color_pairs.get(name, self.color_pairs["green"])

    def _attr_for_position(self, dist_from_head: int, trail_length: int,
                           color_pair: int) -> int:
        """Return the curses attribute for a character based on how far it is
        from the stream head. Produces the classic bright-head → fade-out look."""
        if dist_from_head == 0:
            # Head glyph: bright version of the chosen color
            return curses.color_pair(color_pair) | curses.A_BOLD
        frac = dist_from_head / max(1, trail_length)
        if frac < 0.2:
            return curses.color_pair(color_pair) | curses.A_BOLD
        elif frac < 0.55:
            return curses.color_pair(color_pair)
        else:
            return curses.color_pair(color_pair) | curses.A_DIM

    # ── Drawing ──────────────────────────────────────────────────────────────
    def _draw(self):
        self.stdscr.erase()
        max_col = self.cols - 1  # avoid writing to bottom-right corner

        for stream in self.streams:
            pair = self._get_color_pair(stream.col)
            for row, char in stream.chars.items():
                if 0 <= row < self.rows and 0 <= stream.col < max_col:
                    dist = stream.head - row
                    attr = self._attr_for_position(dist, stream.trail_length, pair)
                    try:
                        self.stdscr.addstr(row, stream.col, char, attr)
                    except curses.error:
                        pass

        self.stdscr.refresh()

    # ── Main Loop ────────────────────────────────────────────────────────────
    def run(self):
        frame_delay = 1.0 / self.config["fps"]

        try:
            self._loop(frame_delay)
        except KeyboardInterrupt:
            pass

    def _loop(self, frame_delay: float):
        while True:
            t0 = time.monotonic()

            # Input
            try:
                key = self.stdscr.getch()
                if key in (ord("q"), ord("Q"), 27):  # q / Q / ESC
                    break
                elif key == curses.KEY_RESIZE:
                    self._resize()
            except curses.error:
                pass

            # Update
            self._spawn_streams()
            for stream in self.streams:
                stream.update()
            self.streams = [s for s in self.streams if not s.is_dead()]
            self.frame_count += 1

            # Draw
            self._draw()

            # Frame pacing
            elapsed = time.monotonic() - t0
            remaining = frame_delay - elapsed
            if remaining > 0:
                time.sleep(remaining)


# ── Interactive Menu ─────────────────────────────────────────────────────────
def interactive_menu() -> dict:
    """Show a terminal menu and return a config dict."""

    def ask_float(prompt: str, default: float, lo: float, hi: float) -> float:
        while True:
            raw = input(f"  {prompt} [{default}]: ").strip()
            if not raw:
                return default
            try:
                val = float(raw)
                if lo <= val <= hi:
                    return val
                print(f"    Please enter a value between {lo} and {hi}.")
            except ValueError:
                print("    Invalid number.")

    def ask_choice(prompt: str, choices: list[str], default: str) -> str:
        while True:
            raw = input(f"  {prompt} ({'/'.join(choices)}) [{default}]: ").strip().lower()
            if not raw:
                return default
            if raw in choices:
                return raw
            print(f"    Choose one of: {', '.join(choices)}")

    def ask_bool(prompt: str, default: bool) -> bool:
        d = "y" if default else "n"
        while True:
            raw = input(f"  {prompt} (y/n) [{d}]: ").strip().lower()
            if not raw:
                return default
            if raw in ("y", "yes"):
                return True
            if raw in ("n", "no"):
                return False
            print("    Please enter y or n.")

    print()
    print("  ╔══════════════════════════════════════╗")
    print("  ║       MATRIX  DIGITAL  RAIN          ║")
    print("  ╚══════════════════════════════════════╝")
    print()

    # Preset or custom?
    preset_names = list(PRESETS.keys()) + ["custom"]
    choice = ask_choice("Preset", preset_names, "classic")

    if choice != "custom":
        config = dict(PRESETS[choice])
        print(f"\n  Using preset '{choice}'. Press Enter to accept defaults or type a new value.\n")
    else:
        config = dict(PRESETS["classic"])
        print()

    config["speed"] = ask_float("Speed (0.1 – 4.0)", config["speed"], 0.1, 4.0)
    config["density"] = ask_float("Density (0.1 – 3.0)", config["density"], 0.1, 3.0)
    config["fps"] = int(ask_float("FPS (10 – 60)", config["fps"], 10, 60))

    if not config.get("rainbow"):
        config["color"] = ask_choice("Color", COLOR_NAMES, config["color"])
    config["rainbow"] = ask_bool("Rainbow mode", config.get("rainbow", False))

    print()
    print("  Starting… press 'q' or ESC to quit.")
    print()
    time.sleep(0.8)
    return config


# ── CLI Argument Parsing ─────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Matrix Digital Rain — terminal effect",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
               "  %(prog)s                          # interactive menu\n"
               "  %(prog)s --preset classic          # quick start\n"
               "  %(prog)s --speed 1.5 --color cyan  # custom via flags\n"
               "  %(prog)s --rainbow                 # rainbow mode\n",
    )
    p.add_argument("--preset", choices=PRESETS.keys(), help="use a built-in preset")
    p.add_argument("--speed", type=float, default=None, help="fall speed (0.1 – 4.0, default 1.0)")
    p.add_argument("--density", type=float, default=None, help="stream density (0.1 – 3.0, default 0.7)")
    p.add_argument("--color", choices=COLOR_NAMES, default=None, help="text color (default green)")
    p.add_argument("--rainbow", action="store_true", default=None, help="enable rainbow mode")
    p.add_argument("--fps", type=int, default=None, help="frames per second (10 – 60, default 24)")
    p.add_argument("--trail-min", type=float, default=None, help="min trail length as fraction of screen height (default 0.25)")
    p.add_argument("--trail-max", type=float, default=None, help="max trail length as fraction of screen height (default 1.0)")
    p.add_argument("--interactive", "-i", action="store_true", help="force interactive menu")
    return p.parse_args()


def config_from_args(args: argparse.Namespace) -> dict | None:
    """Build a config dict from CLI args. Returns None if interactive mode
    should be used instead."""
    if args.interactive:
        return None

    # If no flags were given at all, fall back to interactive
    has_flags = any(v is not None for k, v in vars(args).items()
                    if k not in ("interactive",))
    if not has_flags:
        return None

    base = dict(PRESETS.get(args.preset, PRESETS["classic"]))

    if args.speed is not None:
        base["speed"] = max(0.1, min(4.0, args.speed))
    if args.density is not None:
        base["density"] = max(0.1, min(3.0, args.density))
    if args.color is not None:
        base["color"] = args.color
    if args.rainbow is not None:
        base["rainbow"] = args.rainbow
    if args.fps is not None:
        base["fps"] = max(10, min(60, args.fps))
    if args.trail_min is not None:
        base["trail_min"] = max(0.05, min(1.0, args.trail_min))
    if args.trail_max is not None:
        base["trail_max"] = max(0.1, min(2.0, args.trail_max))

    return base


# ── Entry Point ──────────────────────────────────────────────────────────────
def main(stdscr, config: dict):
    rain = MatrixRain(stdscr, config)
    rain.run()


def cli_entry():
    """Entry point for both `python matrix_rain.py` and the `matrix-rain` console script."""
    try:
        args = parse_args()
        config = config_from_args(args)

        if config is None:
            config = interactive_menu()

        curses.wrapper(lambda stdscr: main(stdscr, config))
    except KeyboardInterrupt:
        print()  # clean newline after ^C


if __name__ == "__main__":
    cli_entry()
