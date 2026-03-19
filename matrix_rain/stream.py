import random

from .constants import CHARSET


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

    def update(self, speed_scale: float = 1.0):
        self.tick_acc += self.speed * speed_scale
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
