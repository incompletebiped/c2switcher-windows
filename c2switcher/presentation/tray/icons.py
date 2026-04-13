"""Dynamic tray icon renderer.

Draws the icon using PIL directly (no Qt SVG dependency).
The geometry matches icon-spec.svg and the Cinnamon applet icon.
"""

from __future__ import annotations

from PIL import Image, ImageDraw


# ── Colours (exact from applet.js / ICON_SPEC.md) ───────────────────────────

_BG       = '#26215C'
_ACTIVE   = '#7F77DD'
_INACTIVE = '#534AB7'
_DIM      = '#3C3489'
_BRIGHT   = '#EEEDFE'
_DIM_FG   = '#AFA9EC'

_DOT_COLORS = {'ok': '#639922', 'warning': '#BA7517', 'limit': '#E24B4A'}


# ── PIL icon renderer ────────────────────────────────────────────────────────

def _draw_rounded_rect(draw: ImageDraw.ImageDraw, xy, radius, fill):
    """Draw a rounded rectangle (PIL doesn't have this in older versions)."""
    x0, y0, x1, y1 = xy
    r = min(radius, (x1 - x0) // 2, (y1 - y0) // 2)
    # Four corners
    draw.ellipse([x0, y0, x0 + 2 * r, y0 + 2 * r], fill=fill)
    draw.ellipse([x1 - 2 * r, y0, x1, y0 + 2 * r], fill=fill)
    draw.ellipse([x0, y1 - 2 * r, x0 + 2 * r, y1], fill=fill)
    draw.ellipse([x1 - 2 * r, y1 - 2 * r, x1, y1], fill=fill)
    # Two rectangles to fill the body
    draw.rectangle([x0 + r, y0, x1 - r, y1], fill=fill)
    draw.rectangle([x0, y0 + r, x1, y1 - r], fill=fill)


def _render_icon_pil(active_index: int, worst_status: str, num_accounts: int, size: int) -> Image.Image:
    """Render the tray icon at the given size using PIL.

    Draws at 256x256 (matching the SVG viewBox) then scales down.
    """
    S = 256
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    draw = ImageDraw.ImageDraw(img)

    # Background rounded rect
    _draw_rounded_rect(draw, (0, 0, S, S), 56, _BG)

    # Row geometry (matches applet.js exactly)
    defs = [
        {'y': 32,  'h': 56, 'cy': 60,  'cr': 16, 'ly': 52,  'lw': 90, 'lh': 8, 'sy': 66,  'sw': 58, 'sh': 6},
        {'y': 96,  'h': 56, 'cy': 124, 'cr': 16, 'ly': 116, 'lw': 90, 'lh': 8, 'sy': 130, 'sw': 58, 'sh': 6},
        {'y': 160, 'h': 44, 'cy': 182, 'cr': 12, 'ly': 178, 'lw': 72, 'lh': 7, 'sy': 0,   'sw': 0,  'sh': 0},
    ]

    num_rows = min(max(num_accounts, 0), 3)

    for i in range(num_rows):
        d = defs[i]
        is_act = (i == active_index)
        row_fill = _ACTIVE if is_act else (_DIM if i == 2 else _INACTIVE)
        fg = _BRIGHT if is_act else _DIM_FG

        # Row background
        _draw_rounded_rect(draw, (32, d['y'], 32 + 192, d['y'] + d['h']), 12, row_fill)

        # Avatar circle
        cx, cy, cr = 60, d['cy'], d['cr']
        draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=fg)

        # Primary label bar
        lx, ly = 86, d['ly']
        _draw_rounded_rect(draw, (lx, ly, lx + d['lw'], ly + d['lh']), 4, fg)

        # Sub-label bar (rows 0 and 1 only)
        if d['sh'] > 0:
            sx, sy = 86, d['sy']
            sub_fill = _BRIGHT if is_act else row_fill
            # Approximate opacity blending onto the row background
            _draw_rounded_rect(draw, (sx, sy, sx + d['sw'], sy + d['sh']), 3, sub_fill)

        # Active tick (right inner edge)
        if is_act:
            ty = d['y'] + 8
            th = d['h'] - 16
            _draw_rounded_rect(draw, (216, ty, 222, ty + th), 3, _BRIGHT)

    # Status dot with dark halo
    dot_color = _DOT_COLORS.get(worst_status, _DOT_COLORS['ok'])
    draw.ellipse([220 - 28, 220 - 28, 220 + 28, 220 + 28], fill=_BG)
    draw.ellipse([220 - 20, 220 - 20, 220 + 20, 220 + 20], fill=dot_color)

    if size != S:
        img = img.resize((size, size), Image.Resampling.LANCZOS)

    return img


# ── Public API ────────────────────────────────────────────────────────────────

def render_tray_icon(
    active_index: int,
    worst_status: str,
    num_accounts: int,
    size: int = 64,
) -> Image.Image:
    """Generate and render the tray icon for the given account state.

    Returns a PIL RGBA Image of the requested size.

    Args:
        active_index: 0-based active account index (-1 = none)
        worst_status: 'ok' | 'warning' | 'limit'
        num_accounts: total registered accounts
        size: output pixel size (default 64)
    """
    return _render_icon_pil(active_index, worst_status, num_accounts, size)


def worst_usage_status(accounts_usage: list[dict]) -> str:
    """Determine worst usage status across all accounts.

    Returns 'limit' | 'warning' | 'ok'.
    """
    worst = 'ok'
    for acc in accounts_usage:
        if not acc:
            continue
        for key in ('five_hour', 'seven_day', 'seven_day_sonnet'):
            w = acc.get(key)
            if not w:
                continue
            util = w.get('utilization')
            if util is None:
                continue
            if util >= 90:
                return 'limit'
            if util >= 70:
                worst = 'warning'
    return worst
