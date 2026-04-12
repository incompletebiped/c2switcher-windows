"""Theme definitions — exact port of the THEMES dict from applet.js."""

from __future__ import annotations

THEMES: dict[str, dict] = {
    'classic': {
        'accountColors': ['#CC785C', '#E69A7B', '#F0AB8A', '#D88A6D', '#C47259'],
        'panelOk':      '#8BC34A',
        'panelWarn':    '#E69A7B',
        'panelErr':     '#CC785C',
        'activeDot':    '#8BC34A',
        'indNull':      {'bg': 'rgba(128,128,128,0.12)', 'border': 'rgba(255,255,255,0.15)'},
        'indOk':        {'bg': 'rgba(102,178,76,0.10)',  'border': 'rgba(102,178,76,0.3)'},
        'indWarn':      {'bg': 'rgba(230,153,77,0.15)',  'border': 'rgba(230,153,77,0.4)'},
        'indErr':       {'bg': 'rgba(204,76,51,0.15)',   'border': 'rgba(204,76,51,0.4)'},
        'indHighlight': 'rgba(100,149,237,0.6)',
        # General UI colours used by the popup
        'bg':           '#1E1E1E',
        'cardBg':       '#2A2A2A',
        'cardActiveBg': '#2E2E1A',
        'separator':    '#3A3A3A',
        'titleColor':   '#CC785C',
        'textPrimary':  '#E0E0E0',
        'textSecondary':'#909090',
    },
    'retro': {
        'accountColors': ['#7F77DD', '#534AB7', '#AFA9EC', '#3C3489', '#9A94E8'],
        'panelOk':      '#639922',
        'panelWarn':    '#BA7517',
        'panelErr':     '#E24B4A',
        'activeDot':    '#639922',
        'indNull':      {'bg': 'rgba(63,52,137,0.25)',   'border': 'rgba(127,119,221,0.2)'},
        'indOk':        {'bg': 'rgba(99,153,34,0.12)',   'border': 'rgba(99,153,34,0.4)'},
        'indWarn':      {'bg': 'rgba(186,117,23,0.15)',  'border': 'rgba(186,117,23,0.45)'},
        'indErr':       {'bg': 'rgba(226,75,74,0.15)',   'border': 'rgba(226,75,74,0.45)'},
        'indHighlight': 'rgba(127,119,221,0.7)',
        # General UI colours
        'bg':           '#1A1828',
        'cardBg':       '#221F38',
        'cardActiveBg': '#2A2745',
        'separator':    '#332F50',
        'titleColor':   '#AFA9EC',
        'textPrimary':  '#EEEDFE',
        'textSecondary':'#8880C0',
    },
}

DEFAULT_THEME = 'retro'


def load_theme_pref() -> str:
    from ...constants import THEME_PREF_PATH
    try:
        import json
        data = json.loads(THEME_PREF_PATH.read_text(encoding='utf-8'))
        name = data.get('theme', DEFAULT_THEME)
        return name if name in THEMES else DEFAULT_THEME
    except Exception:
        return DEFAULT_THEME


def save_theme_pref(name: str):
    from ...constants import THEME_PREF_PATH
    try:
        import json
        from ...utils import atomic_write_json
        atomic_write_json(THEME_PREF_PATH, {'theme': name})
    except Exception:
        pass
