from __future__ import annotations

# limits
MAX_WIDTH = 64
MAX_HEIGHT = 64
MAX_DURATION = 16
MAX_META_DEPTH = 4
MAX_TEXT_LENGTH = 48
MAX_VOLUME = 4096
MAX_INPUT_FILE_SIZE = 65535

# variants
DIRECTION_TILINGS = {
    0, 2, 3
}

DIRECTION_REPRESENTATION_VARIANTS = {
    "r": "`right` / `r` (Facing right)",
    "u": "`up` / `u` (Facing up)",
    "l": "`left` / `l` (Facing left)",
    "d": "`down` / `d` (Facing down)",
}

DIRECTION_VARIANTS = {
    "right": 0,
    "r": 0,
    "up": 8,
    "u": 8,
    "left": 16,
    "l": 16,
    "down": 24,
    "d": 24,
}

SOFT_DIRECTION_VARIANTS = {
    "rightsoft": 0,
    "rs": 0,
    "upsoft": 8,
    "us": 8,
    "leftsoft": 16,
    "ls": 16,
    "downsoft": 24,
    "ds": 24,
}

SOFT_DIRECTION_REPRESENTATION_VARIANTS = {
    "rs": "`rightsoft` / `rs` (Facing right, doesn't error if invalid)",
    "us": "`upsoft` / `us` (Facing up, doesn't error if invalid)",
    "ls": "`leftsoft` / `ls` (Facing left, doesn't error if invalid)",
    "ds": "`downsoft` / `ds` (Facing down, doesn't error if invalid)",
}


ANIMATION_TILINGS = {
    2, 3, 4
}

ANIMATION_REPRESENTATION_VARIANTS = {
    "a0": "`a0` (Animation frame 0)",
    "a1": "`a1` (Animation frame 1)",
    "a2": "`a2` (Animation frame 2)",
    "a3": "`a3` (Animation frame 3)",
}

ANIMATION_VARIANTS = {
    "a0": 0,
    "a1": 1,
    "a2": 2,
    "a3": 3,
}

SOFT_ANIMATION_VARIANTS = {
    "a0s": 0,
    "a0soft": 0,
    "a1s": 1,
    "a1soft": 1,
    "a2s": 2,
    "a2soft": 2,
    "a3s": 3,
    "a3soft": 3,
}

SOFT_ANIMATION_REPRESENTATION_VARIANTS = {
    "a0s": "`a0s` (Animation frame 0, doesn't error if invalid)",
    "a1s": "`a1s` (Animation frame 1, doesn't error if invalid)",
    "a2s": "`a2s` (Animation frame 2, doesn't error if invalid)",
    "a3s": "`a3s` (Animation frame 3, doesn't error if invalid)",
}

SLEEP_TILINGS = {
    2
}

SLEEP_REPRESENTATION_VARIANTS = {
    "s": "`sleep` / `s`"
}

SLEEP_VARIANTS = {
    "sleep": -1,
    "s": -1,
}

SOFT_SLEEP_REPRESENTATION_VARIANTS = {
    "ss": "`sleepsoft` / `ss` (Doesn't error if invalid)"
}

SOFT_SLEEP_VARIANTS = {
    "sleepsoft": -1,
    "ss": -1,
}

AUTO_TILINGS = {
    1
}

AUTO_REPRESENTATION_VARIANTS = {
    "tr": "`tileright` / `tr` (Connects right)",
    "tu": "`tileup` / `tu` (Connects up)",
    "tl": "`tileleft` / `tl` (Connects left)",
    "td": "`tiledown` / `td` (Connects down)",
}

AUTO_VARIANTS = {
    "tr": 1,
    "tileright": 1,
    "tu": 2,
    "tileup": 2,
    "tl": 4,
    "tileleft": 4,
    "td": 8,
    "tiledown": 8,
}

SOFT_AUTO_REPRESENTATION_VARIANTS = {
    "trs": "`tilerightsoft` / `trs` (Connects right, doesn't error if invalid)",
    "tus": "`tileupsoft` / `tus` (Connects up, doesn't error if invalid)",
    "tls": "`tileleftsoft` / `tls` (Connects left, doesn't error if invalid)",
    "tds": "`tiledownsoft` / `tds` (Connects down, doesn't error if invalid)",
}

SOFT_AUTO_VARIANTS = {
    "trs": 1,
    "tilerightsoft": 1,
    "tus": 2,
    "tileupsoft": 2,
    "tls": 4,
    "tileleftsoft": 4,
    "tds": 8,
    "tiledownsoft": 8,
}

# colors
COLOR_NAMES: dict[str, tuple[int, int]] = {
    "maroon": (2, 1), # Not actually a word in the game
    "red":    (2, 2),
    "orange": (2, 3),
    "yellow": (2, 4),
    "lime":   (5, 3),
    "green":  (5, 2),
    "cyan":   (1, 4),
    "blue":   (1, 3),
    "purple": (3, 1),
    "pink":   (4, 1),
    "rosy":   (4, 2),
    "grey":   (0, 1),
    "gray":   (0, 1), # alias
    "black":  (0, 4),
    "silver": (0, 2),
    "white":  (0, 3),
    "brown":  (6, 1),
}

COLOR_REPRESENTATION_VARIANTS = {
    "red": ", ".join(f"`{color}`" for color in COLOR_NAMES) + " (Color names)"
}

INACTIVE_COLORS: dict[tuple[int, int], tuple[int, int]] = {
    (0, 0): (0, 4),
    (1, 0): (0, 4),
    (2, 0): (1, 1),
    (3, 0): (0, 4),
    (4, 0): (0, 4),
    (5, 0): (6, 3),
    (6, 0): (6, 3),
    (0, 1): (1, 1),
    (1, 1): (1, 0),
    (2, 1): (2, 0),
    (3, 1): (3, 0),
    (4, 1): (4, 0),
    (5, 1): (5, 0),
    (6, 1): (6, 0),
    (0, 2): (0, 1),
    (1, 2): (1, 1),
    (2, 2): (2, 1),
    (3, 2): (1, 1),
    (4, 2): (4, 1),
    (5, 2): (5, 1),
    (6, 2): (6, 1),
    (0, 3): (0, 1),
    (1, 3): (1, 2),
    (2, 3): (2, 2),
    (3, 3): (4, 3),
    (4, 3): (1, 0),
    (5, 3): (5, 1),
    (6, 3): (0, 4),
    (0, 4): (6, 4),
    (1, 4): (1, 2),
    (2, 4): (6, 1),
    (3, 4): (6, 0),
    (4, 4): (3, 2),
    (5, 4): (5, 2),
    (6, 4): (6, 4),
}

# other constants
DIRECTIONS = {
    0: "right",
    8: "up",
    16: "left",
    24: "down"
}
# While not all of these are nouns, their appearance is very noun-like
TEXT_TYPES = {
    0: "noun",
    1: "noun",
    2: "property",
    3: "noun",
    4: "noun",
    5: "letter",
    6: "noun",
    7: "noun",
}  
DEFAULT_SPRITE_SIZE = 24
PALETTE_PIXEL_SIZE = 48
SEARCH_RESULT_UNITS_PER_PAGE = 10 # roughtly half the number of lines
OTHER_LEVELS_CUTOFF = 5
DEFAULT_RENDER_ZIP_NAME = "render_0"

BABA_WORLD = "baba"
EXTENSIONS_WORLD = "baba-extensions"

MAXIMUM_GUILD_THRESHOLD = 66 # keep it safe
GAMEOVER_GUILD_THRESHOLD = 76 # if you reach 76 guilds, you're out of luck, verification is forced
