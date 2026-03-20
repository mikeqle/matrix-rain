# Matrix Digital Rain — Agent Guide

Terminal-based Matrix digital rain effect in Python using curses. Zero external dependencies.

## Quick Reference

- **Language**: Python 3.12+
- **Package manager**: [uv](https://docs.astral.sh/uv/)
- **Build backend**: hatchling
- **Runtime deps**: none (stdlib only: curses, argparse, subprocess, random, time, socket)
- **Dev deps**: pytest
- **Entry point**: `matrix_rain:cli_entry` (console script `matrix-rain`)

## Commands

```bash
# Run
python -m matrix_rain                         # interactive menu
python -m matrix_rain --preset classic        # CLI flags
uv run matrix-rain                            # via uv

# Test
uv run pytest test_matrix_rain.py -v

# Install
pip install -e .                              # editable
```

## Project Structure

```
matrix_rain/
├── __init__.py      # Public API, re-exports, backwards-compat aliases
├── __main__.py      # `python -m` entry point → calls cli_entry()
├── cli.py           # argparse CLI, config_from_args(), caffeinate subprocess
├── constants.py     # CHARSET, COLOR_NAMES, PRESETS, BLOCK_FONT, reveal timing
├── engine.py        # MatrixRain class — curses rendering, text reveal state machine
├── ipc.py           # MessageListener (Unix datagram socket), send_message()
├── menu.py          # interactive_menu() — terminal UI for config
└── stream.py        # Stream class — single falling column of characters
test_matrix_rain.py  # ~840 lines, pytest, mocked curses
pyproject.toml       # Package metadata
```

## Architecture

### Data Flow

`cli_entry()` → parse args (or `--send` one-shot client) or `interactive_menu()` → build config dict → create `MessageListener` → `curses.wrapper(main)` → `MatrixRain(stdscr, config, listener).run()`

### Config Dict Keys

`speed`, `density`, `color`, `rainbow`, `fps`, `trail_min`, `trail_max`, `message` (optional)

### Core Classes

- **`MatrixRain`** (`engine.py`): Main loop, curses rendering, stream management, text reveal state machine (states: `idle` → `slowing` → `hold` → `speedup` → `idle`). Accepts optional `message_listener` for IPC.
- **`Stream`** (`stream.py`): Single falling column. Uses `__slots__`, tick accumulator for sub-frame movement, character mutation for flickering.
- **`MessageListener`** (`ipc.py`): Non-blocking Unix datagram socket. `poll()` called each frame in `_loop()` — returns message or `None`. No threading needed.

### Text Reveal System

Press `t` to trigger a multi-phase animation that reveals a `--message` in 5x5 block-font negative space:
1. **slowing** — rain decelerates over 0.6s, mask fades in after 30% progress
2. **hold** — rain nearly stopped, full mask visible for 10s
3. **speedup** — mask fades out, rain returns to normal over 0.6s

Press `t` again during slowing/hold to skip to speedup, or during speedup to immediately return to idle.

### IPC (External Message Input)

Unix datagram socket at `/tmp/matrix-rain-{uid}.sock`. The engine polls non-blocking `recvfrom()` once per frame in `_loop()`. New message during active reveal: interrupt and restart.

- **Sender**: `matrix-rain --send "TEXT"` (one-shot client via `send_message()`)
- **Listener**: `MessageListener` created in `cli_entry()`, passed to engine, cleaned up in `finally`
- **Override path**: `--socket-path`, **disable**: `--no-ipc`
- Stale socket detection: probe + unlink on bind failure

### Key Design Decisions

- Half-width Katakana (U+FF66–FF9D) for authentic Matrix look
- White flash at stream head, bold→normal→dim gradient down trail
- `caffeinate -d` subprocess on macOS to prevent display sleep
- Reveal aborts on terminal resize (mask positions become stale)
- `__init__.py` provides underscore-prefixed aliases (`_FONT_H` etc.) for backwards compatibility with tests

## Testing

Tests use `unittest.mock` to mock curses. Key fixture pattern:

```python
mock_stdscr = MagicMock()
mock_stdscr.getmaxyx.return_value = (rows, cols)
```

Test categories: character sets, presets, Stream class, config_from_args, CLI parsing, MatrixRain engine, caffeinate integration, block font, text reveal state machine, IPC (socket listener, send/receive, stale cleanup, engine integration).

IPC tests use a `sock_path` fixture with short `/tmp` paths to stay within the AF_UNIX 104-byte path limit on macOS.

## CLI Flags

`--preset` (classic/dense/slow/rainbow/storm), `--speed` (0.1–4.0), `--density` (0.1–3.0), `--color` (green/red/blue/cyan/yellow/magenta/white), `--rainbow`, `--fps` (10–60), `--trail-min` (0.05–1.0), `--trail-max` (0.1–2.0), `--message` (str), `--send` (str), `--socket-path` (str), `--no-ipc`, `-i`/`--interactive`

## Runtime Controls

- `q` / `Q` / `ESC` — quit
- `t` / `T` — trigger/dismiss text reveal (requires `--message`)
