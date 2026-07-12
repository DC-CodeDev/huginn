interface SectionHeaderProps {
  title: string;
  action?: React.ReactNode;
}

export function SectionHeader({ title, action }: SectionHeaderProps) {
  return (
    <div className="flex items-center gap-3" style={{ marginBottom: 20 }}>
      <span
        style={{
          fontFamily: "'JetBrains Mono', ui-monospace, monospace",
          fontSize: 10, fontWeight: 500,
          letterSpacing: "0.14em", textTransform: "uppercase",
          color: "var(--sub)", whiteSpace: "nowrap", flexShrink: 0,
        }}
      >
        {title}
      </span>
      <div style={{ flex: 1, height: 1, background: "var(--card-border)" }} />
      {action && <div style={{ flexShrink: 0 }}>{action}</div>}
    </div>
  );
}
