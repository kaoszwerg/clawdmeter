#!/usr/bin/env python3
"""The Professor — the monkey splash set, drawn here and generated to C.

One animal, many moods: every frame is the same 40x40 monkey (gold round
glasses, Pac-Man T-shirt, a few tousled tufts, a lopsided grin), drawn from
parameters — eyes, mouth, brows, arms, a small bob — plus an optional prop.
Nothing is traced or taken from elsewhere.

Writes:
  firmware/src/splash_animations_monkey.h   (built with -DSPLASH_SET_MONKEY)
  tools/monkey/preview/*.gif                 (one per animation + all.gif)

Names match the stock set, so the firmware's rotation groups and the host
API's state animations (allow, done, work coding, ...) pick these up as they
are. Run:  python tools/monkey/make_monkey.py   (needs Pillow)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, replace

from PIL import Image, ImageDraw

N = 40
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
OUT_H = os.path.join(REPO, "firmware", "src", "splash_animations_monkey.h")
PREVIEW = os.path.join(HERE, "preview")

# One palette for the whole set: index 0 is transparent (black on the panel),
# 15 colours after it. Order is the index order in the generated header.
PALETTE = [
    ("clear", None),
    ("dark", "#3e2314"), ("fur", "#6e4126"), ("light", "#9a6238"), ("shine", "#c08450"),
    ("skin", "#f3cfa6"), ("skin_sh", "#d5a47a"), ("ear", "#e59a8a"),
    ("eye", "#141414"), ("white", "#ffffff"), ("mouth", "#7a2e2e"),
    ("gold", "#e8c547"), ("shirt", "#23305e"), ("shirt_sh", "#161f40"),
    ("pac", "#ffd21f"), ("grey", "#9aa0aa"),
]
C = {name: hexv for name, hexv in PALETTE}
assert len(PALETTE) <= 16

PAC = ["..###..",
       ".#####.",
       "####...",
       "###....",
       "####...",
       ".#####.",
       "..###.."]

TUFTS = [((13, 3), (16, 2), (13, -1)), ((17, 2), (20, 2), (19, -2)),
         ((21, 2), (24, 3), (25, 0))]

GLYPHS = {   # 5x7, for the little symbols over his head
    "?": [".###.", "#...#", "....#", "..##.", "..#..", ".....", "..#.."],
    "!": ["..#..", "..#..", "..#..", "..#..", "..#..", ".....", "..#.."],
    "z": ["#####", "...#.", "..#..", ".#...", "#####"],
    "Z": ["######", "....#.", "...#..", "..#...", ".#....", "######"],
}


@dataclass(frozen=True)
class Pose:
    dy: int = 0                 # whole-monkey vertical shift (bob, breathe)
    dx: int = 0                 # whole-monkey horizontal shift (sway)
    head_dy: int = 0            # head only, on top of dy (nod)
    eyes: str = "open"          # open, closed, half, happy, wide, wink
    look: tuple = (0, 0)        # pupil shift for open eyes
    mouth: str = "smirk"        # smirk, grin, o, flat, frown, open
    brows: str = "normal"       # normal, raised, angry, worried
    arms: str = "down"          # down, wave, wave2, chin, thumb, up, type_l, type_r, write
    glare: bool = True          # glint on the glasses
    props: tuple = field(default_factory=tuple)   # (kind, arg) overlays


def P(**kw) -> Pose:
    return Pose(**kw)


# --------------------------------------------------------------------------
# Drawing
# --------------------------------------------------------------------------

def glyph(d, ch, x, y, colour):
    for gy, row in enumerate(GLYPHS[ch]):
        for gx, c in enumerate(row):
            if c == "#":
                d.point((x + gx, y + gy), fill=colour)


def draw_body(d, p: Pose):
    ox, oy = p.dx, p.dy
    def R(x0, y0, x1, y1, col):
        d.rectangle([x0 + ox, y0 + oy, x1 + ox, y1 + oy], fill=C[col])

    # default arms hang by the sides; gestures replace one or both below
    left_down = p.arms not in ("up",)
    right_down = p.arms not in ("wave", "wave2", "thumb", "up", "chin", "write")
    if left_down:
        R(6, 33, 9, 38, "fur"); R(6, 37, 9, 39, "skin_sh")
    if right_down:
        R(30, 33, 33, 38, "fur"); R(30, 37, 33, 39, "skin_sh")
    d.rounded_rectangle([6 + ox, 29 + oy, 33 + ox, 35 + oy], 3, fill=C["shirt_sh"])
    d.rounded_rectangle([7 + ox, 29 + oy, 32 + ox, 34 + oy], 3, fill=C["shirt"])
    R(10, 30, 29, 39, "shirt")
    for y, row in enumerate(PAC):
        for x, c in enumerate(row):
            if c == "#":
                d.point((12 + x + ox, 33 + y + oy), fill=C["pac"])
    R(20, 36, 21, 37, "white"); R(24, 36, 25, 37, "white")


def draw_head(d, p: Pose):
    ox, oy = p.dx, p.dy + p.head_dy
    def E(box, col, outline=False):
        b = [box[0] + ox, box[1] + oy, box[2] + ox, box[3] + oy]
        if outline:
            d.ellipse(b, outline=C[col])
        else:
            d.ellipse(b, fill=C[col])
    def L(pts, col):
        d.line([(x + ox, y + oy) for x, y in pts], fill=C[col])
    def D(pts, col):
        d.point([(x + ox, y + oy) for x, y in pts], fill=C[col])

    for cx in (5, 34):                                   # ears
        E([cx - 5, 11, cx + 5, 22], "dark")
        E([cx - 4, 12, cx + 4, 21], "fur")
        E([cx - 2, 14, cx + 2, 19], "ear")
    E([5, 2, 34, 31], "dark")                            # skull
    E([6, 2, 33, 30], "fur")
    E([10, 4, 25, 11], "light")
    L([(14, 5), (18, 5)], "shine")
    for a, b, tip in TUFTS:                              # tousled tufts
        d.polygon([(a[0] + ox, a[1] + oy), (b[0] + ox, b[1] + oy),
                   (tip[0] + ox, tip[1] + oy)], fill=C["fur"])
        L([a, tip], "dark")
        D([tip], "light")
    E([9, 10, 20, 21], "skin")                           # face
    E([19, 10, 30, 21], "skin")
    E([11, 17, 28, 29], "skin_sh")
    E([11, 17, 28, 28], "skin")

    # brows
    if p.brows == "raised":
        L([(11, 8), (16, 7)], "dark"); L([(23, 7), (28, 8)], "dark")
    elif p.brows == "angry":
        L([(11, 7), (16, 9)], "dark"); L([(23, 9), (28, 7)], "dark")
    elif p.brows == "worried":
        L([(11, 9), (16, 7)], "dark"); L([(23, 7), (28, 9)], "dark")
    else:
        L([(11, 9), (16, 9)], "dark"); L([(23, 9), (28, 9)], "dark")

    # eyes (left eye at x=12, right at x=24; 4x4)
    lx, ly = p.look
    for i, ex in enumerate((12, 24)):
        mode = p.eyes
        if mode == "wink":
            mode = "happy" if i == 1 else "open"
        if mode == "open":
            x0, y0 = ex + lx, 13 + ly
            d.rectangle([x0 + ox, y0 + oy, x0 + 3 + ox, y0 + 3 + oy], fill=C["eye"])
            D([(x0, y0), (x0 + 1, y0), (x0, y0 + 1)], "white")
        elif mode == "half":
            d.rectangle([ex + ox, 15 + oy, ex + 3 + ox, 16 + oy], fill=C["eye"])
            L([(ex, 14), (ex + 3, 14)], "skin_sh")
            D([(ex, 15)], "white")
        elif mode == "closed":
            L([(ex, 15), (ex + 3, 15)], "eye")
        elif mode == "happy":
            D([(ex, 15), (ex + 1, 14), (ex + 2, 14), (ex + 3, 15)], "eye")
        elif mode == "wide":
            d.rectangle([ex - 1 + ox, 12 + oy, ex + 4 + ox, 17 + oy], fill=C["white"])
            d.rectangle([ex + 1 + lx + ox, 14 + ly + oy, ex + 2 + lx + ox, 15 + ly + oy], fill=C["eye"])

    D([(18, 21), (21, 21)], "skin_sh")                   # nostrils

    # mouth
    if p.mouth == "smirk":
        L([(15, 25), (21, 25)], "mouth"); L([(22, 24), (23, 24)], "mouth")
        D([(24, 23)], "mouth"); D([(25, 22)], "skin_sh")
    elif p.mouth == "grin":
        d.rectangle([15 + ox, 24 + oy, 24 + ox, 26 + oy], fill=C["mouth"])
        L([(16, 24), (23, 24)], "white")
        D([(14, 23), (25, 23)], "mouth")
    elif p.mouth == "o":
        d.ellipse([17 + ox, 23 + oy, 21 + ox, 27 + oy], fill=C["mouth"])
    elif p.mouth == "open":
        d.rectangle([17 + ox, 24 + oy, 21 + ox, 26 + oy], fill=C["mouth"])
    elif p.mouth == "flat":
        L([(16, 25), (22, 25)], "mouth")
    elif p.mouth == "frown":
        L([(16, 25), (22, 25)], "mouth"); D([(15, 26), (23, 26)], "mouth")

    # gold round glasses (sit higher when the eyes go wide)
    gy = -1 if p.eyes == "wide" else 0
    E([9, 10 + gy, 18, 19 + gy], "gold", outline=True)
    E([21, 10 + gy, 30, 19 + gy], "gold", outline=True)
    L([(19, 13 + gy), (20, 13 + gy)], "gold")
    L([(6, 13 + gy), (8, 13 + gy)], "gold"); L([(31, 13 + gy), (33, 13 + gy)], "gold")
    if p.glare:
        D([(11, 11 + gy), (23, 11 + gy)], "white")


def raise_arm(d, p: Pose, side: int, sway: int):
    """One arm raised from the shoulder: sleeve cap, a slanted furry arm with a
    dark outer edge, a round hand. side +1 = his left (image right), -1 = the
    other. `sway` tilts the hand outward by that many pixels (waving).

    The arm has to grow out of the shirt: drawn as a free-standing bar beside
    the head it read as a limb cut off at the shoulder.
    """
    ox, oy = p.dx, p.dy
    def X(x):                                  # mirror around the centre (19.5)
        return x if side > 0 else 39 - x
    sh = (X(31) + ox, 31 + oy)                 # shoulder, inside the sleeve
    el = (X(36 + sway) + ox, 13 + oy)          # wrist, up beside the head
    d.line([sh, el], fill=C["dark"], width=5)  # outline
    d.line([sh, el], fill=C["fur"], width=3)
    d.line([(sh[0] + side, sh[1] - 1), (el[0] + side, el[1])], fill=C["light"])
    hx, hy = el[0], el[1] - 4                  # hand above the wrist, clear of the ear
    d.ellipse([hx - 2, hy - 2, hx + 2, hy + 3], fill=C["skin_sh"])
    d.ellipse([hx - 2, hy - 2, hx + 1, hy + 2], fill=C["skin"])
    # sleeve cap over the shoulder so the arm visibly leaves the shirt
    x0, x1 = sorted((X(28) + ox, X(33) + ox))
    d.rounded_rectangle([x0, 28 + oy, x1, 33 + oy], 2, fill=C["shirt_sh"])
    d.rounded_rectangle([x0 + (1 if side < 0 else 0), 28 + oy,
                         x1 - (1 if side > 0 else 0), 32 + oy], 2, fill=C["shirt"])


def draw_arms(d, p: Pose):
    """Gestures that cross the head or body, drawn last."""
    ox, oy = p.dx, p.dy
    def R(x0, y0, x1, y1, col):
        d.rectangle([x0 + ox, y0 + oy, x1 + ox, y1 + oy], fill=C[col])
    if p.arms in ("wave", "wave2"):          # right arm raised, hand waving
        raise_arm(d, p, +1, 0 if p.arms == "wave" else 1)
    elif p.arms == "up":                      # both arms up (dance)
        raise_arm(d, p, +1, 0)
        raise_arm(d, p, -1, 0)
    elif p.arms == "thumb":                   # thumbs up in front of the chest
        R(30, 30, 33, 36, "fur")
        R(25, 27, 31, 32, "skin"); R(25, 31, 31, 32, "skin_sh")
        R(27, 23, 28, 26, "skin")             # thumb
    elif p.arms == "chin":                    # hand on chin, thinking
        R(30, 31, 33, 37, "fur")
        R(22, 27, 28, 30, "skin"); R(22, 30, 28, 30, "skin_sh")
        R(26, 30, 29, 32, "fur")
    elif p.arms in ("type_l", "type_r"):      # hands on the laptop
        up_l = 1 if p.arms == "type_l" else 0
        up_r = 1 - up_l
        R(9, 30 - up_l, 13, 32 - up_l, "skin")
        R(26, 30 - up_r, 30, 32 - up_r, "skin")
    elif p.arms == "write":                   # pencil in the right hand
        R(30, 31, 33, 36, "fur")
        R(25, 30, 29, 33, "skin")


def draw_props(d, p: Pose):
    for kind, arg in p.props:
        if kind == "laptop":                  # lid seen from behind, sticker
            d.rectangle([8, 31, 31, 39], fill=C["grey"])
            d.line([(8, 31), (31, 31)], fill=C["white"])
            glyph_sticker = [(17, 34), (16, 35), (17, 36), (22, 34), (23, 35), (22, 36),
                             (20, 33), (20, 34), (19, 35), (19, 36)]
            d.point(glyph_sticker, fill=C["shirt"])
        elif kind == "notepad":
            d.rectangle([9, 31, 24, 39], fill=C["white"])
            for y in (33, 35, 37):
                d.line([(11, y), (11 + arg[y], y)], fill=C["grey"])
        elif kind == "pencil":                # arg: (x, y) tip position
            x, y = arg
            d.line([(x, y), (x + 5, y - 5)], fill=C["gold"])
            d.point((x, y), fill=C["dark"])
        elif kind == "glyph":                 # arg: (char, x, y, colour)
            ch, x, y, col = arg
            glyph(d, ch, x, y, C[col])
        elif kind == "dots":                  # thought dots, arg = how many
            for i in range(arg):
                x, y = (31 + i * 3, 8 - i * 3)
                d.rectangle([x, y, x + 1, y + 1], fill=C["white"])
        elif kind == "steam":                 # arg: phase 0/1
            for x0 in (0, 36):
                y0 = 9 - arg * 2
                d.point([(x0 + 1, y0), (x0 + 2, y0 + 1), (x0 + 1, y0 + 2), (x0 + 2, y0 + 3)],
                        fill=C["white"])
        elif kind == "sparkle":               # arg: (x, y)
            x, y = arg
            d.point([(x, y - 1), (x - 1, y), (x, y), (x + 1, y), (x, y + 1)], fill=C["gold"])
        elif kind == "sweat":
            x, y = arg
            d.point([(x, y), (x, y + 1), (x - 1, y + 2), (x, y + 2)], fill=C["white"])


def render(p: Pose) -> Image.Image:
    im = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    draw_body(d, p)
    draw_head(d, p)
    # desk things go under the hands, symbols over everything
    under = tuple(pr for pr in p.props if pr[0] in ("laptop", "notepad"))
    over = tuple(pr for pr in p.props if pr[0] not in ("laptop", "notepad"))
    draw_props(d, replace(p, props=under))
    draw_arms(d, p)
    draw_props(d, replace(p, props=over))
    return im


# --------------------------------------------------------------------------
# The animations: (name, category, [(pose, hold_ms), ...])
# --------------------------------------------------------------------------

BASE = P()


def blink_seq(pose, open_ms):
    return [(pose, open_ms), (replace(pose, eyes="half"), 70),
            (replace(pose, eyes="closed"), 110), (replace(pose, eyes="half"), 70)]


def zzz(step):
    # right of the head, clear of the glasses and the ear, rising
    spots = [(34, 5), (35, 0)]
    return tuple(("glyph", ("z", x, y, "white")) for x, y in spots[:step % 3])


ANIMS = []

# --- neutral: the device's own rotation ------------------------------------
ANIMS.append(("idle breathe", "Idle",
              [(P(dy=0), 900), (P(dy=1), 900)] * 2
              + blink_seq(P(dy=0), 700) + [(P(dy=1), 900)]))

ANIMS.append(("idle blink", "Idle",
              blink_seq(BASE, 2200) + [(P(look=(-1, 0)), 1400)]
              + blink_seq(P(look=(-1, 0)), 300) + [(BASE, 1200)]
              + blink_seq(BASE, 150) + [(BASE, 1800)]))

ANIMS.append(("idle look around", "Idle",
              [(BASE, 1000), (P(look=(-1, 0)), 900), (P(look=(-1, -1)), 700),
               (BASE, 600), (P(look=(1, 0)), 900), (P(look=(1, -1), brows="raised"), 800),
               (P(look=(1, 0)), 500)] + blink_seq(BASE, 800)))

ANIMS.append(("expression sleep", "Expressions",
              [(P(eyes="closed", mouth="flat", head_dy=h, glare=False,
                  props=zzz(i)), 600)
               for i, h in enumerate([0, 1, 1, 0, 0, 1, 1, 0])]))

ANIMS.append(("expression wink", "Expressions",
              [(BASE, 1500), (P(eyes="wink", mouth="grin"), 700),
               (P(eyes="wink", mouth="grin", props=(("sparkle", (36, 6)),)), 500),
               (BASE, 1500)]))

bounce = [(P(dy=0, arms="up", mouth="grin", eyes="happy"), 220),
          (P(dy=2, arms="down", mouth="grin", eyes="happy"), 220)]
ANIMS.append(("dance bounce", "Dance", bounce * 4))

sway = [(P(dx=-2, look=(-1, 0), mouth="grin"), 300), (P(dx=0, mouth="grin"), 200),
        (P(dx=2, look=(1, 0), mouth="grin"), 300), (P(dx=0, mouth="grin"), 200)]
ANIMS.append(("dance sway", "Dance", sway * 2))

frantic = [(P(dy=0, arms="up", mouth="grin", eyes="wide", props=(("sweat", (6, 6)),)), 140),
           (P(dy=2, arms="down", mouth="open", eyes="wide", props=(("sweat", (6, 8)),)), 140),
           (P(dy=0, dx=1, arms="up", mouth="grin", eyes="wide"), 140),
           (P(dy=2, dx=-1, arms="down", mouth="open", eyes="wide"), 140)]
ANIMS.append(("dance djmix", "Dance", frantic * 3))

# --- states a host names (the host API's signals) ---------------------------
typing = []
for i in range(6):
    typing.append((P(eyes="open", look=(0, 1), mouth="flat",
                     arms="type_l" if i % 2 == 0 else "type_r",
                     glare=(i % 3 != 2), props=(("laptop", None),)), 160))
typing += [(P(look=(0, 1), mouth="smirk", arms="type_l", props=(("laptop", None),)), 700)]
ANIMS.append(("work coding", "Work", typing))

think = []
for n in (0, 1, 2, 3, 3):
    think.append((P(look=(1, -1), brows="raised", mouth="flat", arms="chin",
                    props=(("dots", n),)), 500))
think.append((P(look=(1, -1), brows="raised", mouth="flat", arms="chin", eyes="half",
                props=(("dots", 3),)), 250))
ANIMS.append(("work think", "Work", think))

ANIMS.append(("think", "Work",
              [(P(look=(0, -1), brows="raised", mouth="flat"), 700),
               (P(look=(0, -1), brows="raised", mouth="flat",
                  props=(("glyph", ("?", 33, 2, "gold")),)), 600),
               (P(look=(0, -1), brows="raised", mouth="flat",
                  props=(("glyph", ("?", 33, 1, "gold")),)), 600),
               (P(look=(1, -1), brows="raised", mouth="smirk",
                  props=(("glyph", ("?", 33, 2, "gold")),)), 800)]))

lens = {33: 10, 35: 12, 37: 7}
write = []
for i, x in enumerate((12, 15, 18, 21, 16, 20)):
    write.append((P(look=(-1, 1), mouth="flat", arms="write",
                    props=(("notepad", lens), ("pencil", (x, 36 - (i % 2))))), 220))
write.append((P(look=(0, 0), mouth="smirk", arms="write",
                props=(("notepad", lens), ("pencil", (20, 35)))), 800))
ANIMS.append(("write", "Work", write))

allow = [(P(arms="wave", brows="raised", mouth="open",
            props=(("glyph", ("?", 1, 1, "gold")),)), 350),
         (P(arms="wave2", brows="raised", mouth="open",
            props=(("glyph", ("?", 1, 0, "gold")),)), 350)] * 3
allow += [(P(arms="wave", brows="raised", mouth="smirk", look=(0, 1),
             props=(("glyph", ("?", 1, 1, "gold")),)), 900)]
ANIMS.append(("allow", "Session Browser", allow))

ANIMS.append(("done", "Session Browser",
              [(P(arms="thumb", mouth="grin"), 600),
               (P(arms="thumb", mouth="grin", eyes="wink",
                  props=(("sparkle", (4, 5)),)), 400),
               (P(arms="thumb", mouth="grin", eyes="wink",
                  props=(("sparkle", (4, 5)), ("sparkle", (35, 3)))), 400),
               (P(arms="thumb", mouth="grin"), 1200)]))

ANIMS.append(("limit", "Session Browser",
              [(P(brows="angry", mouth="frown", props=(("steam", i % 2),)), 300)
               for i in range(6)]
              + [(P(brows="angry", mouth="frown", eyes="closed",
                    props=(("steam", 1),)), 600)]))

ANIMS.append(("expression surprise", "Expressions",
              [(BASE, 600), (P(eyes="wide", mouth="o", brows="raised", dy=-1,
                              props=(("glyph", ("!", 33, 1, "gold")),)), 900),
               (P(eyes="wide", mouth="o", brows="raised",
                  props=(("glyph", ("!", 33, 1, "gold")),)), 700),
               (P(eyes="wide", mouth="open", brows="worried"), 600)]))

# The heavy group's other two names play the same frantic dance.
ALIASES = {"dance bounce dj": "dance djmix", "dance sway dj": "dance djmix"}


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def to_indices(im: Image.Image) -> list[int]:
    lut = {}
    for i, (_, hexv) in enumerate(PALETTE):
        if hexv:
            lut[tuple(int(hexv[k:k + 2], 16) for k in (1, 3, 5))] = i
    out = []
    for px in im.getdata():
        if px[3] == 0:
            out.append(0)
        else:
            out.append(lut[px[:3]])          # KeyError = a colour outside the palette
    return out


def rgb565(hexv: str | None) -> int:
    if not hexv:
        return 0
    r, g, b = (int(hexv[k:k + 2], 16) for k in (1, 3, 5))
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def ident(name: str) -> str:
    return "monkey_" + "".join(c if c.isalnum() else "_" for c in name)


def write_header(frames_by_anim):
    cells = N * N
    lines = [
        "// ============================================================",
        "// The Professor — monkey splash set, generated by",
        "// tools/monkey/make_monkey.py. Do not edit by hand: change the",
        "// generator and re-run it. Selected with -DSPLASH_SET_MONKEY",
        "// (see splash_set.h).",
        "// ============================================================",
        f"// {N}x{N} cells, one {len(PALETTE)}-entry RGB565 palette shared by every",
        "// animation; cell value 0 = empty (black).",
        "#pragma once",
        "#include <stdint.h>",
        "",
        f"#define SPLASH_GRID {N}",
        f"#define SPLASH_PALETTE_SIZE {len(PALETTE)}",
        "",
        "typedef struct {",
        "    const char *name;",
        "    const char *category;",
        "    uint16_t frame_count;",
        "    const uint16_t *palette;",
        f"    const uint8_t (*frames)[{cells}];",
        "    const uint16_t *holds;",
        "} splash_anim_def_t;",
        "",
        f"static const uint16_t monkey_palette[{len(PALETTE)}] = {{"
        + ",".join(f"0x{rgb565(h):04X}" for _, h in PALETTE) + "};",
        "",
    ]
    for name, (category, frames) in frames_by_anim.items():
        ide = ident(name)
        lines.append(f"static const uint8_t {ide}_frames[{len(frames)}][{cells}] = {{")
        for cells_list, _ in frames:
            lines.append("    {" + ",".join(map(str, cells_list)) + "},")
        lines.append("};")
        lines.append(f"static const uint16_t {ide}_holds[{len(frames)}] = {{"
                     + ",".join(str(h) for _, h in frames) + "};")
        lines.append("")
    table = []
    for name, (category, frames) in frames_by_anim.items():
        ide = ident(name)
        table.append(f'    {{"{name}", "{category}", {len(frames)}, monkey_palette, '
                     f"{ide}_frames, {ide}_holds}},")
    for alias, target in ALIASES.items():
        category, frames = frames_by_anim[target]
        ide = ident(target)
        table.append(f'    {{"{alias}", "{category}", {len(frames)}, monkey_palette, '
                     f"{ide}_frames, {ide}_holds}},")
    lines.append(f"#define SPLASH_ANIM_COUNT {len(table)}")
    lines.append("static const splash_anim_def_t splash_anims[SPLASH_ANIM_COUNT] = {")
    lines += table
    lines.append("};")
    with open(OUT_H, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def write_previews(images_by_anim, scale=8):
    os.makedirs(PREVIEW, exist_ok=True)
    tiles = []
    for name, frames in images_by_anim.items():
        big = [Image.alpha_composite(Image.new("RGBA", (N, N), (0, 0, 0, 255)), im)
               .resize((N * scale, N * scale), Image.NEAREST).convert("RGB")
               for im, _ in frames]
        big[0].save(os.path.join(PREVIEW, name.replace(" ", "_") + ".gif"), save_all=True,
                    append_images=big[1:], duration=[h for _, h in frames], loop=0)
        tiles.append((name, frames))
    # all.gif: every animation side by side on its own clock, 100 ms steps
    cols, s = 5, 5
    rows = (len(tiles) + cols - 1) // cols
    total = 8000
    out = []
    for t in range(0, total, 100):
        sheet = Image.new("RGB", (cols * N * s, rows * (N * s + 14)), "black")
        d = ImageDraw.Draw(sheet)
        for k, (name, frames) in enumerate(tiles):
            period = sum(h for _, h in frames)
            tt, idx = t % period, 0
            while tt >= frames[idx][1]:
                tt -= frames[idx][1]; idx += 1
            im = Image.alpha_composite(Image.new("RGBA", (N, N), (0, 0, 0, 255)), frames[idx][0])
            x, y = (k % cols) * N * s, (k // cols) * (N * s + 14)
            sheet.paste(im.resize((N * s, N * s), Image.NEAREST).convert("RGB"), (x, y + 14))
            d.text((x + 3, y), name, fill=(170, 170, 165))
        out.append(sheet)
    out[0].save(os.path.join(PREVIEW, "all.gif"), save_all=True, append_images=out[1:],
                duration=100, loop=0)


def main():
    images, cells = {}, {}
    for name, category, seq in ANIMS:
        frames = [(render(pose), hold) for pose, hold in seq]
        images[name] = frames
        cells[name] = (category, [(to_indices(im), hold) for im, hold in frames])
    write_header(cells)
    write_previews(images)
    n_frames = sum(len(f) for _, f in cells.values())
    print(f"{len(cells)} animations (+{len(ALIASES)} aliases), {n_frames} frames, "
          f"{n_frames * N * N / 1024:.0f} KB of cells -> {os.path.relpath(OUT_H, REPO)}")


if __name__ == "__main__":
    main()
