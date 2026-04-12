"""Dynamic tray icon renderer.

Generates an SVG string (exact port of applet.js _generateIconSvg) and renders
it via PySide6.QtSvg.QSvgRenderer → QImage → PIL Image.

This gives pixel-perfect output matching the Cinnamon applet icon.

Must be called from the Qt main thread (QSvgRenderer requirement).
"""

from __future__ import annotations

import io

from PIL import Image


# ── Colours (exact from applet.js / ICON_SPEC.md) ───────────────────────────

_BG       = '#26215C'
_ACTIVE   = '#7F77DD'
_INACTIVE = '#534AB7'
_DIM      = '#3C3489'
_BRIGHT   = '#EEEDFE'
_DIM_FG   = '#AFA9EC'

_DOT_COLORS = {'ok': '#639922', 'warning': '#BA7517', 'limit': '#E24B4A'}


# ── SVG generator (direct port of applet.js _generateIconSvg) ────────────────

def generate_icon_svg(active_index: int, worst_status: str, num_accounts: int) -> str:
    """Return an SVG string for the tray icon.

    This is a line-for-line port of C2SwitcherApplet._generateIconSvg() from
    applet/applet.js.  The geometry is identical to icon-spec.svg.

    Args:
        active_index: 0-based account index that is currently active (-1 = none)
        worst_status: 'ok' | 'warning' | 'limit'
        num_accounts: total accounts (rows capped at 3)
    """
    dot_color = _DOT_COLORS.get(worst_status, _DOT_COLORS['ok'])
    num_rows = min(max(num_accounts, 0), 3)

    # Row geometry: (y, h, cy, cr, ly, lw, lh, sy, sw, sh)
    # Matches the defs array in applet.js _generateIconSvg exactly.
    defs = [
        {'y': 32,  'h': 56, 'cy': 60,  'cr': 16, 'ly': 52,  'lw': 90, 'lh': 8, 'sy': 66,  'sw': 58, 'sh': 6},
        {'y': 96,  'h': 56, 'cy': 124, 'cr': 16, 'ly': 116, 'lw': 90, 'lh': 8, 'sy': 130, 'sw': 58, 'sh': 6},
        {'y': 160, 'h': 44, 'cy': 182, 'cr': 12, 'ly': 178, 'lw': 72, 'lh': 7, 'sy': 0,   'sw': 0,  'sh': 0},
    ]

    rows = ''
    for i in range(num_rows):
        d = defs[i]
        is_act = (i == active_index)
        row_fill = _ACTIVE if is_act else (_DIM if i == 2 else _INACTIVE)
        fg = _BRIGHT if is_act else _DIM_FG

        # Row background
        rows += (
            f'<rect x="32" y="{d["y"]}" width="192" height="{d["h"]}" rx="12" fill="{row_fill}"/>'
        )
        # Avatar circle
        rows += f'<circle cx="60" cy="{d["cy"]}" r="{d["cr"]}" fill="{fg}"/>'
        # Primary label bar
        rows += (
            f'<rect x="86" y="{d["ly"]}" width="{d["lw"]}" height="{d["lh"]}" rx="4" fill="{fg}"/>'
        )
        # Sub-label bar (rows 0 and 1 only)
        if d['sh'] > 0:
            sub_fill = _BRIGHT if is_act else row_fill
            sub_op   = '0.45' if is_act else '0.5'
            rows += (
                f'<rect x="86" y="{d["sy"]}" width="{d["sw"]}" height="{d["sh"]}" rx="3"'
                f' fill="{sub_fill}" opacity="{sub_op}"/>'
            )
        # Active tick (right inner edge)
        if is_act:
            ty = d['y'] + 8
            th = d['h'] - 16
            rows += (
                f'<rect x="216" y="{ty}" width="6" height="{th}" rx="3"'
                f' fill="{_BRIGHT}" opacity="0.45"/>'
            )

    # Status dot with dark halo
    dot = f'<circle cx="220" cy="220" r="28" fill="{_BG}"/>'
    dot += f'<circle cx="220" cy="220" r="20" fill="{dot_color}"/>'

    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">'
        f'<rect width="256" height="256" rx="56" fill="{_BG}"/>'
        f'{rows}{dot}'
        '</svg>'
    )


# ── SVG → PIL Image via Qt ────────────────────────────────────────────────────

def _svg_to_pil(svg_str: str, size: int) -> Image.Image:
    """Render an SVG string to a PIL RGBA Image using Qt's SVG renderer.

    Must be called from the Qt main thread.
    """
    from PySide6.QtCore import QByteArray, QBuffer, QIODevice
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    renderer = QSvgRenderer(QByteArray(svg_str.encode('utf-8')))

    qimg = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    qimg.fill(0)

    painter = QPainter(qimg)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()

    # QImage → PIL via PNG round-trip
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    qimg.save(buf, 'PNG')
    buf.close()

    pil = Image.open(io.BytesIO(bytes(buf.data())))
    return pil.convert('RGBA')


# ── Public API ────────────────────────────────────────────────────────────────

def render_tray_icon(
    active_index: int,
    worst_status: str,
    num_accounts: int,
    size: int = 64,
) -> Image.Image:
    """Generate and render the tray icon for the given account state.

    Returns a PIL RGBA Image of the requested size.
    Must be called from the Qt main thread.

    Args:
        active_index: 0-based active account index (-1 = none)
        worst_status: 'ok' | 'warning' | 'limit'
        num_accounts: total registered accounts
        size: output pixel size (default 64)
    """
    svg = generate_icon_svg(active_index, worst_status, num_accounts)
    return _svg_to_pil(svg, size)


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
