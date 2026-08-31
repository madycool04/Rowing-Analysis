import type { ReactNode } from "react";

type MetricCardProps = {
  title: ReactNode;
  available: boolean;
  unavailableReason?: string;
  children: ReactNode;
};

export function MetricCard({
  title,
  available,
  unavailableReason,
  children,
}: MetricCardProps) {
  return (
    <div className="card metric-card">
      <p className="card-title">{title}</p>

      {available ? (
        children
      ) : (
        <p className="metric-unavailable">
          {unavailableReason ?? "Not enough data available."}
        </p>
      )}
    </div>
  );
}

export function MetricRow({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="metric-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}