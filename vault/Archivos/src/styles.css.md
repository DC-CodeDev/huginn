@import "tailwindcss";

:root {
  --bg: #0F1117;
  --card: #1A1D27;
  --card-border: #272C3A;
  --field: #0C0E14;
  --field-border: #1E2230;
  --text: #E6E9F1;
  --sub: #565C70;
  --accent: #C4847A;
  --card-overlay: rgba(255,255,255,0.04);
  --card-overlay-border: rgba(255,255,255,0.06);
  --btn-overlay: rgba(255,255,255,0.06);
  --btn-overlay-border: rgba(255,255,255,0.08);
  --dashed-border: rgba(255,255,255,0.1);
  font-synthesis: none;
  text-rendering: optimizeLegibility;
}

[data-theme="light"] {
  --bg: #E8EBF0;
  --card: #FFFFFF;
  --card-border: #D6DBE6;
  --field: #EEF0F6;
  --field-border: #DCE0EA;
  --text: #0F1117;
  --sub: #5B6172;
  --accent: #C4847A;
  --card-overlay: rgba(0,0,0,0.03);
  --card-overlay-border: rgba(0,0,0,0.06);
  --btn-overlay: rgba(0,0,0,0.04);
  --btn-overlay-border: rgba(0,0,0,0.08);
  --dashed-border: rgba(0,0,0,0.1);
}

* { box-sizing: border-box; }
html, body, #root {
  width: 100%; height: 100%; margin: 0;
  background: var(--bg);
  font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
  color: var(--text);
  transition: background 0.2s, color 0.2s;
}
button, input, textarea { font: inherit; }

/* ── Clases utilitarias para el Home (del showcase huginn_standalone.html) ── */

.empty-state-btn {
  display: inline-flex; align-items: center; gap: 9px;
  padding: 11px 20px;
  font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
  font-size: 13.5px; font-weight: 600;
  color: var(--accent);
  background: rgba(196,132,122,0.10);
  border: 1px solid var(--accent);
  border-radius: 7px;
  cursor: pointer;
  line-height: normal;
  transition: background 0.15s, transform 0.1s;
}

.empty-state-btn:hover { background: rgba(196,132,122,0.18); }

/* ── 1c: Cards de Estudio ── */

.studio-card {
  transition: transform 0.25s cubic-bezier(0.2, 0.8, 0.2, 1), box-shadow 0.25s cubic-bezier(0.2, 0.8, 0.2, 1);
}

.studio-card:hover {
  transform: translateY(-3px);
  box-shadow: rgba(0, 0, 0, 0.3) 0px 18px 38px;
}

.new-studio-card {
  transition: background 0.18s, border-color 0.18s, transform 0.25s cubic-bezier(0.2, 0.8, 0.2, 1);
}

.new-studio-card:hover {
  background: var(--card);
  border-color: var(--accent);
  transform: translateY(-3px);
}
