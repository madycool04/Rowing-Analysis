import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { analyticsApi, extractErrorMessage, workoutsApi } from "../api/client";
import { HRChart, type HrZoneDatum } from "../components/HRChart";
import { Layout } from "../components/Layout";
import { LoadingState } from "../components/LoadingState";
import { MetricCard, MetricRow } from "../components/MetricCard";
import { WorkoutChart } from "../components/WorkoutChart";
import type { AnalyticsEnvelope, Workout, WorkoutListItem } from "../types";
import {
  categoryBadgeClass,
  categoryLabel,
  formatDate,
  formatDistance,
  formatDuration,
} from "../utils/format";

export function WorkoutDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [workout, setWorkout] = useState<Workout | null>(null);
  const [analytics, setAnalytics] = useState<AnalyticsEnvelope | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">(
    "loading"
  );
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [similar, setSimilar] = useState<WorkoutListItem[]>([]);
  const [previousSimilarWStroke, setPreviousSimilarWStroke] = useState<
    number | null
  >(null);

  useEffect(() => {
    if (!id) return;

    let cancelled = false;

    Promise.all([
      workoutsApi.get(Number(id)),
      analyticsApi.workout(Number(id)),
      workoutsApi.list({
        page: 1,
        page_size: 100,
        sort: "newest",
      }),
    ])
      .then(([w, a, list]) => {
        if (cancelled) return;

        setWorkout(w);
        setAnalytics(a);

        /*
         * A previous similar workout must:
         * - be a different workout
         * - be older than the current workout
         * - be within ±3% of the current workout distance
         *
         * We then sort explicitly by date so the first workout
         * is the most recent older comparable workout.
         */
        const similarWorkouts = list.items
          .filter(
            (x) =>
              x.id !== w.id &&
              new Date(x.date).getTime() <
                new Date(w.date).getTime() &&
              Math.abs(x.total_distance_m - w.total_distance_m) /
                Math.max(w.total_distance_m, 1) <=
                0.03
          )
          .sort(
            (a, b) =>
              new Date(b.date).getTime() -
              new Date(a.date).getTime()
          )
          .slice(0, 5);

        setSimilar(similarWorkouts);

        /*
         * The main workout can now render immediately.
         * Comparison analytics are loaded separately so they
         * don't keep the whole page on the loading screen.
         */
        setStatus("ready");

        void findPreviousSimilarWStroke(
          similarWorkouts,
          cancelled
        );
      })
      .catch((err) => {
        if (cancelled) return;

        setError(
          extractErrorMessage(err, "Couldn't load this workout.")
        );
        setStatus("error");
      });

    return () => {
      cancelled = true;
    };
  }, [id]);

  async function findPreviousSimilarWStroke(
    candidates: WorkoutListItem[],
    cancelled: boolean
  ) {
    /*
     * Candidates are already ordered from newest to oldest.
     * We use the first older comparable workout that actually
     * has W/stroke data.
     */
    try {
      const candidateResults = await Promise.all(
        candidates.map(async (candidate) => {
          try {
            const candidateAnalytics =
              await analyticsApi.workout(candidate.id);

            const metrics =
              candidateAnalytics.metrics as Record<string, any>;

            const wattsPerStroke =
              metrics.watts_per_stroke;

            if (
              wattsPerStroke &&
              wattsPerStroke.average_w_per_stroke != null
            ) {
              return {
                date: candidate.date,
                value: Number(
                  wattsPerStroke.average_w_per_stroke
                ),
              };
            }

            return null;
          } catch {
            return null;
          }
        })
      );

      if (cancelled) return;

      const previous = candidateResults.find(
        (result) => result != null
      );

      setPreviousSimilarWStroke(
        previous?.value ?? null
      );
    } catch {
      if (!cancelled) {
        setPreviousSimilarWStroke(null);
      }
    }
  }

  async function handleDelete() {
    if (
      !workout ||
      !confirm("Delete this workout? This can't be undone.")
    ) {
      return;
    }

    setDeleting(true);

    try {
      await workoutsApi.delete(workout.id);
      navigate("/history");
    } catch (err) {
      setError(
        extractErrorMessage(err, "Couldn't delete this workout.")
      );
      setDeleting(false);
    }
  }

  if (status === "loading") {
    return (
      <Layout>
        <LoadingState
          status="loading"
          loadingLabel="Loading workout..."
        />
      </Layout>
    );
  }

  if (status === "error" || !workout || !analytics) {
    return (
      <Layout>
        <LoadingState
          status="error"
          errorLabel={error ?? "Workout not found."}
        />
      </Layout>
    );
  }

  const workSplits = workout.segments
    .filter((s) => s.type === "work")
    .flatMap((s) => s.splits)
    .sort((a, b) => a.ordinal - b.ordinal);

  const paceData = workSplits.map((s, i) => ({
    splitLabel: `${i + 1}`,
    value: s.pace_s_per_500,
  }));

  const wattsData = workSplits.map((s, i) => ({
    splitLabel: `${i + 1}`,
    value: s.watts,
  }));

  const hrData = workSplits.map((s, i) => ({
    splitLabel: `${i + 1}`,
    value: s.heart_rate,
  }));

  const spmData = workSplits.map((s, i) => ({
    splitLabel: `${i + 1}`,
    value: s.stroke_rate,
  }));

  const wStrokeData = workSplits.map((s, i) => ({
    splitLabel: `${i + 1}`,
    value:
      s.watts != null && s.stroke_rate
        ? s.watts / s.stroke_rate
        : null,
  }));

  const m = analytics.metrics as Record<string, any>;
  const dq = analytics.data_quality as Record<string, any>;

  const pacing = m.pacing ?? {};

  const intervals = m.intervals;
  const hrZones = m.hr_zones;
  const ef = m.efficiency_factor;
  const decoupling = m.cardiac_decoupling;
  const drift = m.hr_drift;
  const wstroke = m.watts_per_stroke;

  const currentWStroke =
    wstroke?.average_w_per_stroke != null
      ? Number(wstroke.average_w_per_stroke)
      : null;

  const wStrokeChange =
    currentWStroke != null &&
    previousSimilarWStroke != null
      ? currentWStroke - previousSimilarWStroke
      : null;

  const wStrokeChangePct =
    currentWStroke != null &&
    previousSimilarWStroke != null &&
    previousSimilarWStroke !== 0 &&
    wStrokeChange != null
      ? (wStrokeChange / previousSimilarWStroke) * 100
      : null;

  /*
   * Use the displayed precision when deciding how to describe
   * a change. This prevents awkward output such as:
   *
   * +0.00 W/stroke (+0.0%)
   * You produced more...
   *
   * If the difference disappears when rounded for display,
   * we describe it as no meaningful change at displayed precision.
   */
  const displayedWStrokeChange =
    wStrokeChange != null
      ? Number(wStrokeChange.toFixed(2))
      : null;

  const displayedWStrokeChangePct =
    wStrokeChangePct != null
      ? Number(wStrokeChangePct.toFixed(1))
      : null;

  const calories = workout.segments
    .flatMap((s) => s.splits)
    .reduce(
      (sum, s) => sum + (s.calories ?? 0),
      0
    );

  return (
    <Layout>
      <div
        className="page-header"
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
        }}
      >
        <div>
          <h1>
            {workout.title}{" "}
            <span className={categoryBadgeClass(workout.category)}>
              {categoryLabel(workout.category)}
            </span>
          </h1>

          <p className="page-subtitle">
            {formatDate(workout.date)}
          </p>
        </div>

        <button
          className="btn-secondary"
          onClick={handleDelete}
          disabled={deleting}
        >
          {deleting ? "Deleting..." : "Delete"}
        </button>
      </div>

      <div className="stat-grid">
        <StatBlock
          label="Distance"
          value={formatDistance(workout.total_distance_m)}
        />

        <StatBlock
          label="Duration"
          value={formatDuration(workout.total_duration_s)}
        />

        <StatBlock
          label="Avg Pace"
          value={`${workout.avg_pace_display}/500m`}
        />

        <StatBlock
          label="Avg Watts"
          value={`${workout.avg_watts.toFixed(0)}W`}
        />

        {workout.avg_hr != null && (
          <StatBlock
            label="Avg HR"
            value={`${workout.avg_hr.toFixed(0)}bpm`}
          />
        )}

        {workout.avg_stroke_rate != null && (
          <StatBlock
            label="Avg Stroke Rate"
            value={`${workout.avg_stroke_rate.toFixed(1)}spm`}
          />
        )}

        <StatBlock
          label="Calories"
          value={
            calories > 0
              ? `${calories.toFixed(0)} kcal`
              : "—"
          }
        />
      </div>

      {analytics.insights.length > 0 && (
        <div className="card">
          <p className="card-title">Insights</p>

          <ul className="insight-list">
            {analytics.insights.map((insight, i) => (
              <li key={i}>{insight}</li>
            ))}
          </ul>
        </div>
      )}

      {workSplits.length > 0 && (
        <>
          <div className="card">
            <p className="card-title">Pace</p>

            <WorkoutChart
              data={paceData}
              color="#3ddc97"
              unit="s/500m"
              invertY
            />
          </div>

          <div className="card">
            <p className="card-title">Watts</p>

            <WorkoutChart
              data={wattsData}
              color="#e0a94a"
              unit="W"
            />
          </div>

          {hrData.some((d) => d.value != null) && (
            <div className="card">
              <p className="card-title">Heart Rate</p>

              <WorkoutChart
                data={hrData}
                color="#e0575b"
                unit="bpm"
              />
            </div>
          )}

          {spmData.some((d) => d.value != null) && (
            <div className="card">
              <p className="card-title">Stroke Rate</p>

              <WorkoutChart
                data={spmData}
                color="#4f6a8f"
                unit="spm"
              />
            </div>
          )}

          {wStrokeData.some((d) => d.value != null) && (
            <div className="card">
              <p className="card-title">W/stroke</p>

              <WorkoutChart
                data={wStrokeData}
                color="#8f6ad8"
                unit=" W/stroke"
              />
            </div>
          )}
        </>
      )}

      <div className="metric-grid">
        <MetricCard
          title="Pacing"
          available={dq.pacing_evenness_available}
          unavailableReason={
            dq.pacing_evenness_unavailable_reason
          }
        >
          {dq.pacing_evenness_available && (
            <>
              <div className="pacing-metrics">
                <MetricRow
                  label="Pace variation (CV)"
                  value={
                    pacing.pacing_cv_pct != null
                      ? `${pacing.pacing_cv_pct.toFixed(1)}%`
                      : "—"
                  }
                />

                {pacing.pace_fade_pct != null && (
                  <MetricRow
                    label="Pace fade"
                    value={`${pacing.pace_fade_pct.toFixed(1)}%`}
                  />
                )}

                {pacing.fastest_split && (
                  <MetricRow
                    label="Fastest split"
                    value={`#${pacing.fastest_split.ordinal + 1}`}
                  />
                )}
              </div>

              <p className="metric-note">
                <strong>What does this mean?</strong>
                <br />
                Pace variation shows how consistently you rowed.
                Lower variation means your pace stayed more even.
                Pace fade shows how much your pace slowed toward
                the end of the workout.
              </p>

              <p className="metric-note">
                <strong>Research context</strong>
                <br />
                An analysis of 636 crews from World and European
                Championship A-finals found that medal-winning
                crews averaged a split-time variation (CV) of
                1.72%, compared with 2.00% for non-podium crews.
                This suggests that lower pacing variation is
                associated with higher-level race performance,
                although there is no single "elite" CV target for
                every workout.
              </p>

              <p className="metric-note">
                <em>
                  Consistency labels are general guidelines, not
                  official rowing standards.
                </em>
              </p>
            </>
          )}
        </MetricCard>

        <MetricCard
          title="Heart-Rate Zones"
          available={!!hrZones}
          unavailableReason={dq.hr_zones_unavailable_reason}
        >
          {hrZones && (
            <HRChart
              zones={hrZones.zones as HrZoneDatum[]}
            />
          )}
        </MetricCard>

        <MetricCard
          title="Stroke Efficiency Proxy"
          available={!!wstroke}
          unavailableReason={
            dq.watts_per_stroke_unavailable_reason
          }
        >
          {wstroke && (
            <>
              <MetricRow
                label="Average W/stroke"
                value={
                  currentWStroke != null
                    ? `${currentWStroke.toFixed(2)} W/stroke`
                    : "—"
                }
              />

              <p className="metric-note">
                <strong>What does this mean?</strong>
                <br />
                W/stroke is a simple measure of how much power you
                produced relative to your stroke rate. A higher
                value means you produced more power relative to
                your stroke rate. However, higher is not
                automatically better — the ideal relationship
                between power and stroke rate depends on the
                workout and training goal.
              </p>

              <div className="metric-note">
                <strong>
                  Previous similar workout
                </strong>

                {previousSimilarWStroke != null &&
                currentWStroke != null &&
                wStrokeChange != null &&
                wStrokeChangePct != null ? (
                  <>
                    <MetricRow
                      label="Previous similar"
                      value={`${previousSimilarWStroke.toFixed(
                        2
                      )} W/stroke`}
                    />

                    <MetricRow
                      label="Current"
                      value={`${currentWStroke.toFixed(
                        2
                      )} W/stroke`}
                    />

                    <MetricRow
                      label="Change"
                      value={`${
                        displayedWStrokeChange! >= 0
                          ? "+"
                          : ""
                      }${displayedWStrokeChange!.toFixed(
                        2
                      )} W/stroke (${
                        displayedWStrokeChangePct! >= 0
                          ? "+"
                          : ""
                      }${displayedWStrokeChangePct!.toFixed(
                        1
                      )}%)`}
                    />

                    <p>
                      {displayedWStrokeChange === 0 ? (
                        <>
                          No meaningful change in W/stroke at the
                          displayed precision.
                        </>
                      ) : displayedWStrokeChange! > 0 ? (
                        <>
                          You produced more power relative to your
                          stroke rate than in your previous similar
                          workout.
                        </>
                      ) : (
                        <>
                          You produced less power relative to your
                          stroke rate than in your previous similar
                          workout.
                        </>
                      )}
                    </p>
                  </>
                ) : (
                  <p>
                    No previous similar workout with W/stroke data
                    is available for comparison.
                  </p>
                )}
              </div>

              <p className="metric-note">
                <strong>Important:</strong> W/stroke is a
                descriptive proxy, not a direct measure of
                mechanical work per stroke or technical efficiency.
              </p>
            </>
          )}
        </MetricCard>

        <MetricCard
          title="Efficiency Factor"
          available={!!ef}
          unavailableReason={
            dq.efficiency_factor_unavailable_reason
          }
        >
          {ef && (
            <>
              <MetricRow
                label="EF"
                value={ef.efficiency_factor.toFixed(2)}
              />

              <p className="metric-note">
                {ef.note}
              </p>
            </>
          )}
        </MetricCard>

        <MetricCard
          title="Cardiac Decoupling"
          available={!!decoupling}
          unavailableReason={
            dq.cardiac_decoupling_unavailable_reason
          }
        >
          {decoupling && (
            <>
              <MetricRow
                label="Decoupling"
                value={`${decoupling.decoupling_pct.toFixed(1)}%`}
              />

              <p className="metric-note">
                {decoupling.note}
              </p>
            </>
          )}
        </MetricCard>

        <MetricCard
          title="HR Drift"
          available={!!drift}
          unavailableReason={
            dq.hr_drift_unavailable_reason
          }
        >
          {drift && (
            <MetricRow
              label="Drift"
              value={`${drift.drift_pct.toFixed(1)}%`}
            />
          )}
        </MetricCard>

        <MetricCard
          title="Interval Analysis"
          available={!!intervals}
          unavailableReason={
            dq.interval_analysis_unavailable_reason
          }
        >
          {intervals && (
            <>
              <MetricRow
                label="Avg interval watts"
                value={`${intervals.avg_interval_watts.toFixed(0)}W`}
              />

              <MetricRow
                label="Consistency (CV)"
                value={`${intervals.interval_consistency_cv_pct?.toFixed(
                  1
                )}%`}
              />

              <MetricRow
                label="Work:rest ratio"
                value={intervals.work_rest_ratio ?? "—"}
              />

              <p className="metric-note">
                {intervals.decay.interpretation}
              </p>

              {intervals.decay.noisy_estimate_warning && (
                <p className="metric-note">
                  {intervals.decay.noisy_estimate_warning}
                </p>
              )}
            </>
          )}
        </MetricCard>

        {similar.length > 0 && (
          <MetricCard
            title="Compare Similar Workout"
            available={true}
          >
            {similar.slice(0, 1).map((other) => (
              <div key={other.id}>
                <MetricRow
                  label="This workout"
                  value={`${formatDuration(
                    workout.total_duration_s
                  )} · ${workout.avg_watts.toFixed(0)}W`}
                />

                <MetricRow
                  label="Previous similar"
                  value={`${formatDuration(
                    other.total_duration_s
                  )} · ${other.avg_watts.toFixed(0)}W`}
                />

                <button
                  className="btn-secondary"
                  onClick={() =>
                    navigate(`/workouts/${other.id}`)
                  }
                >
                  Open comparison workout
                </button>
              </div>
            ))}
          </MetricCard>
        )}

        <MetricCard
          title="Data Quality"
          available={true}
        >
          <MetricRow
            label="Splits"
            value={
              workout.has_splits
                ? `✓ Available (${workSplits.length})`
                : "⚠ Unavailable: CSV contains no split-level data."
            }
          />

          <MetricRow
            label="Heart rate"
            value={
              workout.has_hr
                ? `✓ ${
                    dq.hr_coverage_pct?.toFixed(0) ?? 100
                  }% coverage`
                : "⚠ Unavailable: no split-level HR data."
            }
          />

          <MetricRow
            label="Power"
            value={
              workout.has_power
                ? "✓ Available"
                : "⚠ Unavailable: power missing."
            }
          />

          <MetricRow
            label="Stroke rate"
            value={
              workout.has_stroke_rate
                ? "✓ Available"
                : "⚠ Unavailable: stroke rate missing."
            }
          />
        </MetricCard>
      </div>

      {workSplits.length > 0 && (
        <div className="card">
          <p className="card-title">Splits</p>

          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Split</th>
                  <th>Distance</th>
                  <th>Time</th>
                  <th>Watts</th>
                  <th>HR</th>
                  <th>Stroke Rate</th>
                </tr>
              </thead>

              <tbody>
                {workSplits.map((s, i) => (
                  <tr key={s.id}>
                    <td>{i + 1}</td>

                    <td>
                      {formatDistance(s.distance_m)}
                    </td>

                    <td>
                      {formatDuration(s.elapsed_time_s)}
                    </td>

                    <td>
                      {s.watts != null
                        ? `${s.watts.toFixed(0)}W`
                        : "—"}
                    </td>

                    <td>
                      {s.heart_rate ?? "—"}
                    </td>

                    <td>
                      {s.stroke_rate != null
                        ? s.stroke_rate.toFixed(0)
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Layout>
  );
}

function StatBlock({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="stat-card">
      <p className="stat-card-label">{label}</p>
      <p className="stat-card-value">{value}</p>
    </div>
  );
}