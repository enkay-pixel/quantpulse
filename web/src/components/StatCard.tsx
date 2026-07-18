interface StatCardProps {
  label: string;
  value: string;
  valueColor?: string;
  sub?: string;
}

export function StatCard({ label, value, valueColor, sub }: StatCardProps) {
  return (
    <div className="card px-4 py-3">
      <div className="text-xs font-medium uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
        {label}
      </div>
      <div className="mt-1 text-2xl font-semibold" style={{ color: valueColor ?? "var(--text-primary)" }}>
        {value}
      </div>
      {sub ? (
        <div className="mt-0.5 text-xs" style={{ color: "var(--text-secondary)" }}>
          {sub}
        </div>
      ) : null}
    </div>
  );
}
