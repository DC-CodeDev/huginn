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
  --safe-top: env(safe-area-inset-top, 0px);
  --safe-right: env(safe-area-inset-right, 0px);
  --safe-bottom: env(safe-area-inset-bottom, 0px);
  --safe-left: env(safe-area-inset-left, 0px);
  --app-dvh: 100vh;
  font-synthesis: none;
  text-rendering: optimizeLegibility;
}

@supports (height: 100dvh) {
  :root {
    --app-dvh: 100dvh;
  }
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
  width: 100%; min-height: var(--app-dvh); margin: 0;
  background: var(--bg);
  font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
  color: var(--text);
  transition: background 0.2s, color 0.2s;
}
button, input, textarea { font: inherit; }

.app-dvh {
  min-height: var(--app-dvh);
}

.app-safe-page {
  padding-top: var(--safe-top);
  padding-right: var(--safe-right);
  padding-bottom: var(--safe-bottom);
  padding-left: var(--safe-left);
}

.app-safe-top-left {
  top: calc(16px + var(--safe-top));
  left: calc(16px + var(--safe-left));
}

.app-safe-top-right {
  top: calc(16px + var(--safe-top));
  right: calc(16px + var(--safe-right));
}

.app-safe-bottom-left {
  bottom: calc(16px + var(--safe-bottom));
  left: calc(16px + var(--safe-left));
}

.app-safe-bottom-center {
  bottom: calc(20px + var(--safe-bottom));
  left: 50%;
  transform: translateX(-50%);
}

.app-modal-backdrop {
  padding: calc(20px + var(--safe-top)) calc(16px + var(--safe-right)) calc(20px + var(--safe-bottom)) calc(16px + var(--safe-left));
}

.app-notice-stack {
  position: fixed;
  z-index: 70;
  top: calc(16px + var(--safe-top));
  left: 50%;
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: min(100vw - 32px - var(--safe-left) - var(--safe-right), 420px);
  transform: translateX(-50%);
  pointer-events: none;
}

.app-notice {
  pointer-events: auto;
  border-radius: 18px;
  padding: 14px 16px;
  box-shadow: 0 18px 40px -20px rgba(0,0,0,.6);
}

.app-notice-title {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.4;
}

.app-notice-copy {
  margin: 6px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--sub);
}

.app-notice-copy-subtle {
  opacity: 0.85;
}

.app-notice-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}

.app-notice-btn {
  border: 1px solid var(--card-border);
  border-radius: 999px;
  padding: 7px 12px;
  background: var(--field);
  color: var(--text);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.app-notice-btn:disabled {
  cursor: default;
  opacity: 0.55;
}

.app-notice-btn-primary {
  background: rgba(196,132,122,0.14);
  border-color: rgba(196,132,122,0.4);
  color: var(--accent);
}

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
