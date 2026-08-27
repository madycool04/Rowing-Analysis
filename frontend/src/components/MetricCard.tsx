import type { ReactNode } from "react";

interface MetricCardProps {
  title: string;
  available: boolean;
  unavailableReason?: string | null;
  children?: ReactNode;
}

export function MetricCard({ title, available, unavailableReason, children }: MetricCardProps) {
  return (
    <div className="metric-card">
      <p className="metric-card-title">{title}</p>
      {available ? (
        <div className="metric-card-body">{children}</div>
      ) : (
        <p className="metric-card-unavailable">
          {unavailableReason ?? "Not enough data to calculate this yet."}
        </p>
      )}
    </div>
  );
}

export function MetricRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="metric-row">
      <span className="metric-row-label">{label}</span>
      <span className="metric-row-value">{value}</span>
    </div>
  );
}
