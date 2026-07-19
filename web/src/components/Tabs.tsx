interface TabsProps {
  tabs: string[];
  active: string;
  onSelect: (tab: string) => void;
}

export function Tabs({ tabs, active, onSelect }: TabsProps) {
  return (
    <div role="tablist" aria-label="Dashboard sections" className="flex gap-1">
      {tabs.map((tab) => {
        const selected = tab === active;
        return (
          <button
            key={tab}
            role="tab"
            aria-selected={selected}
            onClick={() => onSelect(tab)}
            className="rounded-lg px-3 py-1.5 text-sm font-medium transition-colors"
            style={{
              background: selected ? "var(--surface-1)" : "transparent",
              color: selected ? "var(--text-primary)" : "var(--text-muted)",
              border: `1px solid ${selected ? "var(--border)" : "transparent"}`,
            }}
          >
            {tab}
          </button>
        );
      })}
    </div>
  );
}
