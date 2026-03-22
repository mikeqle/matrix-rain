"""
Matrix Digital Rain — Terminal Effect

Usage:
    matrix-rain                              # run with saved config (or defaults)
    matrix-rain -i                           # interactive menu
    matrix-rain --preset classic             # quick start with a preset
    matrix-rain --speed 1.2 --density 0.8 --color cyan
    matrix-rain config --speed 2.0 --color red   # save config values
    matrix-rain config --show                # show current config
    matrix-rain config --reset               # reset to defaults

Press 'q' or ESC to quit while running.
Press 't' to trigger text reveal (requires --message).
"""

import argparse
import curses
import subprocess
import sys

from .config import (
    _clamp,
    config_path,
    format_config,
    load_config,
    reset_config,
    resolve_config,
    save_config,
)
from .constants import COLOR_NAMES, PRESETS
from .engine import MatrixRain
from .ipc import MessageListener, default_socket_path, send_message
from .menu import interactive_menu


def _add_display_flags(p: argparse.ArgumentParser) -> None:
    """Add the shared display/config flags to a parser."""
    p.add_argument("--preset", choices=PRESETS.keys(), default=None,
                   help="use a built-in preset")
    p.add_argument("--speed", type=float, default=None,
                   help="fall speed (0.1 – 4.0)")
    p.add_argument("--density", type=float, default=None,
                   help="stream density (0.1 – 3.0)")
    p.add_argument("--color", choices=COLOR_NAMES, default=None,
                   help="text color")
    p.add_argument("--rainbow", action=argparse.BooleanOptionalAction, default=None,
                   help="enable rainbow mode")
    p.add_argument("--fps", type=int, default=None,
                   help="frames per second (10 – 60)")
    p.add_argument("--trail-min", type=float, default=None,
                   help="min trail length as fraction of screen height")
    p.add_argument("--trail-max", type=float, default=None,
                   help="max trail length as fraction of screen height")
    p.add_argument("--message", type=str, default=None,
                   help="text to reveal when 't' is pressed")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Matrix Digital Rain — terminal effect",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
               "  %(prog)s                              # run with saved config\n"
               "  %(prog)s -i                            # interactive menu\n"
               "  %(prog)s --preset classic               # quick start\n"
               "  %(prog)s --speed 1.5 --color cyan       # custom via flags\n"
               "  %(prog)s config --speed 2.0 --color red # save to config\n"
               "  %(prog)s config --show                  # view config\n"
               "  %(prog)s config --reset                 # reset config\n",
    )

    sub = p.add_subparsers(dest="command")

    # ── config subcommand ──
    config_parser = sub.add_parser(
        "config",
        help="view or set persistent configuration",
        description="View or set persistent configuration values.",
    )
    _add_display_flags(config_parser)
    config_parser.add_argument("--show", action="store_true",
                               help="show current configuration")
    config_parser.add_argument("--reset", action="store_true",
                               help="reset configuration to defaults")

    # ── main (run) flags ──
    _add_display_flags(p)
    p.add_argument("--interactive", "-i", action="store_true",
                   help="force interactive menu")
    p.add_argument("--send", type=str, default=None, metavar="TEXT",
                   help="send a message to a running matrix-rain instance and exit")
    p.add_argument("--socket-path", type=str, default=None,
                   help=f"override IPC socket path (default: {default_socket_path()})")
    p.add_argument("--no-ipc", action="store_true",
                   help="disable the IPC listener")

    return p.parse_args(argv)


def _collect_display_overrides(args: argparse.Namespace) -> dict:
    """Extract non-None display flags from parsed args into a dict."""
    keys = ("preset", "speed", "density", "color", "rainbow",
            "fps", "trail_min", "trail_max", "message")
    return {k: getattr(args, k) for k in keys if getattr(args, k, None) is not None}


def handle_config_command(args: argparse.Namespace) -> None:
    """Handle the 'config' subcommand."""
    if args.reset:
        reset_config()
        print("Configuration reset to defaults.")
        return

    overrides = _collect_display_overrides(args)

    if overrides:
        clamped = _clamp(overrides)
        saved = save_config(clamped)
        print("Configuration saved.")
        print()
        print(format_config(saved))
    else:
        # No flags (or --show): display current config.
        print(format_config())
        print()
        print(f"Config file: {config_path()}")


def config_from_args(args: argparse.Namespace) -> dict | None:
    """Build a config dict from CLI args.  Returns None if interactive mode
    should be used instead."""
    if args.interactive:
        return None

    # Collect CLI display overrides.
    ipc_only = ("interactive", "no_ipc", "send", "socket_path", "command")
    has_display_flags = any(v is not None for k, v in vars(args).items()
                           if k not in ipc_only)

    # Start from saved config merged with defaults.
    base = resolve_config()

    if has_display_flags:
        # If a preset is explicitly given, layer its values onto the
        # resolved base so non-preset saved settings (e.g. message,
        # custom trail limits) are preserved.
        if args.preset is not None:
            base.update(PRESETS[args.preset])

        # Layer CLI flags on top.
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

        # ── config subcommand ──
        if args.command == "config":
            handle_config_command(args)
            return

        # ── --send mode ──
        if args.send is not None:
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
            config = interactive_menu(defaults=resolve_config())

        # Keep the machine awake while the rain is running (macOS).
        caffeinate = None
        listener = None
        try:
            try:
                caffeinate = subprocess.Popen(
                    ["caffeinate", "-d"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except FileNotFoundError:
                pass  # not on macOS — skip silently

            # IPC listener
            if not args.no_ipc:
                try:
                    listener = MessageListener(args.socket_path)
                except OSError as e:
                    if args.socket_path is not None:
                        print(f"Error: cannot bind to {args.socket_path}: {e}",
                              file=sys.stderr)
                        sys.exit(1)
                    print(f"Warning: IPC disabled ({e})", file=sys.stderr)

            curses.wrapper(lambda stdscr: main(stdscr, config, listener))
        finally:
            if listener is not None:
                listener.close()
            if caffeinate is not None:
                caffeinate.terminate()
                caffeinate.wait()
    except KeyboardInterrupt:
        print()  # clean newline after ^C
