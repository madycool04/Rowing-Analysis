import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { coachApi, extractErrorMessage } from "../api/client";
import { Layout } from "../components/Layout";
import { LoadingState } from "../components/LoadingState";
import { PaceChart } from "../components/PaceChart";
import { StatCard } from "../components/StatCard";
import type {
  Athlete,
  PerformanceMetrics,
  PredictionResponse,
  TrainingLoadMetrics,
  TrendsMetrics,
  WorkoutListItem,
} from "../types";
import { formatDate, formatDistance, formatDuration } from "../utils/format";

export function CoachAthlete() {
  const { athleteId } = useParams<{ athleteId: string }>();
  const navigate = useNavigate();
  const id = Number(athleteId);
  const [athlete, setAthlete] = useState<Athlete | null>(null);
  const [workouts, setWorkouts] = useState<WorkoutListItem[]>([]);
  const [performance, setPerformance] = useState<PerformanceMetrics | null>(null);
  const [load, setLoad] = useState<TrainingLoadMetrics | null>(null);
  const [trends, setTrends] = useState<TrendsMetrics | null>(null);
  const [prediction, setPrediction] = useState<PredictionResponse | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    if (!Number.isFinite(id)) return;
    Promise.all([
      coachApi.athlete(id),
      coachApi.workouts(id, 1, 100),
      coachApi.performance(id),
      coachApi.trainingLoad(id),
      coachApi.trends(id),
      coachApi.prediction(id),
    ]).then(([a, w, p, l, t, pred]) => {
      setAthlete(a);
      setWorkouts(w.items);
      setPerformance(p.metrics);
      setLoad(l.metrics);
      setTrends(t.metrics);
      setPrediction(pred);
      setStatus("ready");
    }).catch((err) => {
      setError(extractErrorMessage(err, "Couldn't load this athlete."));
      setStatus("error");
    });
  }, [id]);

  const totals = useMemo(() => ({
    distance: workouts.reduce((sum, w) => sum + w.total_distance_m, 0),
    duration: workouts.reduce((sum, w) => sum + w.total_duration_s, 0),
  }), [workouts]);

  async function downloadReport() {
    setDownloading(true);
    try {
      await coachApi.downloadReport(id);
    } catch (err) {
      setError(extractErrorMessage(err, "Couldn't generate the report."));
    } finally {
      setDownloading(false);
    }
  }

  if (status === "loading") return <Layout><LoadingState status="loading" loadingLabel="Loading athlete..." /></Layout>;
  if (status === "error" || !athlete) return <Layout><LoadingState status="error" errorLabel={error ?? "Athlete not found."} /></Layout>;

  const pbs = performance?.personal_bests ?? {};
  const latestLoad = load?.daily_series.at(-1);
  const latestWatts = trends?.avg_watts.at(-1);
  const twoKProgression = (trends?.performance_2k ?? []).map((point) => ({
    date: formatDate(point.date),
    value: point.duration_s,
  }));
  const powerTrend = (trends?.avg_watts ?? []).slice(-12).map((point) => ({
    date: formatDate(point.date),
    value: point.avg_watts,
  }));
  const loadTrend = (load?.daily_series ?? []).slice(-28).map((point) => ({
    date: formatDate(point.date),
    value: point.rolling_7_day,
  }));

  return (
    <Layout>
      <div className="page-header coach-page-header">
        <div>
          <button className="btn-link" onClick={() => navigate("/coach")} type="button">Back to athletes</button>
          <h1>{athlete.name}</h1>
          <p className="page-subtitle">Read-only athlete overview and training analytics.</p>
        </div>
        <button className="btn-primary" onClick={downloadReport} disabled={downloading} type="button">
          {downloading ? "Generating..." : "Export Athlete Report"}
        </button>
      </div>
      {error && <div className="auth-error" style={{ marginTop: "1rem" }}>{error}</div>}

      <div className="stat-grid">
        <StatCard label="Workouts" value={String(workouts.length)} />
        <StatCard label="Recorded distance" value={formatDistance(totals.distance)} />
        <StatCard label="Recorded time" value={formatDuration(totals.duration)} />
        <StatCard label="Latest watts" value={latestWatts ? latestWatts.avg_watts.toFixed(0) : "-"} unit={latestWatts ? "W" : ""} />
        <StatCard label="7-day load" value={latestLoad ? latestLoad.rolling_7_day.toFixed(0) : "-"} />
        <StatCard label="2K prediction" value={prediction?.available && prediction.predicted_time_s ? formatDuration(prediction.predicted_time_s) : "-"} />
      </div>

      <div className="metric-grid">
        <div className="card">
          <p className="card-title">Athlete Profile</p>
          <Info label="Training level" value={athlete.training_level ?? "Not set"} />
          <Info label="Weight" value={athlete.weight_kg ? `${athlete.weight_kg} kg` : "Not set"} />
          <Info label="Resting / max HR" value={athlete.resting_hr && athlete.max_hr ? `${athlete.resting_hr} / ${athlete.max_hr} bpm` : "Not set"} />
        </div>
        <div className="card">
          <p className="card-title">Personal Bests</p>
          {Object.keys(pbs).length === 0 && <p className="metric-card-unavailable">No qualifying PBs yet.</p>}
          {Object.entries(pbs).map(([distance, pb]) => (
            <Info key={distance} label={distance.toUpperCase()} value={`${formatDuration(pb.current.duration_s)} (${pb.current.pace_display}/500m)`} />
          ))}
        </div>
        <div className="card">
          <p className="card-title">Prediction</p>
          <Info label="Estimate" value={prediction?.available && prediction.predicted_time_s ? formatDuration(prediction.predicted_time_s) : "Unavailable"} />
          <Info label="Confidence" value={prediction?.confidence ?? "-"} />
          <Info label="Method" value={prediction?.method_used?.replaceAll("_", " ") ?? "-"} />
          {prediction?.note && <p className="metric-note">{prediction.note}</p>}
        </div>
      </div>

      <div className="metric-grid">
        <div className="card">
          <p className="card-title">2K Progression</p>
          {twoKProgression.length > 1 ? (
            <PaceChart data={twoKProgression} formatValue={formatDuration} />
          ) : <p className="metric-card-unavailable">At least two recorded 2K efforts are needed.</p>}
        </div>
        <div className="card">
          <p className="card-title">Recent Power Trend</p>
          {powerTrend.length > 1 ? (
            <PaceChart data={powerTrend} invertY={false} color="#e0a94a" formatValue={(value) => `${value.toFixed(0)}W`} />
          ) : <p className="metric-card-unavailable">Not enough workouts for a power trend.</p>}
        </div>
        <div className="card">
          <p className="card-title">7-Day Training Load</p>
          {loadTrend.length > 1 ? (
            <PaceChart data={loadTrend} invertY={false} color="#8f6ad8" formatValue={(value) => value.toFixed(0)} />
          ) : <p className="metric-card-unavailable">Not enough load data for a trend.</p>}
        </div>
      </div>

      <div className="card" style={{ marginTop: "1rem" }}>
        <p className="card-title">Workout History</p>
        {workouts.length === 0 ? <p className="metric-card-unavailable">No workouts recorded.</p> : (
          <div className="table-scroll"><table className="data-table">
            <thead><tr><th>Date</th><th>Workout</th><th>Distance</th><th>Time</th><th>Pace</th><th>Watts</th><th>HR</th></tr></thead>
            <tbody>{workouts.map((w) => (
              <tr key={w.id} className="clickable" onClick={() => navigate(`/coach/athletes/${id}/workouts/${w.id}`)}>
                <td>{formatDate(w.date)}</td><td className="data-table-text">{w.title}</td><td>{formatDistance(w.total_distance_m)}</td>
                <td>{formatDuration(w.total_duration_s)}</td><td>{w.avg_pace_display}</td><td>{w.avg_watts.toFixed(0)}W</td><td>{w.avg_hr ? `${w.avg_hr.toFixed(0)} bpm` : "-"}</td>
              </tr>
            ))}</tbody>
          </table></div>
        )}
      </div>
    </Layout>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return <div className="metric-row"><span className="metric-row-label">{label}</span><span className="metric-row-value">{value}</span></div>;
}
