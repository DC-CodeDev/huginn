/* ------------------------------------------------------------------ */
/*  Tema visual del canvas                                             */
/* ------------------------------------------------------------------ */

export interface Theme {
  bg: string;
  dot: string;
  card: string;
  cardBorder: string;
  field: string;
  fieldBorder: string;
  text: string;
  sub: string;
}

export const THEMES: Record<string, Theme> = {
  dark: {
    bg: "#0F1117",
    dot: "#0A0C10",          // dots levemente más oscuros que el fondo
    card: "#161923",
    cardBorder: "#242938",
    field: "#0C0E14",
    fieldBorder: "#1E2230",
    text: "#E8EBF0",
    sub: "#8A90A3",
  },
  light: {
    bg: "#E8EBF0",
    dot: "#DCE0E9",
    card: "#FFFFFF",
    cardBorder: "#D6DBE6",
    field: "#EEF0F6",
    fieldBorder: "#DCE0EA",
    text: "#0F1117",
    sub: "#5B6172",
  },
};
