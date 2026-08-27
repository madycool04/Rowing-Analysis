import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { analyticsApi, extractErrorMessage } from "../api/client";
import { Layout } from "../components/Layout";
import { LoadingState } from "../components/LoadingState";
import { StatCard } from "../components/StatCard";
import type { TrainingLoadMetrics } from "../types";
import { formatDateShort } from "../utils/format";

const chartTooltipStyle = {
  contentStyle: { background: "#1a1f2e", border: "1px solid #262c3d", borderRadius: 8, fontSize: 13 },
  labelStyle: { color: "#8b93a7" },
};

export function TrainingLoad() {
  const [metrics, setMetrics] = useState<TrainingLoadMetrics | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    analyticsApi
      .trainingLoad()
      .then((res) => {
        if (cancelled) return;
        setMetrics(res.metrics);
        setStatus("ready");
      })
      .catch((err) => {
        if (cancelled) return;
        setError(extractErrorMessage(err, "Couldn't load training load data."));
        setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (status === "loading") {
    return (
      <Layout>
        <LoadingState status="loading" loadingLabel="Loading training load..." />
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

  if (metrics.daily_series.length === 0) {
    return (
      <Layout>
        <div className="page-header">
          <h1>Training Load</h1>
        </div>
        <LoadingState
          status="empty"
          emptyTitle="No training load data yet"
          emptyBody="Log a few workouts to start tracking your training load."
        />
      </Layout>
    );
  }

  const series = metrics.daily_series;
  const latest = series[series.length - 1];
  const chartData = series.map((d) => ({ ...d, dateLabel: formatDateShort(d.date) }));

  return (
    <Layout>
      <div className="page-header">
        <h1>Training Load</h1>
        <p className="page-subtitle">
          A descriptive measure of training volume - not a medical or injury-risk assessment.
        </p>
      </div>

      <div className="stat-grid">
        <StatCard label="Today's Load" value={latest.daily_load.toFixed(0)} tone="accent" />
        <StatCard label="7-Day Rolling" value={latest.rolling_7_day.toFixed(0)} />
        <StatCard label="28-Day Rolling" value={latest.rolling_28_day.toFixed(0)} />
        <StatCard label="Acute:Chronic Ratio" value={latest.acwr != null ? latest.acwr.toFixed(2) : "—"} />
      </div>

      <div className="card">
        <p className="card-title">Daily Load</p>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#262c3d" vertical={false} />
            <XAxis dataKey="dateLabel" tick={{ fill: "#8b93a7", fontSize: 11 }} axisLine={{ stroke: "#262c3d" }} tickLine={false} />
            <YAxis tick={{ fill: "#8b93a7", fontSize: 12 }} axisLine={false} tickLine={false} width={40} />
            <Tooltip {...chartTooltipStyle} />
            <Bar dataKey="daily_load" fill="#3ddc97" radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="card">
        <p className="card-title">Rolling Load (7-day vs 28-day)</p>
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#262c3d" vertical={false} />
            <XAxis dataKey="dateLabel" tick={{ fill: "#8b93a7", fontSize: 11 }} axisLine={{ stroke: "#262c3d" }} tickLine={false} />
            <YAxis tick={{ fill: "#8b93a7", fontSize: 12 }} axisLine={false} tickLine={false} width={40} />
            <Tooltip {...chartTooltipStyle} />
            <Line type="monotone" dataKey="rolling_7_day" stroke="#3ddc97" strokeWidth={2} dot={false} name="7-day" />
            <Line type="monotone" dataKey="rolling_28_day" stroke="#4f6a8f" strokeWidth={2} dot={false} name="28-day" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <p className="metric-note">
        Acute:chronic workload ratio (ACWR) compares recent training volume to your longer-term
        baseline. It's shown here as descriptive information only - it is not a medical assessment
        and does not predict injury risk.
      </p>
    </Layout>
  );
}
