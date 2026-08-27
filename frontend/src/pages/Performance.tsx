import { useEffect, useState } from "react";
import { analyticsApi, extractErrorMessage } from "../api/client";
import { Layout } from "../components/Layout";
import { LoadingState } from "../components/LoadingState";
import type { PerformanceMetrics } from "../types";
import { formatDate, formatDuration } from "../utils/format";

const DISTANCE_ORDER = ["500m", "1k", "2k", "5k", "6k", "10k"];
const DISTANCE_LABELS: Record<string, string> = {
  "500m": "500m",
  "1k": "1K",
  "2k": "2K",
  "5k": "5K",
  "6k": "6K",
  "10k": "10K",
};

export function Performance() {
  const [metrics, setMetrics] = useState<PerformanceMetrics | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    analyticsApi
      .performance()
      .then((res) => {
        if (cancelled) return;
        setMetrics(res.metrics);
        setStatus("ready");
      })
      .catch((err) => {
        if (cancelled) return;
        setError(extractErrorMessage(err, "Couldn't load your personal bests."));
        setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <Layout>
      <div className="page-header">
        <h1>Performance</h1>
        <p className="page-subtitle">Your personal bests across standard rowing distances.</p>
      </div>

      {status === "loading" && <LoadingState status="loading" loadingLabel="Loading personal bests..." />}
      {status === "error" && <LoadingState status="error" errorLabel={error ?? undefined} />}

      {status === "ready" && metrics && Object.keys(metrics.personal_bests).length === 0 && (
        <LoadingState
          status="empty"
          emptyTitle="No personal bests yet"
          emptyBody="Log a 500m, 1K, 2K, 5K, 6K, or 10K effort (as a full workout or an interval rep) to see it here."
        />
      )}

      {status === "ready" && metrics && (
        <div className="metric-grid">
          {DISTANCE_ORDER.filter((d) => metrics.personal_bests[d]).map((distance) => {
            const pb = metrics.personal_bests[distance];
            return (
              <div className="metric-card" key={distance}>
                <p className="metric-card-title">{DISTANCE_LABELS[distance]}</p>
                <p className="stat-card-value" style={{ fontSize: "1.6rem" }}>
                  {formatDuration(pb.current.duration_s)}
                </p>
                <p className="metric-note" style={{ borderTop: "none", paddingTop: 0 }}>
                  {pb.current.pace_display}/500m · {pb.current.avg_watts.toFixed(0)}W · {formatDate(pb.current.date)}
                </p>
                {pb.previous && (
                  <div className="metric-row">
                    <span className="metric-row-label">Previous</span>
                    <span className="metric-row-value">{formatDuration(pb.previous.duration_s)}</span>
                  </div>
                )}
                {pb.improvement_s != null && pb.improvement_s > 0 && (
                  <div className="metric-row">
                    <span className="metric-row-label">Improvement</span>
                    <span className="metric-row-value" style={{ color: "var(--color-accent)" }}>
                      -{pb.improvement_s.toFixed(1)}s
                    </span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </Layout>
  );
}
