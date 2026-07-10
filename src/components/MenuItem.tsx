import type { ReactNode } from "react";
import type { Theme } from "../lib/theme";
import { PressableButton } from "./PressableButton";

interface MenuItemProps {
  T: Theme;
  icon: ReactNode;
  label: string;
  onClick: () => void;
}

export function MenuItem({ T, icon, label, onClick }: MenuItemProps) {
  return (
    <PressableButton
      className="flex items-center gap-2 w-full px-3 py-2 text-left hover:opacity-75"
      style={{ color: T.text }}
      onClick={onClick}
    >
      <span style={{ color: T.sub }}>{icon}</span>{label}
    </PressableButton>
  );
}
