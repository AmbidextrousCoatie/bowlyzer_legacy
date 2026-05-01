import { useState } from "react";

type TooltipState = {
  visible: boolean;
  x: number;
  y: number;
  content: string;
  cellKey: string;
};

const initialState: TooltipState = {
  visible: false,
  x: 0,
  y: 0,
  content: "",
  cellKey: "",
};

export function useHoverTooltip() {
  const [tooltip, setTooltip] = useState<TooltipState>(initialState);

  function onEnter(e: React.MouseEvent<HTMLElement>, content: string, cellKey: string) {
    setTooltip({
      visible: true,
      x: e.clientX + 12,
      y: e.clientY + 12,
      content,
      cellKey,
    });
  }

  function onMove(e: React.MouseEvent<HTMLElement>) {
    setTooltip((prev) => (prev.visible ? { ...prev, x: e.clientX + 12, y: e.clientY + 12 } : prev));
  }

  function onLeave() {
    setTooltip((prev) => ({ ...prev, visible: false, cellKey: "" }));
  }

  return { tooltip, onEnter, onMove, onLeave };
}
