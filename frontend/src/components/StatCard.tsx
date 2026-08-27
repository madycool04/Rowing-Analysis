interface StatCardProps {
  label: string;
  value: string;
  unit?: string;
  trend?: { direction: "up" | "down" | "flat"; label: string };
  tone?: "default" | "accent";
}

export function StatCard({ label, value, unit, trend, tone = "default" }: StatCardProps) {
  return (
    <div className={`stat-card${tone === "accent" ? " stat-card--accent" : ""}`}>
      <p className="stat-card-label">{label}</p>
      <p className="stat-card-value">
        {value}
        {unit && <span className="stat-card-unit">{unit}</span>}
      </p>
      {trend && (
        <p className={`stat-card-trend stat-card-trend--${trend.direction}`}>
          {trend.direction === "up" && "▲"}
          {trend.direction === "down" && "▼"}
          {trend.direction === "flat" && "–"} {trend.label}
        </p>
      )}
    </div>
  );
}
