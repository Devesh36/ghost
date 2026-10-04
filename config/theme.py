"""Named terminal palettes. Renderers read colors at draw time for live switching."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    description: str
    text: str
    accent: str
    secondary: str
    muted: str
    border: str
    warning: str
    danger: str
    background: str
    surface: str
    code_theme: str = 'monokai'


THEMES = {
    'ghost': Palette('Ivory, mint and lavender', '#f2eee5', '#91d9be', '#c0b8e4', '#a1adbd',
                     '#465367', '#e9be7b', '#f28f9b', '#101720', '#17212e'),
    'dracula': Palette('Purple nights and pink accents', '#f8f8f2', '#bd93f9', '#ff79c6', '#b1b7d1',
                       '#626784', '#f1fa8c', '#ff5555', '#282a36', '#343746'),
    'nord': Palette('Arctic blues and quiet contrast', '#eceff4', '#88c0d0', '#81a1c1', '#bac4d5',
                    '#67758a', '#ebcb8b', '#bf616a', '#2e3440', '#3b4252'),
    'catppuccin': Palette('Soft mocha with mauve and peach', '#cdd6f4', '#cba6f7', '#fab387', '#a6adc8',
                          '#6c7086', '#f9e2af', '#f38ba8', '#1e1e2e', '#313244'),
    'amber': Palette('Warm gold on charcoal', '#f5e9d5', '#efbd72', '#d5a0b9', '#bfb2a0',
                     '#70665a', '#ffd27d', '#f49389', '#211c18', '#302821'),
    'paper': Palette('Light canvas with ink and teal', '#253342', '#00695c', '#63479b', '#566373',
                     '#83909a', '#865300', '#ad233a', '#faf7f0', '#e9e5dc', 'friendly'),
    'mono': Palette('Minimal grayscale; severity labels remain visible', '#ededed', '#ffffff', '#d0d0d0',
                    '#b0b0b0', '#777777', '#e0e0e0', '#ffffff', '#151515', '#252525', 'bw'),
}

ACTIVE_NAME = 'ghost'


def current() -> Palette:
    return THEMES[ACTIVE_NAME]


def activate(name: str) -> None:
    if name not in THEMES:
        raise ValueError('Unknown theme. Use ghost theme to list available themes.')
    global ACTIVE_NAME, TEXT, MINT, VIOLET, MUTED, BORDER, WARNING, DANGER, PALETTE
    ACTIVE_NAME = name
    palette = current()
    TEXT, MINT, VIOLET, MUTED = palette.text, palette.accent, palette.secondary, palette.muted
    BORDER, WARNING, DANGER = palette.border, palette.warning, palette.danger
    # A restrained highlight-to-shadow gradient keeps the mascot geometry intact.
    def mix(color, target, amount):
        parts = [round(int(color[i:i+2], 16) * (1-amount) + int(target[i:i+2], 16) * amount)
                 for i in (1, 3, 5)]
        return '#' + ''.join(f'{part:02x}' for part in parts)
    PALETTE = [mix(MINT, '#ffffff', .5), mix(MINT, '#ffffff', .35), mix(MINT, '#ffffff', .18),
               MINT, MINT, mix(MINT, palette.background, .06), mix(MINT, palette.background, .12),
               mix(MINT, palette.background, .2)]


activate(ACTIVE_NAME)
