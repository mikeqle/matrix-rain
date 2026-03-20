"""
Matrix Digital Rain — Terminal Effect

Usage:
    python -m matrix_rain                    # interactive menu
    python -m matrix_rain --preset classic   # quick start with a preset
    python -m matrix_rain --speed 1.2 --density 0.8 --color cyan
    python -m matrix_rain --message "WAKE UP"  # set reveal message

Press 'q' or ESC to quit while running.
Press 't' to trigger text reveal (requires --message).
"""

import argparse
import curses
import subprocess
import sys

from .constants import COLOR_NAMES, PRESETS
from .engine import MatrixRain
from .ipc import MessageListener, default_socket_path, send_message
from .menu import interactive_menu


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
    p.add_argument("--message", type=str, default=None, help="text to reveal when 't' is pressed (block-font negative space)")
    p.add_argument("--interactive", "-i", action="store_true", help="force interactive menu")
    p.add_argument("--send", type=str, default=None, metavar="TEXT",
                   help="send a message to a running matrix-rain instance and exit")
    p.add_argument("--socket-path", type=str, default=None,
                   help=f"override IPC socket path (default: {default_socket_path()})")
    p.add_argument("--no-ipc", action="store_true",
                   help="disable the IPC listener")
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
    if args.message is not None:
        base["message"] = args.message

    return base


def main(stdscr, config: dict, message_listener=None):
    rain = MatrixRain(stdscr, config, message_listener)
    rain.run()


def cli_entry():
    """Entry point for both `python -m matrix_rain` and the `matrix-rain` console script."""
    try:
        args = parse_args()

        # --send mode: send a message to a running instance and exit
        if args.send:
            path = args.socket_path or default_socket_path()
            try:
                send_message(args.send, path)
            except (FileNotFoundError, ConnectionRefusedError, OSError) as e:
                print(f"Error: could not reach matrix-rain at {path}: {e}",
                      file=sys.stderr)
                sys.exit(1)
            return

        config = config_from_args(args)

        if config is None:
            config = interactive_menu()

        # Keep the machine awake while the rain is running (macOS).
        caffeinate = None
        try:
            caffeinate = subprocess.Popen(
                ["caffeinate", "-d"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            pass  # not on macOS — skip silently

        # IPC listener
        listener = None
        if not args.no_ipc:
            try:
                listener = MessageListener(args.socket_path)
            except OSError as e:
                print(f"Warning: IPC disabled ({e})", file=sys.stderr)

        try:
            curses.wrapper(lambda stdscr: main(stdscr, config, listener))
        finally:
            if listener is not None:
                listener.close()
            if caffeinate is not None:
                caffeinate.terminate()
                caffeinate.wait()
    except KeyboardInterrupt:
        print()  # clean newline after ^C
