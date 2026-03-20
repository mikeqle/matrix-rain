import curses
import random
import time

from .constants import (
    BLOCK_FONT,
    CHARSET,
    FONT_GAP,
    FONT_H,
    FONT_W,
    RAINBOW_SEQUENCE,
    REVEAL_FAST_SECS,
    REVEAL_HOLD_SECS,
    REVEAL_MIN_SPEED,
    REVEAL_SLOW_SECS,
)
from .stream import Stream


class MatrixRain:
    def __init__(self, stdscr, config: dict, message_listener=None):
        self.stdscr = stdscr
        self.config = config
        self.message_listener = message_listener
        self.streams: list[Stream] = []
        self.color_pairs: dict[str, int] = {}
        self.frame_count = 0
        self._setup_curses()
        self._resize()

        # Text reveal state
        self.message = config.get("message", "")
        self.reveal_state = "idle"
        self.reveal_timer = 0.0
        self.reveal_mask: set[tuple[int, int]] = set()
        self.reveal_mask_order: list[tuple[int, int]] = []
        self.reveal_fill_chars: dict[tuple[int, int], str] = {}
        self.speed_multiplier = 1.0

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
        spawn_chance = density * 0.018 * self.speed_multiplier

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
            # Head glyph: white flash
            return curses.color_pair(self.color_pairs["white"]) | curses.A_BOLD
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
        mask = self._active_mask()
        fade = self._non_mask_fade()

        for stream in self.streams:
            pair = self._get_color_pair(stream.col)
            for row, char in stream.chars.items():
                if 0 <= row < self.rows and 0 <= stream.col < max_col:
                    in_mask = mask and (row, stream.col) in mask
                    if mask and not in_mask:
                        # Non-mask position: probabilistically suppress
                        if hash((row, stream.col)) % 1000 / 1000.0 >= fade:
                            continue
                    if in_mask:
                        # Consistent shade for text readability
                        attr = curses.color_pair(pair) | curses.A_BOLD
                    else:
                        dist = stream.head - row
                        attr = self._attr_for_position(dist, stream.trail_length, pair)
                    try:
                        self.stdscr.addstr(row, stream.col, char, attr)
                    except curses.error:
                        pass

        # Fill text mask positions that have no stream char
        if mask:
            self._draw_mask_fill(max_col, mask)

        self.stdscr.refresh()

    # ── Text Reveal ───────────────────────────────────────────────────────
    def _start_reveal(self):
        """Begin the slow-down → reveal → speed-up sequence."""
        self.reveal_state = "slowing"
        self.reveal_timer = 0.0
        self.reveal_mask = self._compute_text_mask(self.message)
        self.reveal_mask_order = list(self.reveal_mask)
        random.shuffle(self.reveal_mask_order)
        self.reveal_fill_chars = {pos: random.choice(CHARSET)
                                  for pos in self.reveal_mask}

    def _update_reveal(self, dt: float):
        """Advance the reveal state machine by *dt* seconds."""
        if self.reveal_state == "idle":
            return

        self.reveal_timer += dt

        if self.reveal_state == "slowing":
            progress = min(1.0, self.reveal_timer / REVEAL_SLOW_SECS)
            self.speed_multiplier = 1.0 - progress * (1.0 - REVEAL_MIN_SPEED)
            if progress >= 1.0:
                self.reveal_state = "hold"
                self.reveal_timer = 0.0

        elif self.reveal_state == "hold":
            self.speed_multiplier = REVEAL_MIN_SPEED
            if self.reveal_timer >= REVEAL_HOLD_SECS:
                self.reveal_state = "speedup"
                self.reveal_timer = 0.0

        elif self.reveal_state == "speedup":
            progress = min(1.0, self.reveal_timer / REVEAL_FAST_SECS)
            self.speed_multiplier = REVEAL_MIN_SPEED + progress * (1.0 - REVEAL_MIN_SPEED)
            if progress >= 1.0:
                self.reveal_state = "idle"
                self.reveal_mask = set()
                self.reveal_mask_order = []
                self.reveal_fill_chars = {}
                self.speed_multiplier = 1.0

        # Mutate fill characters for rain-like flicker in the text
        for pos in self.reveal_fill_chars:
            if random.random() < 0.04:
                self.reveal_fill_chars[pos] = random.choice(CHARSET)

    def _active_mask(self) -> set[tuple[int, int]]:
        """Return the set of (row, col) positions to suppress for text reveal."""
        if self.reveal_state == "idle" or not self.reveal_mask_order:
            return set()

        if self.reveal_state == "hold":
            return self.reveal_mask

        if self.reveal_state == "slowing":
            # Fade in: no mask for first 30%, then grow over remaining 70%
            progress = self.reveal_timer / REVEAL_SLOW_SECS
            if progress < 0.3:
                return set()
            fade = (progress - 0.3) / 0.7
            count = int(len(self.reveal_mask_order) * fade)
            return set(self.reveal_mask_order[:count])

        if self.reveal_state == "speedup":
            # Fade out: shrink mask over first 50%, then gone
            progress = self.reveal_timer / REVEAL_FAST_SECS
            if progress > 0.5:
                return set()
            fade = 1.0 - progress / 0.5
            count = int(len(self.reveal_mask_order) * fade)
            return set(self.reveal_mask_order[:count])

        return set()

    def _compute_text_mask(self, message: str) -> set[tuple[int, int]]:
        """Build a set of (row, col) positions for the block-font rendering
        of *message*, centred on the screen."""
        message = message.upper()
        total_w = len(message) * (FONT_W + FONT_GAP) - FONT_GAP
        start_col = max(0, (self.cols - total_w) // 2)
        start_row = max(0, (self.rows - FONT_H) // 2)

        mask: set[tuple[int, int]] = set()
        col = start_col
        for ch in message:
            glyph = BLOCK_FONT.get(ch, BLOCK_FONT.get(' '))
            if glyph:
                for r, row_str in enumerate(glyph):
                    for c, pixel in enumerate(row_str):
                        if pixel != ' ':
                            pr, pc = start_row + r, col + c
                            if 0 <= pr < self.rows and 0 <= pc < self.cols:
                                mask.add((pr, pc))
            col += FONT_W + FONT_GAP
        return mask

    def _non_mask_fade(self) -> float:
        """Return opacity (0.0–1.0) for rain outside the text mask."""
        if self.reveal_state == "idle":
            return 1.0
        if self.reveal_state == "hold":
            return 0.0
        if self.reveal_state == "slowing":
            progress = self.reveal_timer / REVEAL_SLOW_SECS
            return max(0.0, 1.0 - progress / 0.7)
        if self.reveal_state == "speedup":
            progress = self.reveal_timer / REVEAL_FAST_SECS
            return min(1.0, progress / 0.7)
        return 1.0

    def _draw_mask_fill(self, max_col: int, mask: set[tuple[int, int]]):
        """Draw rain characters at mask positions not covered by any stream,
        ensuring the text shape is always fully visible."""
        covered = set()
        for stream in self.streams:
            for row in stream.chars:
                pos = (row, stream.col)
                if pos in mask:
                    covered.add(pos)

        pair = self._get_color_pair(self.cols // 2)
        attr = curses.color_pair(pair) | curses.A_BOLD
        for pos in mask - covered:
            if 0 <= pos[1] < max_col:
                char = self.reveal_fill_chars.get(pos)
                if char:
                    try:
                        self.stdscr.addstr(pos[0], pos[1], char, attr)
                    except curses.error:
                        pass

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

            # IPC input (non-blocking)
            if self.message_listener:
                incoming = self.message_listener.poll()
                if incoming is not None:
                    self.message = incoming
                    self.reveal_state = "idle"
                    self.reveal_mask = set()
                    self.reveal_mask_order = []
                    self.reveal_fill_chars = {}
                    self.speed_multiplier = 1.0
                    self._start_reveal()

            # Input
            try:
                key = self.stdscr.getch()
                if key in (ord("q"), ord("Q"), 27):  # q / Q / ESC
                    break
                elif key == curses.KEY_RESIZE:
                    self._resize()
                    if self.reveal_state != "idle":
                        # Abort reveal on resize — mask positions are stale
                        self.reveal_state = "idle"
                        self.reveal_mask = set()
                        self.reveal_mask_order = []
                        self.reveal_fill_chars = {}
                        self.speed_multiplier = 1.0
                elif key in (ord("t"), ord("T")):
                    if self.reveal_state == "idle" and self.message:
                        self._start_reveal()
                    elif self.reveal_state in ("slowing", "hold"):
                        self.reveal_state = "speedup"
                        self.reveal_timer = 0.0
                    elif self.reveal_state == "speedup":
                        self.reveal_state = "idle"
                        self.reveal_mask = set()
                        self.reveal_mask_order = []
                        self.reveal_fill_chars = {}
                        self.speed_multiplier = 1.0
            except curses.error:
                pass

            # Reveal animation
            self._update_reveal(frame_delay)

            # Update
            self._spawn_streams()
            for stream in self.streams:
                stream.update(self.speed_multiplier)
            self.streams = [s for s in self.streams if not s.is_dead()]
            self.frame_count += 1

            # Draw
            self._draw()

            # Frame pacing
            elapsed = time.monotonic() - t0
            remaining = frame_delay - elapsed
            if remaining > 0:
                time.sleep(remaining)
