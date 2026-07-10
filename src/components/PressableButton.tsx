import { usePressable } from "bylgja";
import type {
  ButtonHTMLAttributes,
  MouseEventHandler,
  PointerEventHandler,
} from "react";

type PressableButtonProps = ButtonHTMLAttributes<HTMLButtonElement>;

export function PressableButton({
  className,
  onMouseDown,
  onMouseUp,
  onPointerCancel,
  onPointerDown,
  onPointerUp,
  ...props
}: PressableButtonProps) {
  const pressable = usePressable<HTMLButtonElement>({ className });

  const handleMouseDown: MouseEventHandler<HTMLButtonElement> = (event) => {
    pressable.onMouseDown(event);
    onMouseDown?.(event);
  };

  const handleMouseUp: MouseEventHandler<HTMLButtonElement> = (event) => {
    pressable.onMouseUp(event);
    onMouseUp?.(event);
  };

  const handlePointerCancel: PointerEventHandler<HTMLButtonElement> = (event) => {
    pressable.onPointerCancel(event);
    onPointerCancel?.(event);
  };

  const handlePointerDown: PointerEventHandler<HTMLButtonElement> = (event) => {
    pressable.onPointerDown(event);
    onPointerDown?.(event);
  };

  const handlePointerUp: PointerEventHandler<HTMLButtonElement> = (event) => {
    pressable.onPointerUp(event);
    onPointerUp?.(event);
  };

  return (
    <button
      {...props}
      ref={pressable.ref}
      className={pressable.className}
      onMouseDown={handleMouseDown}
      onMouseUp={handleMouseUp}
      onPointerCancel={handlePointerCancel}
      onPointerDown={handlePointerDown}
      onPointerUp={handlePointerUp}
    />
  );
}
