import { useEffect, useState } from "react";
import { analyticsApi, extractErrorMessage } from "../api/client";
import { Layout } from "../components/Layout";
import { LoadingState } from "../components/LoadingState";
import { PaceChart } from "../components/PaceChart";
import { WorkoutChart } from "../components/WorkoutChart";
import type { TrendsMetrics } from "../types";
import { formatDateShort, formatDuration } from "../utils/format";

export function Trends() {
  const [metrics, setMetrics] = useState<TrendsMetrics | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    analyticsApi
      .trends()
      .then((res) => {
        if (cancelled) return;
        setMetrics(res.metrics);
        setStatus("ready");
      })
      .catch((err) => {
        if (cancelled) return;
        setError(extractErrorMessage(err, "Couldn't load trends."));
        setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (status === "loading") {
    return (
      <Layout>
        <LoadingState status="loading" loadingLabel="Loading trends..." />
      </Layout>
    );
  }
  if (status === "error" || !metrics) {
    return (
      <Layout>
        <LoadingState status="error" errorLabel={error ?? undefined} />
      </Layout>
    );
  }

  const hasAnyData = metrics.avg_watts.length > 0;
  if (!hasAnyData) {
    return (
      <Layout>
        <div className="page-header">
          <h1>Trends</h1>
        </div>
        <LoadingState status="empty" emptyTitle="Not enough data yet" emptyBody="Log more workouts to see trends over time." />
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="page-header">
        <h1>Trends</h1>
        <p className="page-subtitle">How your training has changed over time.</p>
      </div>

      {metrics.performance_2k.length >= 2 && (
        <div className="card">
          <p className="card-title">2K Performance Over Time</p>
          <PaceChart
            data={metrics.performance_2k.map((p) => ({ date: formatDateShort(p.date), value: p.duration_s }))}
            formatValue={formatDuration}
          />
        </div>
      )}

      {metrics.performance_5k.length >= 2 && (
        <div className="card">
          <p className="card-title">5K Performance Over Time</p>
          <PaceChart
            data={metrics.performance_5k.map((p) => ({ date: formatDateShort(p.date), value: p.duration_s }))}
            formatValue={formatDuration}
          />
        </div>
      )}

      <div className="metric-grid">
        <div className="card">
          <p className="card-title">Average Watts</p>
          <WorkoutChart
            data={metrics.avg_watts.map((p) => ({ splitLabel: formatDateShort(p.date), value: p.avg_watts }))}
            color="#e0a94a"
            unit="W"
          />
        </div>

        {metrics.avg_hr.length > 0 && (
          <div className="card">
            <p className="card-title">Average Heart Rate</p>
            <WorkoutChart
              data={metrics.avg_hr.map((p) => ({ splitLabel: formatDateShort(p.date), value: p.avg_hr }))}
              color="#e0575b"
              unit="bpm"
            />
          </div>
        )}

        {metrics.efficiency_factor.length > 0 && (
          <div className="card">
            <p className="card-title">Efficiency Factor</p>
            <WorkoutChart
              data={metrics.efficiency_factor.map((p) => ({ splitLabel: formatDateShort(p.date), value: p.efficiency_factor }))}
              color="#3ddc97"
            />
          </div>
        )}

        {metrics.pacing_consistency.length > 0 && (
          <div className="card">
            <p className="card-title">Pacing Consistency (CV)</p>
            <WorkoutChart
              data={metrics.pacing_consistency.map((p) => ({ splitLabel: formatDateShort(p.date), value: p.pacing_cv_pct }))}
              color="#4f6a8f"
              unit="%"
              invertY
            />
          </div>
        )}

        {metrics.interval_decay.length > 0 && (
          <div className="card">
            <p className="card-title">Interval Decay Slope</p>
            <WorkoutChart
              data={metrics.interval_decay.map((p) => ({ splitLabel: formatDateShort(p.date), value: p.slope_watts_per_interval }))}
              color="#e0a94a"
              unit="W/interval"
            />
          </div>
        )}

        {metrics.training_load.length > 0 && (
          <div className="card">
            <p className="card-title">Training Load (7-day rolling)</p>
            <WorkoutChart
              data={metrics.training_load.map((p) => ({ splitLabel: formatDateShort(p.date), value: p.rolling_7_day }))}
              color="#3ddc97"
            />
          </div>
        )}
      </div>
    </Layout>
  );
}
