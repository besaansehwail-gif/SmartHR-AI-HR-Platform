"""Create the reusable celebration graphic the Social Hub post carries.

    venv\\Scripts\\python.exe -m scripts.seed_celebration_image
    venv\\Scripts\\python.exe -m scripts.seed_celebration_image --dry-run

**Why a graphic and not a photograph of the employee.** SmartHR has no
employee photograph anywhere: `employees` has no image column, and the only
avatar in the system lives on `social_profiles`, which is keyed on a *user
account* - and 11 of the 12 employee rows have no account at all, with zero
avatars stored. A celebration post therefore either carries the person's own
avatar, when they happen to have uploaded one, or a piece of decoration. It
never carries an invented face: a stock photograph beside a real colleague's
name is a fabricated identity, which is the thing this feature must not do.

So this writes an **abstract** banner - a warm gradient in the Amber Sand
palette with confetti - through `social_storage.store_image()`, the same
function an uploaded photo goes through. It gets an ordinary stored name, it
is served by the ordinary `GET /social/media/{name}` route behind
`require_staff`, and nothing about it is special-cased.

No new dependency: Pillow is not installed and was not added, so the PNG is
encoded here with `zlib` and `struct` from the standard library. It is
decoration, not a photograph, so a hand-rolled encoder is enough.

The stored name is printed at the end. Put it in `.env`:

    SMARTHR_CELEBRATION_IMAGE=<the name printed>

With that unset, or pointing at a file that is not there, celebrations simply
carry no image - `celebration_image()` returns None and the post is text, as
it was before. Nothing breaks.
"""

import argparse
import math
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import social_storage  # noqa: E402

WIDTH = 1200
HEIGHT = 480

#: The Amber Sand palette, so the banner belongs to SmartHR rather than
#: looking like a stock asset somebody pasted in.
SAND_TOP = (255, 247, 237)
SAND_BOTTOM = (254, 233, 209)
BRAND = (194, 91, 32)
BRAND_LIGHT = (234, 141, 74)
GOLD = (233, 179, 74)
ROSE = (214, 116, 105)
TEAL = (108, 160, 148)


def _blend(bottom: tuple, top: tuple, alpha: float) -> tuple:
    return tuple(
        int(round(bottom[index] * (1 - alpha) + top[index] * alpha))
        for index in range(3)
    )


def _canvas() -> list[list[tuple]]:
    """A vertical gradient, top to bottom."""
    rows = []
    for y in range(HEIGHT):
        ratio = y / (HEIGHT - 1)
        colour = _blend(SAND_TOP, SAND_BOTTOM, ratio)
        rows.append([colour] * WIDTH)
    return rows


def _disc(rows, cx: float, cy: float, radius: float, colour: tuple,
          alpha: float = 1.0) -> None:
    """One soft-edged circle. Confetti, and the ribbon's dots."""
    left, right = max(0, int(cx - radius) - 1), min(WIDTH, int(cx + radius) + 2)
    top, bottom = max(0, int(cy - radius) - 1), min(HEIGHT, int(cy + radius) + 2)

    for y in range(top, bottom):
        for x in range(left, right):
            distance = math.hypot(x - cx, y - cy)
            if distance > radius + 1:
                continue
            # One pixel of feathering, so the edges are not stair-stepped.
            edge = min(1.0, max(0.0, radius + 0.5 - distance))
            rows[y][x] = _blend(rows[y][x], colour, alpha * edge)


def _band(rows, y0: int, y1: int, colour: tuple, alpha: float) -> None:
    for y in range(max(0, y0), min(HEIGHT, y1)):
        for x in range(WIDTH):
            rows[y][x] = _blend(rows[y][x], colour, alpha)


def _confetti(rows) -> None:
    """Scattered discs, placed deterministically so every run is identical.

    A small linear congruential generator rather than `random`, and rather
    than the golden angle a first version used - the golden angle laid the
    confetti along visible spiral arms, which read as a pattern instead of as
    thrown confetti.
    """
    palette = [BRAND, BRAND_LIGHT, GOLD, ROSE, TEAL]
    seed = 20260924

    def nxt() -> float:
        nonlocal seed
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        return seed / 0x7FFFFFFF

    for index in range(190):
        cx = nxt() * WIDTH
        cy = nxt() * HEIGHT

        # Thinner towards the middle, so the banner stays calm where a
        # caption would sit if one is ever added.
        middle = abs(cy - HEIGHT / 2) / (HEIGHT / 2)
        if middle < 0.42 and nxt() > 0.35:
            continue

        size = 4 + nxt() * 13
        colour = palette[int(nxt() * len(palette)) % len(palette)]
        alpha = 0.28 + nxt() * 0.42
        _disc(rows, cx, cy, size, colour, alpha)


def _ribbon(rows) -> None:
    """A soft brand band across the lower third, to anchor the composition."""
    _band(rows, HEIGHT - 96, HEIGHT - 88, BRAND, 0.22)
    _band(rows, HEIGHT - 88, HEIGHT, BRAND, 0.10)

    for index in range(9):
        cx = 120 + index * 120
        _disc(rows, cx, HEIGHT - 44, 12, BRAND, 0.35)


def _encode_png(rows) -> bytes:
    """A minimal 8-bit RGB PNG. stdlib only."""
    raw = bytearray()
    for row in rows:
        raw.append(0)                                 # filter type 0 (None)
        for red, green, blue in row:
            raw += bytes((red, green, blue))

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0)

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="build the image but write nothing.")
    args = parser.parse_args()

    print("=" * 74)
    print("CELEBRATION GRAPHIC - an abstract banner, not a person")
    print("=" * 74)

    rows = _canvas()
    _confetti(rows)
    _ribbon(rows)
    data = _encode_png(rows)

    print(f"  size      : {WIDTH}x{HEIGHT}, {len(data):,} bytes")
    print(f"  detected  : {social_storage.detect_image_type(data)}")

    if len(data) > social_storage.MAX_IMAGE_BYTES:
        print("  TOO LARGE for the Social Hub's own limit. Not stored.")
        return 1

    if args.dry_run:
        print("  dry run - nothing written.")
        return 0

    stored_path = social_storage.store_image(data)
    name = social_storage.media_name(stored_path)

    print(f"  stored    : {stored_path}")
    print(f"  served at : {social_storage.media_url(stored_path)}")
    print()
    print("  Put this line in .env so celebrations carry it:")
    print()
    print(f"    SMARTHR_CELEBRATION_IMAGE={name}")
    print()
    print("  With it unset, celebrations are text only - nothing breaks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
