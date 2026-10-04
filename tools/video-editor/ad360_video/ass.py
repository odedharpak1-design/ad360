"""Build an Advanced SubStation Alpha (.ass) file with the captions and the
text overlays. libass (used by ffmpeg) shapes Hebrew correctly (RTL)."""

from __future__ import annotations

from .captions import CaptionLine, CaptionSettings, display_text
from .overlays import TextOverlay, anchor, px

RLM = "‏"


def ass_color(value: str) -> str:
    """'#RRGGBB' or '#RRGGBBAA' (AA = opacity) -> '&HAABBGGRR' (AA = transparency)."""
    v = value.strip().lstrip("#")
    if len(v) == 6:
        v += "FF"
    if len(v) != 8:
        raise ValueError(f"Bad colour {value!r}; use #RRGGBB or #RRGGBBAA")
    r, g, b, a = v[0:2], v[2:4], v[4:6], int(v[6:8], 16)
    return f"&H{255 - a:02X}{b}{g}{r}".upper()


def _ts(t: float) -> str:
    cs = int(round(max(0.0, t) * 100))
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02}:{s:02}.{cs:02}"


def _clean(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def _rtl(text: str) -> str:
    # Start each visual line with a right-to-left mark so lines that begin
    # with a number or a Latin word are still laid out right-to-left.
    return "\\N".join(RLM + part for part in text.split("\\N"))


def _style(name, font, size, primary, outline_c, back_c, bold, border_style, outline, shadow, align, ml, mr, mv):
    return (
        f"Style: {name},{font},{size},{primary},{primary},{outline_c},{back_c},"
        f"{-1 if bold else 0},0,0,0,100,100,0,0,{border_style},{outline:g},{shadow:g},{align},{ml},{mr},{mv},1"
    )


def build_ass(
    width: int,
    height: int,
    lines: list[CaptionLine],
    cs: CaptionSettings,
    texts: list[TextOverlay],
) -> str:
    short = min(width, height)
    styles: list[str] = []
    events: list[str] = []

    # ---- captions
    size = cs.font_size or round(min(height * 0.065, width * 0.06))
    outline = cs.outline or max(2, round(size * 0.08))
    portrait = height > width
    margin_v = cs.margin or round(height * (0.13 if portrait else 0.07))
    align = {"bottom": 2, "middle": 5, "center": 5, "top": 8}.get(cs.position, 2)
    if cs.box:
        styles.append(_style("Caption", cs.font, size, ass_color(cs.color), ass_color(cs.box_color),
                             ass_color(cs.box_color), cs.bold, 3, max(4, outline), 0, align,
                             round(width * 0.05), round(width * 0.05), margin_v))
    else:
        styles.append(_style("Caption", cs.font, size, ass_color(cs.color), ass_color(cs.outline_color),
                             "&H80000000", cs.bold, 1, outline, cs.shadow, align,
                             round(width * 0.05), round(width * 0.05), margin_v))
    if cs.enabled:
        for ln in lines:
            events.append(f"Dialogue: 1,{_ts(ln.start)},{_ts(ln.end)},Caption,,0,0,0,,{_rtl(_clean(display_text(ln, cs)))}")

    # ---- text overlays
    an_map = {(0.0, 0.0): 7, (0.5, 0.0): 8, (1.0, 0.0): 9, (0.0, 0.5): 4, (0.5, 0.5): 5,
              (1.0, 0.5): 6, (0.0, 1.0): 1, (0.5, 1.0): 2, (1.0, 1.0): 3}
    for i, t in enumerate(texts):
        ax, ay, use_margin = anchor(t.position)
        fsize = round(px(t.font_size, height))
        name = f"Text{i}"
        if t.box:
            styles.append(_style(name, t.font or cs.font, fsize, ass_color(t.color), ass_color(t.box_color),
                                 ass_color(t.box_color), t.bold, 3, max(6, round(fsize * 0.2)), 0, 5, 0, 0, 0))
        else:
            styles.append(_style(name, t.font or cs.font, fsize, ass_color(t.color), ass_color(t.outline_color),
                                 "&H80000000", t.bold, 1, t.outline, 0, 5, 0, 0, 0))
        if use_margin:
            m = px(t.margin, short)
            x = m + ax * (width - 2 * m)
            y = m + ay * (height - 2 * m)
            an = an_map[(ax, ay)]
        else:
            x, y, an = ax * width, ay * height, 5
        fade = round(t.fade * 1000)
        tags = f"{{\\an{an}\\pos({x:.0f},{y:.0f})\\fad({fade},{fade})}}"
        events.append(f"Dialogue: 2,{_ts(t.when.start)},{_ts(t.when.end)},{name},,0,0,0,,{tags}{_rtl(_clean(t.text))}")

    header = (
        "[Script Info]\nScriptType: v4.00+\nWrapStyle: 0\nScaledBorderAndShadow: yes\n"
        f"PlayResX: {width}\nPlayResY: {height}\nYCbCr Matrix: TV.709\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
    )
    body = "\n".join(styles) + "\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    return header + body + "\n".join(events) + "\n"
