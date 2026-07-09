import { usePressable } from "bylgja";
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
  const pressable = usePressable<HTMLButtonElement>({
    className: "p-2 rounded-xl hover:opacity-75 transition-opacity disabled:cursor-not-allowed disabled:hover:opacity-45",
  });

  return (
    <button
      ref={pressable.ref}
      title={label}
      data-testid={testId}
      className={pressable.className}
      style={{ color: T.text, opacity: disabled ? 0.45 : 1 }}
      onMouseDown={pressable.onMouseDown}
      onMouseUp={pressable.onMouseUp}
      onClick={onClick}
      onPointerCancel={pressable.onPointerCancel}
      onPointerDown={pressable.onPointerDown}
      onPointerUp={pressable.onPointerUp}
      disabled={disabled}
    >
      {children}
    </button>
  );
}
