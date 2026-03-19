import time

from .constants import COLOR_NAMES, PRESETS


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

    msg = input("  Reveal message (press 't' to show) []: ").strip()
    if msg:
        config["message"] = msg

    print()
    print("  Starting… press 'q' or ESC to quit.")
    if config.get("message"):
        print("  Press 't' to reveal your message.")
    print()
    time.sleep(0.8)
    return config
