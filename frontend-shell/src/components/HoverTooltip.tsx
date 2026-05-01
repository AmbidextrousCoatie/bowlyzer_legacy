type Props = {
  visible: boolean;
  x: number;
  y: number;
  content: string;
};

export default function HoverTooltip({ visible, x, y, content }: Props) {
  if (!visible) return null;
  return (
    <div
      className="heatTooltip"
      style={{
        left: x,
        top: y,
      }}
    >
      {content}
    </div>
  );
}
