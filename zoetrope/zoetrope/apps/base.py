"""App base classes + texture helpers (PIL/moderngl imported lazily).

Colors follow the suite "Adwaita-through-glass" tokens (see
beampro/docs/16-suite-design-language.md and zoetrope/tokens.py):
translucent white glass fills + strokes on the additive display (black
is transparent there), white text, Adwaita blue accent (drawn by the
renderer's focus border).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..scene import Panel


def _load_font(size: int):
    from PIL import ImageFont
    for path in (
        "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def pil_to_texture(ctx, img):
    """Upload a PIL image as an RGBA moderngl texture."""
    img = img.convert("RGBA")
    tex = ctx.texture(img.size, 4, img.tobytes())
    tex.build_mipmaps()
    tex.anisotropy = 8.0
    return tex


def _solid_texture(ctx, rgba, size):
    """A plain solid-colour RGBA texture (fallback when Pillow isn't installed)."""
    w, h = size
    tex = ctx.texture((w, h), 4, bytes(rgba) * (w * h))
    return tex


def _ellipsize(draw, text: str, font, max_w: int) -> str:
    """Trim `text` with a Unicode ellipsis until it fits in max_w pixels."""
    if draw.textlength(text, font=font) <= max_w:
        return text
    while text and draw.textlength(text + "…", font=font) > max_w:
        text = text[:-1]
    return text + "…"


def _draw_icon(d, kind: str, x: int, y: int, s: int, color) -> None:
    """Small vector glyphs so tiles read at a glance (no icon files needed)."""
    lw = max(2, s // 14)
    if kind == "photo":
        d.rounded_rectangle([x, y, x + s, y + s * 0.78], radius=s * 0.12,
                            outline=color, width=lw)
        d.ellipse([x + s * 0.16, y + s * 0.12, x + s * 0.34, y + s * 0.30], fill=color)
        d.polygon([(x + s * 0.10, y + s * 0.68), (x + s * 0.38, y + s * 0.34),
                   (x + s * 0.58, y + s * 0.58), (x + s * 0.72, y + s * 0.44),
                   (x + s * 0.90, y + s * 0.68)], fill=color)
    elif kind == "movie":
        d.rounded_rectangle([x, y + s * 0.24, x + s, y + s * 0.86], radius=s * 0.08,
                            outline=color, width=lw)
        d.polygon([(x, y + s * 0.24), (x + s, y + s * 0.06),
                   (x + s * 0.96, y - s * 0.06 + s * 0.24), (x, y + s * 0.13 + s * 0.24)],
                  fill=color)
        d.polygon([(x + s * 0.40, y + s * 0.40), (x + s * 0.40, y + s * 0.74),
                   (x + s * 0.66, y + s * 0.57)], fill=color)
    elif kind == "term":
        d.rounded_rectangle([x, y + s * 0.08, x + s, y + s * 0.86], radius=s * 0.10,
                            outline=color, width=lw)
        d.line([(x + s * 0.18, y + s * 0.30), (x + s * 0.40, y + s * 0.47),
                (x + s * 0.18, y + s * 0.64)], fill=color, width=lw)
        d.line([(x + s * 0.50, y + s * 0.64), (x + s * 0.80, y + s * 0.64)],
               fill=color, width=lw)


def _card_base(w: int, h: int, thumb=None):
    """Rounded card: vertical gradient (or a darkened thumbnail) inside an outline."""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    inset, radius = 8, 28
    card = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    cd = ImageDraw.Draw(card)
    # Glass fill: white ~16% at the top easing to ~9% (token glass-fill
    # is 12%; the gradient centers there and adds a top-lit read).
    for yy in range(h):
        t = yy / max(1, h - 1)
        a = int(41 - 18 * t)
        cd.line([(0, yy), (w, yy)], fill=(255, 255, 255, a))
    if thumb is not None:
        tw, th = thumb.size
        scale = max(w / tw, h / th)                      # cover-crop
        thumb = thumb.resize((int(tw * scale) or 1, int(th * scale) or 1))
        tx, ty = (thumb.width - w) // 2, (thumb.height - h) // 2
        thumb = thumb.crop((tx, ty, tx + w, ty + h)).convert("RGBA")
        card = Image.blend(card, thumb, 0.75)
        shade = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        sd = ImageDraw.Draw(shade)
        for yy in range(h):                              # legibility gradient
            a = int(200 * max(0.0, (yy / h - 0.35)) / 0.65)
            sd.line([(0, yy), (w, yy)], fill=(8, 12, 18, a))
        card = Image.alpha_composite(card, shade)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [inset, inset, w - inset, h - inset], radius=radius, fill=255)
    img.paste(card, (0, 0), mask)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([inset, inset, w - inset, h - inset], radius=radius,
                        outline=(255, 255, 255, 89), width=2)
    return img, d


def make_tile(ctx, title: str, subtitle: str = "", w: int = 512, h: int = 320,
              icon: str | None = None, thumb=None):
    """Render a launcher tile to a texture: rounded card, optional icon glyph or
    PIL-image thumbnail (cover-cropped, darkened toward the caption)."""
    try:
        from PIL import Image, ImageDraw  # noqa: F401
    except ImportError:
        return _solid_texture(ctx, (255, 255, 255, 31), (w, h))
    img, d = _card_base(w, h, thumb=thumb)
    if icon and thumb is None:
        _draw_icon(d, icon, 40, 40, 64, (255, 255, 255, 220))
    font = _load_font(44)
    sub_font = _load_font(22)
    d.text((36, h - 110), title, font=font, fill=(255, 255, 255, 255))
    if subtitle:
        d.text((36, h - 54), _ellipsize(d, subtitle, sub_font, w - 72),
               font=sub_font, fill=(255, 255, 255, 178))
    return pil_to_texture(ctx, img)


def clock_image(w: int = 640, h: int = 180, when=None):
    """The ambient clock strip (a PIL image; the shell uploads + refreshes it)."""
    import time as _time
    from PIL import Image, ImageDraw
    t = _time.localtime() if when is None else when
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    big = _load_font(96)
    small = _load_font(28)
    hhmm = _time.strftime("%H:%M", t)
    date = _time.strftime("%a %d %b", t)
    tw = d.textlength(hhmm, font=big)
    d.text(((w - tw) / 2, 8), hhmm, font=big, fill=(255, 255, 255, 230))
    dw = d.textlength(date, font=small)
    d.text(((w - dw) / 2, 124), date, font=small, fill=(255, 255, 255, 165))
    return img


def message_texture(ctx, lines: list[str], w: int = 1280, h: int = 720):
    """A big panel texture showing a few lines of text (errors, placeholders).
    Long lines are wrapped, and the font shrinks until everything fits."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return _solid_texture(ctx, (255, 255, 255, 31), (w, h))
    import textwrap
    img = Image.new("RGBA", (w, h), (255, 255, 255, 31))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([4, 4, w - 4, h - 4], radius=24,
                        outline=(255, 255, 255, 89), width=2)
    margin = 60
    for size in (40, 32, 26, 20):
        font = _load_font(size)
        char_w = max(1, int(d.textlength("M" * 10, font=font) // 10))
        cols = max(16, (w - 2 * margin) // char_w)
        wrapped = []
        for ln in lines:
            wrapped.extend(textwrap.wrap(ln, cols, subsequent_indent="  ") or [""])
        line_h = int(size * 1.5)
        if len(wrapped) * line_h <= h - 2 * margin:
            break
    y = max(margin, h // 2 - len(wrapped) * line_h // 2)
    for ln in wrapped:
        d.text((margin, y), ln, font=font, fill=(255, 255, 255, 255))
        y += line_h
    return pil_to_texture(ctx, img)


class App:
    """An app that presents one large focused panel in the shell."""
    id: str = "app"
    title: str = "App"
    accepts_text: bool = False     # True: keyboard text is routed to write_input
    handles_nav: bool = False      # True: prev/next go to nav() instead of resize
    wants_void: bool = False       # True: theater purity — blank the stage

    def panel(self) -> Panel:
        raise NotImplementedError

    def update(self, dt: float) -> None:
        pass

    def nav(self, delta: int) -> None:
        """prev/next while focused (only when handles_nav is True)."""

    def on_activate(self) -> None:
        """Enter/tap while the app is focused (e.g. play/pause)."""

    def ornament(self) -> Panel | None:
        """Optional secondary panel floating below the app panel
        (transport bars etc. — doc 17 §5); None when hidden."""
        return None

    def write_input(self, text: str) -> None:
        pass

    def close(self) -> None:
        pass


@dataclass
class AppSpec:
    id: str
    title: str
    subtitle: str
    factory: Callable[..., App]     # (ctx, get_proc_address) -> App
