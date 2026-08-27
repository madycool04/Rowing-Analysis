import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { extractErrorMessage, workoutsApi, type WorkoutListParams } from "../api/client";
import { Layout } from "../components/Layout";
import { LoadingState } from "../components/LoadingState";
import type { WorkoutListItem } from "../types";
import { categoryBadgeClass, categoryLabel, formatDate, formatDistance, formatDuration } from "../utils/format";

const PAGE_SIZE = 15;

const SORT_OPTIONS: { value: NonNullable<WorkoutListParams["sort"]>; label: string }[] = [
  { value: "newest", label: "Newest first" },
  { value: "oldest", label: "Oldest first" },
  { value: "fastest", label: "Fastest pace" },
  { value: "longest", label: "Longest duration" },
];

export function History() {
  const navigate = useNavigate();
  const [items, setItems] = useState<WorkoutListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState<NonNullable<WorkoutListParams["sort"]>>("newest");
  const [hasHrFilter, setHasHrFilter] = useState<boolean | undefined>(undefined);
  const [hasSplitsFilter, setHasSplitsFilter] = useState<boolean | undefined>(undefined);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    workoutsApi
      .list({ page, page_size: PAGE_SIZE, sort, has_hr: hasHrFilter, has_splits: hasSplitsFilter })
      .then((res) => {
        if (cancelled) return;
        setItems(res.items);
        setTotal(res.total);
        setStatus("ready");
      })
      .catch((err) => {
        if (cancelled) return;
        setError(extractErrorMessage(err, "Couldn't load workout history."));
        setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [page, sort, hasHrFilter, hasSplitsFilter]);

  const totalPages = Math.max(Math.ceil(total / PAGE_SIZE), 1);

  return (
    <Layout>
      <div className="page-header">
        <h1>History</h1>
        <p className="page-subtitle">Every workout you've logged, in one place.</p>
      </div>

      <div className="filter-row">
        <select className="select" value={sort} onChange={(e) => { setSort(e.target.value as typeof sort); setPage(1); }}>
          {SORT_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <select
          className="select"
          value={hasHrFilter === undefined ? "any" : hasHrFilter ? "yes" : "no"}
          onChange={(e) => {
            const v = e.target.value;
            setHasHrFilter(v === "any" ? undefined : v === "yes");
            setPage(1);
          }}
        >
          <option value="any">HR: any</option>
          <option value="yes">HR: available</option>
          <option value="no">HR: unavailable</option>
        </select>
        <select
          className="select"
          value={hasSplitsFilter === undefined ? "any" : hasSplitsFilter ? "yes" : "no"}
          onChange={(e) => {
            const v = e.target.value;
            setHasSplitsFilter(v === "any" ? undefined : v === "yes");
            setPage(1);
          }}
        >
          <option value="any">Splits: any</option>
          <option value="yes">Splits: available</option>
          <option value="no">Splits: summary only</option>
        </select>
      </div>

      {status === "loading" && <LoadingState status="loading" loadingLabel="Loading workouts..." />}
      {status === "error" && <LoadingState status="error" errorLabel={error ?? undefined} />}

      {status === "ready" && total === 0 && (
        <LoadingState
          status="empty"
          emptyTitle="No workouts match these filters"
          emptyBody="Try clearing a filter, or add a new workout."
          emptyAction={
            <button className="btn-primary" onClick={() => navigate("/upload")}>
              Add a workout
            </button>
          }
        />
      )}

      {status === "ready" && total > 0 && (
        <div className="card">
          <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Workout</th>
                <th>Distance</th>
                <th>Time</th>
                <th>Pace</th>
                <th>Watts</th>
                <th>HR</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {items.map((w) => (
                <tr key={w.id} className="clickable" onClick={() => navigate(`/workouts/${w.id}`)}>
                  <td className="data-table-text">{formatDate(w.date)}</td>
                  <td className="data-table-text">
                    {w.title} <span className={categoryBadgeClass(w.category)}>{categoryLabel(w.category)}</span>
                  </td>
                  <td>{formatDistance(w.total_distance_m)}</td>
                  <td>{formatDuration(w.total_duration_s)}</td>
                  <td>{w.avg_pace_display}</td>
                  <td>{w.avg_watts.toFixed(0)}W</td>
                  <td>{w.avg_hr ? `${w.avg_hr.toFixed(0)}bpm` : "—"}</td>
                  <td className="data-table-text">{w.has_splits ? "Full detail" : "Summary only"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>

          <div className="pagination-row">
            <span>
              Page {page} of {totalPages} ({total} workouts)
            </span>
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <button className="btn-secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                Previous
              </button>
              <button
                className="btn-secondary"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </button>
            </div>
          </div>
        </div>
      )}
    </Layout>
  );
}
