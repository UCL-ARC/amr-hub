"""Inline SVG building blocks (icons, gauges, badges, QR code) for the dashboard.

All graphics are plain SVG strings that inherit colours from CSS variables
defined in ``ui_theme`` so they follow the light/dark theme automatically.
"""

from __future__ import annotations

import html
import re
from functools import lru_cache
from io import BytesIO

import qrcode
import qrcode.image.svg

# 24x24 stroke icons; each value is the inner SVG markup.
_ICONS: dict[str, str] = {
    "circle": '<circle cx="12" cy="12" r="9"/>',
    "moving": '<circle cx="12" cy="12" r="9"/><path d="M8 12h8M13 8l4 4-4 4"/>',
    "suspended": '<circle cx="12" cy="12" r="9"/><path d="M10 9v6M14 9v6"/>',
    "in_progress": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "completed": '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l3 3 5-6"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "users": (
        '<circle cx="9" cy="8" r="3"/><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6"/>'
        '<circle cx="17" cy="9" r="2.5"/><path d="M16 14.2c3 .3 5 2.4 5 5.8"/>'
    ),
    "virus": (
        '<circle cx="12" cy="12" r="4"/>'
        '<path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1'
        'M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1"/>'
    ),
    "exposed": ('<path d="M12 3l9 16H3z"/><path d="M12 10v4M12 17h.01"/>'),
    "link": (
        '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/>'
        '<path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>'
    ),
    "play": '<path d="M7 5v14l12-7z" fill="currentColor"/>',
    "pause": '<path d="M8 5v14M16 5v14"/>',
    "step": '<path d="M6 5v14l9-7z"/><path d="M18 5v14"/>',
    "reset": '<path d="M4 12a8 8 0 1 1 3 6.2"/><path d="M4 19v-5h5"/>',
    "download": '<path d="M12 4v11M7 11l5 5 5-5M5 20h14"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
    "cross": '<path d="M10 4h4v6h6v4h-6v6h-4v-6H4v-4h6z"/>',
    "nurse": (
        '<circle cx="12" cy="8" r="3.5"/><path d="M5 21c0-4 3-7 7-7s7 3 7 7"/>'
        '<path d="M12 5.5v5M9.5 8h5"/>'
    ),
    "bed": '<path d="M3 18V7M3 14h18v4M21 14v-3a3 3 0 0 0-3-3h-6v6"/>'
    '<circle cx="7" cy="11" r="1.5"/>',
    "floor": '<path d="M3 8l9-4 9 4-9 4zM3 12l9 4 9-4M3 16l9 4 9-4"/>',
    "map": '<path d="M9 4L3 6v14l6-2 6 2 6-2V4l-6 2z"/><path d="M9 4v14M15 6v14"/>',
    "chart": '<path d="M4 20V4M4 20h16"/><path d="M8 16l3-5 3 3 4-7"/>',
    "pie": '<path d="M12 3v9h9"/><path d="M20.5 15A9 9 0 1 1 9 3.5"/>',
    "trophy": (
        '<path d="M8 4h8v5a4 4 0 0 1-8 0zM8 6H4v1a4 4 0 0 0 4 4M16 6h4v1a4 4 0 0 1-4 4"/>'
        '<path d="M12 13v4M8 20h8"/>'
    ),
}

# Task progress -> (icon, CSS colour variable, label)
TASK_STATUS: dict[str, tuple[str, str, str]] = {
    "NOT_STARTED": ("circle", "--amr-muted", "Not started"),
    "MOVING_TO_LOCATION": ("moving", "--amr-accent", "Moving"),
    "SUSPENDED": ("suspended", "--amr-warn", "Suspended"),
    "IN_PROGRESS": ("in_progress", "--amr-primary", "In progress"),
    "COMPLETED": ("completed", "--amr-ok", "Completed"),
}

# Infection status -> (icon, CSS colour variable, label)
INFECTION_STATUS: dict[str, tuple[str, str, str]] = {
    "SUSCEPTIBLE": ("circle", "--amr-ok", "Susceptible"),
    "EXPOSED": ("exposed", "--amr-warn", "Exposed"),
    "INFECTED": ("virus", "--amr-danger", "Infected"),
    "RECOVERED": ("completed", "--amr-accent", "Recovered"),
}


def icon(name: str, size: int = 20, color: str = "currentColor") -> str:
    """Return an inline SVG icon."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.8" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        f"{_ICONS[name]}</svg>"
    )


def logo(size: int = 40) -> str:
    """Return the AMR-Hub logo: a medical cross with a transmission network."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        'viewBox="0 0 48 48" role="img" aria-label="AMR-Hub logo">'
        '<defs><linearGradient id="amrLogoGrad" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#0f766e"/><stop offset="1" stop-color="#4f46e5"/>'
        "</linearGradient></defs>"
        '<rect width="48" height="48" rx="12" fill="url(#amrLogoGrad)"/>'
        '<path d="M21 11h6v10h10v6H27v10h-6V27H11v-6h10z" fill="#fff" fill-opacity=".95"/>'
        '<g stroke="#fff" stroke-opacity=".7" stroke-width="1.4">'
        '<path d="M11 37l7-6M37 11l-7 6"/></g>'
        '<circle cx="10" cy="38" r="3" fill="#fbbf24"/>'
        '<circle cx="38" cy="10" r="3" fill="#fb7185"/></svg>'
    )


def _gauge_colour(value: float) -> str:
    if value >= 0.8:  # noqa: PLR2004
        return "var(--amr-danger)"
    if value >= 0.5:  # noqa: PLR2004
        return "var(--amr-warn)"
    return "var(--amr-ok)"


def ring(  # noqa: PLR0913
    value: float,
    label: str = "",
    *,
    size: int = 88,
    color: str | None = None,
    center: str | None = None,
    sub: str = "",
) -> str:
    """
    Return an SVG ring gauge.

    Parameters
    ----------
    value : float
        Fill level between 0 and 1.
    label : str, optional
        Caption rendered under the ring.
    size : int, optional
        Diameter in pixels.
    color : str | None, optional
        Stroke colour; defaults to a green/amber/red severity scale.
    center : str | None, optional
        Text in the middle; defaults to the percentage.
    sub : str, optional
        Small text under the centre text.

    """
    value = min(1.0, max(0.0, value))
    radius = 36
    circumference = 2 * 3.14159265 * radius
    stroke = color or _gauge_colour(value)
    centre_text = html.escape(center if center is not None else f"{value:.0%}")
    sub_markup = (
        f'<text x="50" y="64" text-anchor="middle" font-size="9" '
        f'fill="var(--amr-muted)">{html.escape(sub)}</text>'
        if sub
        else ""
    )
    caption = f'<div class="amr-ring-label">{html.escape(label)}</div>' if label else ""
    return (
        f'<div class="amr-ring"><svg width="{size}" height="{size}" viewBox="0 0 100 100"'
        f' role="img" aria-label="{html.escape(label)} {centre_text}">'
        f'<circle cx="50" cy="50" r="{radius}" fill="none" '
        'stroke="var(--amr-track)" stroke-width="9"/>'
        f'<circle cx="50" cy="50" r="{radius}" fill="none" stroke="{stroke}" '
        'stroke-width="9" stroke-linecap="round" '
        f'stroke-dasharray="{circumference * value:.2f} {circumference:.2f}" '
        'transform="rotate(-90 50 50)"/>'
        f'<text x="50" y="{"55" if sub else "56"}" text-anchor="middle" '
        f'font-size="20" font-weight="700" fill="var(--amr-text)">{centre_text}</text>'
        f"{sub_markup}</svg>{caption}</div>"
    )


def status_chip(kind: dict[str, tuple[str, str, str]], key: str) -> str:
    """Return a coloured pill with an icon for a task or infection status."""
    icon_name, colour, label = kind[key]
    return (
        f'<span class="amr-chip" style="--chip:var({colour})">'
        f"{icon(icon_name, 14)}{html.escape(label)}</span>"
    )


def status_icon(key: str, size: int = 22) -> str:
    """Return the coloured icon for a task status."""
    icon_name, colour, _ = TASK_STATUS[key]
    return icon(icon_name, size, f"var({colour})")


def legend(kind: dict[str, tuple[str, str, str]]) -> str:
    """Return a row of chips describing every status in ``kind``."""
    chips = "".join(status_chip(kind, key) for key in kind)
    return f'<div class="amr-legend">{chips}</div>'


def kpi_tile(  # noqa: PLR0913
    icon_name: str,
    label: str,
    value: str,
    sub: str = "",
    tone: str = "--amr-primary",
    *,
    visual: str = "",
) -> str:
    """Return a KPI tile; ``visual`` (e.g. a ring) replaces the icon badge."""
    badge = visual or (
        f'<div class="amr-kpi-badge" style="--tone:var({tone})">'
        f"{icon(icon_name, 22)}</div>"
    )
    sub_markup = f'<div class="amr-kpi-sub">{html.escape(sub)}</div>' if sub else ""
    return (
        f'<div class="amr-kpi">{badge}<div><div class="amr-kpi-label">'
        f'{html.escape(label)}</div><div class="amr-kpi-value">{html.escape(value)}'
        f"</div>{sub_markup}</div></div>"
    )


def spinner(size: int = 56) -> str:
    """Return an animated SVG spinner."""
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 50 50" role="status" '
        'aria-label="Loading"><circle cx="25" cy="25" r="20" fill="none" '
        'stroke="var(--amr-track)" stroke-width="5"/>'
        '<circle cx="25" cy="25" r="20" fill="none" stroke="var(--amr-primary)" '
        'stroke-width="5" stroke-linecap="round" stroke-dasharray="30 126">'
        '<animateTransform attributeName="transform" type="rotate" from="0 25 25" '
        'to="360 25 25" dur="0.9s" repeatCount="indefinite"/></circle></svg>'
    )


def empty_state(title: str, text: str) -> str:
    """Return an illustrated empty state (floorplan with a contact hotspot)."""
    art = (
        '<svg width="180" height="120" viewBox="0 0 180 120" fill="none" '
        'aria-hidden="true"><rect x="8" y="8" width="164" height="104" rx="10" '
        'stroke="var(--amr-border)" stroke-width="3"/>'
        '<path d="M70 8v46M70 76v36M70 54h102" stroke="var(--amr-border)" '
        'stroke-width="3"/>'
        '<circle cx="118" cy="82" r="22" fill="var(--amr-primary)" fill-opacity=".12"/>'
        '<circle cx="118" cy="82" r="12" fill="var(--amr-primary)" fill-opacity=".25"/>'
        '<circle cx="118" cy="82" r="5" fill="var(--amr-primary)"/>'
        '<circle cx="36" cy="32" r="4" fill="var(--amr-accent)"/>'
        '<circle cx="46" cy="38" r="4" fill="var(--amr-warn)"/></svg>'
    )
    return (
        f'<div class="amr-empty">{art}<h3>{html.escape(title)}</h3>'
        f"<p>{html.escape(text)}</p></div>"
    )


@lru_cache(maxsize=8)
def qr_svg(url: str) -> str:
    """Return a QR code for ``url`` as an inline SVG (generated once, cached)."""
    image = qrcode.make(
        url,
        image_factory=qrcode.image.svg.SvgPathImage,
        box_size=10,
        border=1,
    )
    buffer = BytesIO()
    image.save(buffer)
    markup = buffer.getvalue().decode("utf-8")
    return responsive_svg(markup)


def responsive_svg(markup: str) -> str:
    """Strip the XML prolog and fixed width/height so the SVG scales with CSS."""
    markup = markup[markup.index("<svg") :]
    end = markup.index(">") + 1
    root = re.sub(r'\s(?:width|height)="[^"]*"', "", markup[:end])
    return root + markup[end:]
