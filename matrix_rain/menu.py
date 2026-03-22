import time

from .constants import COLOR_NAMES, PRESETS


def interactive_menu(defaults: dict | None = None) -> dict:
    """Show a terminal menu and return a config dict.

    *defaults* seeds the prompt defaults.  When ``None``, the classic
    preset is used."""

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

    # Seed from caller-supplied defaults (e.g. saved config) or classic.
    if defaults is None:
        defaults = dict(PRESETS["classic"])

    # Preset or custom?
    preset_names = list(PRESETS.keys()) + ["custom"]
    default_preset = defaults.get("preset", "classic")
    if default_preset not in preset_names:
        default_preset = "classic"
    choice = ask_choice("Preset", preset_names, default_preset)

    if choice != "custom":
        if choice == default_preset:
            # User accepted the saved preset — keep saved overrides.
            config = dict(defaults)
        else:
            # User switched to a different preset — re-base, but carry
            # over non-preset keys from defaults (e.g. message).
            config = dict(defaults)
            config.update(PRESETS[choice])
        print(f"\n  Using preset '{choice}'. Press Enter to accept defaults or type a new value.\n")
    else:
        config = dict(defaults)
        print()

    config["speed"] = ask_float("Speed (0.1 – 4.0)", config.get("speed", 1.0), 0.1, 4.0)
    config["density"] = ask_float("Density (0.1 – 3.0)", config.get("density", 0.7), 0.1, 3.0)
    config["fps"] = int(ask_float("FPS (10 – 60)", config.get("fps", 24), 10, 60))

    if not config.get("rainbow"):
        config["color"] = ask_choice("Color", COLOR_NAMES, config.get("color", "green"))
    config["rainbow"] = ask_bool("Rainbow mode", config.get("rainbow", False))

    default_msg = config.get("message", "")
    msg_prompt = f"  Reveal message (press 't' to show) [{default_msg}]: " if default_msg else "  Reveal message (press 't' to show) []: "
    msg = input(msg_prompt).strip()
    if msg:
        config["message"] = msg
    elif default_msg and not msg:
        config["message"] = default_msg

    print()
    print("  Starting… press 'q' or ESC to quit.")
    if config.get("message"):
        print("  Press 't' to reveal your message.")
    print()
    time.sleep(0.8)
    return config
