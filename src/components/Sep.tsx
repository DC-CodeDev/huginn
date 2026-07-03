import type { Theme } from "../lib/theme";

export function Sep({ T }: { T: Theme }) {
  return <span className="w-px h-5 mx-1" style={{ background: T.cardBorder }} />;
}
