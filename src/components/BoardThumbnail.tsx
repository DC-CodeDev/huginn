import type { ReactNode } from "react";

function hashId(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return h;
}

export interface BoardThumbnailProps {
  boardId: string;
  nodeCount: number;
  edgeCount: number;
}

const BG: React.CSSProperties = {
  flex: "1 1 0",
  background: "var(--field)",
  backgroundImage: "radial-gradient(rgba(255,255,255,0.025) 1.5px, transparent 1.5px)",
  backgroundSize: "22px 22px",
  padding: "12px 10px",
  overflow: "hidden",
};

function N(x: number, y: number, w: number, h: number, accent: boolean): ReactNode {
  return (
    <rect
      x={x} y={y} width={w} height={h} rx={7}
      fill={accent ? "var(--accent)" : "var(--card)"}
      fillOpacity={accent ? 0.1 : 1}
      stroke={accent ? "var(--accent)" : "var(--card-border)"}
      strokeOpacity={accent ? 0.32 : 1}
      strokeWidth={1.5}
    />
  );
}

function E(d: string, show: boolean): ReactNode {
  if (!show) return null;
  return <path d={d} stroke="var(--sub)" strokeWidth={1.2} strokeOpacity={0.5} />;
}

export function BoardThumbnail({ boardId, nodeCount, edgeCount }: BoardThumbnailProps) {
  const seed = hashId(boardId);
  const hasEdges = edgeCount > 0;
  const accentIdx = seed % 3;

  const svg = (children: ReactNode) => (
    <div style={BG}>
      <svg viewBox="0 0 260 120" fill="none" style={{ width: "100%", height: "100%" }}>
        {children}
      </svg>
    </div>
  );

  // Empty board
  if (nodeCount === 0) {
    return svg(
      <rect x="80" y="40" width="100" height="40" rx="8"
        fill="none" stroke="var(--card-border)" strokeWidth="1.5" strokeDasharray="6 3" />
    );
  }

  // Single node
  if (nodeCount === 1) {
    return svg(N(76, 34, 108, 52, false));
  }

  // Two nodes
  if (nodeCount === 2) {
    return svg(<>
      {N(14, 38, 96, 44, accentIdx === 0)}
      {N(150, 38, 96, 44, accentIdx !== 0)}
      {E("M110 60 L150 60", hasEdges)}
    </>);
  }

  // 3+ nodes: 4 layout variants
  const a = (i: number) => accentIdx === i;

  switch (seed % 4) {
    case 0: // 1 left, 2 stacked right
      return svg(<>
        {N(14, 32, 92, 56, a(0))}
        {N(154, 12, 90, 40, a(1))}
        {N(154, 66, 90, 40, a(2))}
        {E("M106 50 C130 50 130 32 154 32", hasEdges)}
        {E("M106 70 C130 70 130 86 154 86", hasEdges)}
      </>);

    case 1: // horizontal chain
      return svg(<>
        {N(8, 40, 72, 40, a(0))}
        {N(94, 40, 72, 40, a(1))}
        {N(180, 40, 72, 40, a(2))}
        {E("M80 60 L94 60", hasEdges)}
        {E("M166 60 L180 60", hasEdges)}
      </>);

    case 2: // top feeds 2 below
      return svg(<>
        {N(84, 8, 92, 36, a(0))}
        {N(14, 70, 100, 40, a(1))}
        {N(146, 70, 100, 40, a(2))}
        {E("M114 44 C78 44 78 70 64 70", hasEdges)}
        {E("M146 44 C182 44 182 70 196 70", hasEdges)}
      </>);

    default: // diagonal chain
      return svg(<>
        {N(8, 14, 82, 38, a(0))}
        {N(89, 62, 82, 38, a(1))}
        {N(170, 14, 82, 38, a(2))}
        {E("M90 33 C130 33 70 81 89 81", hasEdges)}
        {E("M171 81 C191 81 191 33 170 33", hasEdges)}
      </>);
  }
}
