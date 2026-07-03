import type { ReactNode } from "react";
import type { Theme } from "../lib/theme";

interface ToolBtnProps {
  T: Theme;
  label: string;
  onClick: () => void;
  children: ReactNode;
  testId?: string;
}

export function ToolBtn({ T, label, onClick, children, testId }: ToolBtnProps) {
  return (
    <button
      title={label}
      data-testid={testId}
      className="p-2 rounded-xl hover:opacity-75 transition-opacity"
      style={{ color: T.text }}
      onClick={onClick}
    >
      {children}
    </button>
  );
}
