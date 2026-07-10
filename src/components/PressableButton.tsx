import { Tooltip, usePressable } from "bylgja";
import type {
  ButtonHTMLAttributes,
  MouseEventHandler,
  PointerEventHandler,
  ReactNode,
} from "react";

type PressableButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  tooltip?: ReactNode;
};

export function PressableButton({
  className,
  onMouseDown,
  onMouseUp,
  onPointerCancel,
  onPointerDown,
  onPointerUp,
  tooltip,
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

  const button = (
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

  return tooltip ? (
    <Tooltip content={tooltip} openDelay={350} closeDelay={80} placement="top" viewportPadding={12}>
      {button}
    </Tooltip>
  ) : button;
}
