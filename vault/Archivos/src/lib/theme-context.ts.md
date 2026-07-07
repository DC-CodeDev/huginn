import { createContext, useContext } from "react";
import type { Theme } from "./theme";

export interface ThemeCtx {
  theme: string;
  T: Theme;
  toggleTheme: () => void;
}

export const ThemeContext = createContext<ThemeCtx>({
  theme: "dark",
  T: { bg: "#0F1117", dot: "#0A0C10", card: "#161923", cardBorder: "#242938", field: "#0C0E14", fieldBorder: "#1E2230", text: "#E8EBF0", sub: "#8A90A3" },
  toggleTheme: () => {},
});

export const useTheme = () => useContext(ThemeContext);
