import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { analyticsApi, extractErrorMessage, workoutsApi } from "../api/client";
import { Layout } from "../components/Layout";
import { LoadingState } from "../components/LoadingState";
import { PaceChart } from "../components/PaceChart";
import { StatCard } from "../components/StatCard";
import { useAuth } from "../context/AuthContext";
import type { PerformanceMetrics, TrainingLoadMetrics, TrendsMetrics, WorkoutListItem } from "../types";
import { categoryBadgeClass, categoryLabel, formatDate, formatDistance, formatDuration } from "../utils/format";

type LoadState = "loading" | "ready" | "error" | "empty";

export function Dashboard() {
  const { athlete } = useAuth();
  const navigate = useNavigate();

  const [state, setState] = useState<LoadState>("loading");
  const [error, setError] = useState<string | null>(null);
  const [recentWorkouts, setRecentWorkouts] = useState<WorkoutListItem[]>([]);
  const [performance, setPerformance] = useState<PerformanceMetrics | null>(null);
  const [trainingLoad, setTrainingLoad] = useState<TrainingLoadMetrics | null>(null);
  const [trends, setTrends] = useState<TrendsMetrics | null>(null);
  const [allWorkouts, setAllWorkouts] = useState<WorkoutListItem[]>([]);

  useEffect(() => {
    let cancelled = false;

    Promise.all([
      workoutsApi.list({ page: 1, page_size: 5, sort: "newest" }),
      workoutsApi.list({ page: 1, page_size: 100, sort: "newest" }),
      analyticsApi.performance(),
      analyticsApi.trainingLoad(),
      analyticsApi.trends(),
    ])
      .then(([workoutsRes, allRes, perfRes, loadRes, trendsRes]) => {
        if (cancelled) return;
        setRecentWorkouts(workoutsRes.items);
        setAllWorkouts(allRes.items);
        setPerformance(perfRes.metrics);
        setTrainingLoad(loadRes.metrics);
        setTrends(trendsRes.metrics);
        setState(workoutsRes.total === 0 ? "empty" : "ready");
      })
      .catch((err) => {
        if (cancelled) return;
        setError(extractErrorMessage(err, "Couldn't load your dashboard."));
        setState("error");
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const weeklyLoad = trainingLoad?.daily_series.at(-1)?.rolling_7_day;
  const pb2k = performance?.personal_bests["2k"];
  const pb5k = performance?.personal_bests["5k"];
  const pb6k = performance?.personal_bests["6k"];
  const pb10k = performance?.personal_bests["10k"];

  const now = new Date();
  const weekStart = new Date(now); weekStart.setDate(now.getDate() - ((now.getDay() + 6) % 7)); weekStart.setHours(0,0,0,0);
  const monthStart = new Date(now.getFullYear(), now.getMonth(), 1);
  const week = allWorkouts.filter(w => new Date(w.date) >= weekStart);
  const month = allWorkouts.filter(w => new Date(w.date) >= monthStart);
  const sumDistance = (xs: WorkoutListItem[]) => xs.reduce((a,w)=>a+w.total_distance_m,0);
  const sumTime = (xs: WorkoutListItem[]) => xs.reduce((a,w)=>a+w.total_duration_s,0);
  const insights: string[] = [];
  if ((trends?.avg_watts?.length ?? 0) >= 4) { const a=trends!.avg_watts.slice(-4); const first=a.slice(0,2).reduce((x,p)=>x+p.avg_watts,0)/2; const last=a.slice(-2).reduce((x,p)=>x+p.avg_watts,0)/2; if (last>first*1.02) insights.push(`Average watts are up ${((last/first-1)*100).toFixed(1)}% across your latest four workouts.`); }
  if ((trends?.avg_hr?.length ?? 0) >= 4 && (trends?.avg_watts?.length ?? 0) >= 4) insights.push("Keep an eye on heart rate alongside power to spot changes in cardiovascular response.");

  const progression2k = (trends?.performance_2k ?? []).map((p) => ({
    date: formatDate(p.date),
    value: p.duration_s,
  }));

  return (
    <Layout>
      <div className="page-header">
        <h1>Welcome back{athlete ? `, ${athlete.name}` : ""}</h1>
        <p className="page-subtitle">Here's how your training is shaping up.</p>
      </div>

      {state === "loading" && <LoadingState status="loading" loadingLabel="Loading your dashboard..." />}
      {state === "error" && <LoadingState status="error" errorLabel={error ?? undefined} />}

      {state === "empty" && (
        <LoadingState
          status="empty"
          emptyTitle="No workouts yet"
          emptyBody="Upload a Concept2 CSV or log a workout manually to see your analytics here."
          emptyAction={
            <button className="btn-primary" onClick={() => navigate("/upload")}>
              Add your first workout
            </button>
          }
        />
      )}

      {state === "ready" && (
        <>
          <div className="stat-grid">
            <StatCard label="Current 2K PB" value={pb2k?.current.pace_display ?? "—"} unit={pb2k ? "/500m" : ""} tone="accent" />
            <StatCard label="Best 5K" value={pb5k?.current.pace_display ?? "—"} unit={pb5k ? "/500m" : ""} />
            <StatCard label="Best 6K" value={pb6k?.current.pace_display ?? "—"} unit={pb6k ? "/500m" : ""} />
            <StatCard label="Best 10K" value={pb10k?.current.pace_display ?? "—"} unit={pb10k ? "/500m" : ""} />
            <StatCard
              label="Weekly Training Load"
              value={weeklyLoad !== undefined ? weeklyLoad.toFixed(0) : "—"}
            />
          </div>

          <div className="metric-grid">
            <div className="card"><p className="card-title">Training Summary</p><StatLine label="This week" value={`${formatDistance(sumDistance(week))} · ${week.length} workouts`} /><StatLine label="This month" value={`${formatDistance(sumDistance(month))} · ${month.length} workouts`} /><StatLine label="Training time" value={formatDuration(sumTime(month))} /></div>
            <div className="card"><p className="card-title">Insights</p>{insights.length ? <ul className="insight-list">{insights.map((x,i)=><li key={i}>{x}</li>)}</ul> : <p className="metric-card-unavailable">Not enough recent data for a reliable trend insight.</p>}</div>
          </div>

          <div className="metric-grid">
            <div className="card">
              <p className="card-title">2K Progression</p>
              {progression2k.length >= 2 ? (
                <PaceChart data={progression2k} formatValue={(v) => formatDuration(v)} />
              ) : (
                <p className="metric-card-unavailable">
                  Log a few more 2K efforts to see your progression here.
                </p>
              )}
            </div>

            <div className="card">
              <p className="card-title">Recent Workouts</p>
              <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Workout</th>
                    <th>Distance</th>
                    <th>Time</th>
                    <th>Pace</th>
                  </tr>
                </thead>
                <tbody>
                  {recentWorkouts.map((w) => (
                    <tr key={w.id} className="clickable" onClick={() => navigate(`/workouts/${w.id}`)}>
                      <td className="data-table-text">{formatDate(w.date)}</td>
                      <td className="data-table-text">
                        {w.title} <span className={categoryBadgeClass(w.category)}>{categoryLabel(w.category)}</span>
                      </td>
                      <td>{formatDistance(w.total_distance_m)}</td>
                      <td>{formatDuration(w.total_duration_s)}</td>
                      <td>{w.avg_pace_display}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            </div>
          </div>
        </>
      )}
    </Layout>
  );
}

function StatLine({label,value}:{label:string;value:string}){return <div style={{display:"flex",justifyContent:"space-between",gap:16,margin:"10px 0"}}><span>{label}</span><strong>{value}</strong></div>}
