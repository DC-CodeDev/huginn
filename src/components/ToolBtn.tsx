import type { ReactNode } from "react";
import type { Theme } from "../lib/theme";

interface ToolBtnProps {
  T: Theme;
  label: string;
  onClick: () => void;
  children: ReactNode;
  testId?: string;
  disabled?: boolean;
}

export function ToolBtn({ T, label, onClick, children, testId, disabled = false }: ToolBtnProps) {
  return (
    <button
      title={label}
      data-testid={testId}
      className="p-2 rounded-xl hover:opacity-75 transition-opacity disabled:cursor-not-allowed disabled:hover:opacity-45"
      style={{ color: T.text, opacity: disabled ? 0.45 : 1 }}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  );
}
