import type { ReactNode } from "react";
import type { Theme } from "../lib/theme";

interface MiniBtnProps {
  T: Theme;
  children: ReactNode;
  onClick: () => void;
}

export function MiniBtn({ T, children, onClick }: MiniBtnProps) {
  return (
    <button className="text-[10px] rounded-md px-1.5 py-0.5 hover:opacity-75"
      style={{ background: T.card, border: `1px solid ${T.fieldBorder}`, color: T.sub }} onClick={onClick}>
      {children}
    </button>
  );
}
