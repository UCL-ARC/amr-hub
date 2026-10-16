"""Design tokens and global CSS for the AMR-Hub dashboard."""

COLORWAY = [
    "#0f766e",
    "#4f46e5",
    "#f59e0b",
    "#e11d48",
    "#0ea5e9",
    "#a855f7",
    "#64748b",
    "#84cc16",
]

APP_CSS = """
:root {
  --amr-bg: #f3f6f9;
  --amr-surface: #ffffff;
  --amr-border: #e2e8f0;
  --amr-track: #e5eaf0;
  --amr-text: #0f172a;
  --amr-muted: #64748b;
  --amr-primary: #0f766e;
  --amr-accent: #4f46e5;
  --amr-ok: #16a34a;
  --amr-warn: #d97706;
  --amr-danger: #dc2626;
  --amr-shadow: 0 1px 2px rgba(15,23,42,.06), 0 4px 16px rgba(15,23,42,.06);
  --amr-radius: 16px;
}
.theme--dark {
  --amr-bg: #0b1220;
  --amr-surface: #111a2b;
  --amr-border: #1f2b40;
  --amr-track: #223049;
  --amr-text: #e2e8f0;
  --amr-muted: #94a3b8;
  --amr-primary: #2dd4bf;
  --amr-accent: #818cf8;
  --amr-ok: #4ade80;
  --amr-warn: #fbbf24;
  --amr-danger: #fb7185;
  --amr-shadow: 0 1px 2px rgba(0,0,0,.4), 0 4px 16px rgba(0,0,0,.35);
}
.v-application, .v-application--wrap { background: var(--amr-bg) !important; }
.v-application { color: var(--amr-text); font-family: Inter, "Segoe UI", Roboto,
  system-ui, sans-serif !important; }

/* header */
.amr-header { display: flex; align-items: center; gap: 14px; padding: 12px 24px;
  background: var(--amr-surface); border-bottom: 1px solid var(--amr-border);
  position: sticky; top: 0; z-index: 20; flex-wrap: wrap; }
.amr-brand { display: flex; align-items: center; gap: 12px; }
.amr-brand h1 { font-size: 1.15rem; line-height: 1.1; margin: 0; font-weight: 700;
  letter-spacing: -.01em; }
.amr-brand span { font-size: .78rem; color: var(--amr-muted); }
.amr-nav { display: flex; gap: 6px; margin-left: 28px; }
.amr-nav a { display: inline-flex; align-items: center; gap: 8px; padding: 8px 14px;
  border-radius: 999px; color: var(--amr-muted) !important; font-weight: 600;
  font-size: .9rem; text-decoration: none !important; transition: all .15s; }
.amr-nav a:hover { background: var(--amr-track); color: var(--amr-text) !important; }
.amr-nav a.active { background: var(--amr-primary); color: #fff !important; }
.theme--dark .amr-nav a.active { color: #042f2a !important; }
.amr-spacer { flex: 1; }

/* layout */
.amr-page { max-width: 1480px; margin: 0 auto; padding: 24px; width: 100%;
  box-sizing: border-box; }
.amr-grid-2 { display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(0, 1fr);
  gap: 20px; align-items: start; }
.amr-grid-auto { display: grid; gap: 20px;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 520px), 1fr));
  min-width: 0; }
@media (max-width: 1000px) { .amr-grid-2 { grid-template-columns: 1fr; }
  .amr-nav { margin-left: 0; } .amr-grid-auto { grid-template-columns: 1fr; } }

/* cards */
.amr-card { background: var(--amr-surface); border: 1px solid var(--amr-border);
  border-radius: var(--amr-radius); box-shadow: var(--amr-shadow); padding: 20px; }
.amr-card h2 { font-size: 1.05rem; margin: 0 0 4px; font-weight: 700; }
.amr-card .amr-hint { color: var(--amr-muted); font-size: .85rem; margin-bottom: 14px; }
.amr-paper { background: #fbfcfd; border-radius: 12px; padding: 8px;
  border: 1px solid var(--amr-border); }
.amr-paper svg { width: 100%; height: auto; display: block; }
.amr-svg svg { width: 100%; height: auto; }

/* KPI strip */
.amr-kpis { display: grid; gap: 16px; margin-bottom: 20px;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }
.amr-kpi { display: flex; align-items: center; gap: 14px; background: var(--amr-surface);
  border: 1px solid var(--amr-border); border-radius: var(--amr-radius);
  box-shadow: var(--amr-shadow); padding: 16px 18px; }
.amr-kpi-badge { width: 46px; height: 46px; border-radius: 14px; display: grid;
  place-items: center; color: var(--tone);
  background: color-mix(in srgb, var(--tone) 14%, transparent); flex: none; }
.amr-kpi-label { color: var(--amr-muted); font-size: .8rem; font-weight: 600;
  text-transform: uppercase; letter-spacing: .04em; }
.amr-kpi-value { font-size: 1.55rem; font-weight: 700; line-height: 1.15; }
.amr-kpi-sub { color: var(--amr-muted); font-size: .8rem; }

/* gauges, chips */
.amr-rings { display: flex; gap: 18px; flex-wrap: wrap; margin: 6px 0 4px; }
.amr-ring { display: flex; flex-direction: column; align-items: center; }
.amr-ring-label { font-size: .78rem; color: var(--amr-muted); font-weight: 600;
  margin-top: 2px; }
.amr-chip { display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px;
  border-radius: 999px; font-size: .78rem; font-weight: 600; color: var(--chip);
  background: color-mix(in srgb, var(--chip) 14%, transparent); white-space: nowrap; }
.amr-legend { display: flex; gap: 8px; flex-wrap: wrap; }

/* agent header + timeline */
.amr-agent { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.amr-avatar { width: 44px; height: 44px; border-radius: 50%; display: grid;
  place-items: center; color: #fff;
  background: linear-gradient(135deg, var(--amr-primary), var(--amr-accent)); }
.amr-agent b { font-size: 1.05rem; }
.amr-timeline { max-height: 380px; overflow: auto; margin-top: 10px;
  padding-right: 4px; }
.amr-task { display: flex; align-items: center; gap: 12px; padding: 10px 12px;
  border-radius: 12px; border: 1px solid var(--amr-border); margin-bottom: 8px;
  background: color-mix(in srgb, var(--amr-track) 35%, transparent); }
.amr-task-name { font-weight: 600; }
.amr-task-meta { color: var(--amr-muted); font-size: .78rem; }
.amr-task > div:nth-child(2) { flex: 1; min-width: 0; }

/* misc */
.amr-empty { text-align: center; padding: 36px 16px; color: var(--amr-muted); }
.amr-empty h3 { color: var(--amr-text); margin: 12px 0 4px; }
.amr-center { display: flex; flex-direction: column; align-items: center;
  gap: 12px; padding: 40px 0; color: var(--amr-muted); }
.amr-footer { display: flex; align-items: center; gap: 16px; justify-content: center;
  padding: 28px 24px 36px; color: var(--amr-muted); font-size: .85rem; }
.amr-qr { width: 64px; height: 64px; background: #fff; padding: 4px;
  border-radius: 10px; border: 1px solid var(--amr-border); }
.amr-footer a { color: var(--amr-primary) !important; font-weight: 600; }
.amr-btn.v-btn { text-transform: none !important; letter-spacing: 0 !important;
  font-weight: 600; border-radius: 12px !important; }
.amr-btn .amr-btn-icon { display: inline-flex; margin-right: 6px; }
.v-tab { text-transform: none !important; font-weight: 600; letter-spacing: 0 !important; }
.amr-hero { margin-bottom: 20px; }
.amr-hero h2 { margin: 0 0 4px; font-size: 1.5rem; letter-spacing: -.01em; }
.amr-hero p { margin: 0; color: var(--amr-muted); }
"""


def button_label(icon_svg: str, text: str) -> str:
    """Return button markup combining an SVG icon with text."""
    return f'<span class="amr-btn-icon">{icon_svg}</span>{text}'
