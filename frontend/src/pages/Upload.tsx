import { useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { extractErrorMessage, workoutsApi } from "../api/client";
import { Layout } from "../components/Layout";
import type {
  SegmentType,
  WorkoutCategory,
  WorkoutUploadResponse,
} from "../types";
import { formatDistance, formatDuration } from "../utils/format";

type Mode = "csv" | "manual";

function todayLocalDatetime(): string {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  return now.toISOString().slice(0, 16);
}

export function Upload() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<Mode>("csv");

  return (
    <Layout>
      <div className="page-header">
        <h1>Add a workout</h1>
        <p className="page-subtitle">
          Import a Concept2 export, or log a session by hand.
        </p>
      </div>

      <div className="tab-row">
        <button
          className={`tab-button${
            mode === "csv" ? " tab-button--active" : ""
          }`}
          onClick={() => setMode("csv")}
        >
          Upload CSV
        </button>

        <button
          className={`tab-button${
            mode === "manual" ? " tab-button--active" : ""
          }`}
          onClick={() => setMode("manual")}
        >
          Enter Manually
        </button>
      </div>

      {mode === "csv" ? (
        <CsvUploadPanel
          onDone={(id) => navigate(`/workouts/${id}`)}
        />
      ) : (
        <ManualEntryPanel
          onDone={(id) => navigate(`/workouts/${id}`)}
        />
      )}
    </Layout>
  );
}

/* ============================================================
   CSV UPLOAD
   ============================================================ */

function CsvUploadPanel({
  onDone,
}: {
  onDone: (workoutId: number) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);

  const [dragActive, setDragActive] = useState(false);

  const [status, setStatus] = useState<
    "idle" | "uploading" | "done" | "error"
  >("idle");

  const [error, setError] = useState<string | null>(null);

  const [result, setResult] =
    useState<WorkoutUploadResponse | null>(null);

  async function handleFile(file: File) {
    setStatus("uploading");
    setError(null);
    setResult(null);

    try {
      const res = await workoutsApi.uploadCsv(file);

      /*
       * IMPORTANT:
       *
       * A CSV can now contain:
       *
       *   1 workout  -> preserve old behaviour and
       *                 immediately open its analysis page.
       *
       *   Multiple workouts -> stay on this page and show
       *                        all imported workouts.
       */
      if (res.workouts.length === 1) {
        onDone(res.workouts[0].id);
        return;
      }

      setResult(res);
      setStatus("done");
    } catch (err) {
      setError(
        extractErrorMessage(
          err,
          "Couldn't parse this file. Check the export and try again."
        )
      );

      setStatus("error");
    }
  }

  return (
    <div className="card">
      {status !== "done" && (
        <div
          className={`dropzone${
            dragActive ? " dropzone--active" : ""
          }`}
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragActive(true);
          }}
          onDragLeave={() => setDragActive(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragActive(false);

            const file = e.dataTransfer.files?.[0];

            if (file) {
              handleFile(file);
            }
          }}
        >
          <p className="dropzone-title">
            {status === "uploading"
              ? "Uploading..."
              : "Drag a Concept2 CSV here, or click to browse"}
          </p>

          <p className="dropzone-hint">
            Summary or detailed split exports both work.
          </p>

          <input
            ref={inputRef}
            type="file"
            accept=".csv,text/csv"
            style={{ display: "none" }}
            onChange={(e) => {
              const file = e.target.files?.[0];

              if (file) {
                handleFile(file);
              }
            }}
          />
        </div>
      )}

      {status === "error" && (
        <div
          className="auth-error"
          style={{ marginTop: "1rem" }}
        >
          {error}
        </div>
      )}

      {status === "done" && result && (
        <div>
          {/* Warnings */}
          {result.warnings.map((w, i) => (
            <div
              className="upload-warning"
              key={i}
            >
              {w}
            </div>
          ))}

          {/* Number of workouts imported */}
          <p
            className="card-title"
            style={{
              marginTop: result.warnings.length
                ? "1rem"
                : 0,
            }}
          >
            {result.workouts.length} workout
            {result.workouts.length !== 1 ? "s" : ""} imported
          </p>

          {/* Workout cards */}
          <div style={{ marginTop: "1rem" }}>
            {result.workouts.map((workout) => (
              <div
                className="panel"
                key={workout.id}
                style={{
                  marginBottom: "1rem",
                }}
              >
                <p className="card-title">
                  {workout.title}
                </p>

                <div className="metric-row">
                  <span className="metric-row-label">
                    Distance
                  </span>

                  <span className="metric-row-value">
                    {formatDistance(
                      workout.total_distance_m
                    )}
                  </span>
                </div>

                <div className="metric-row">
                  <span className="metric-row-label">
                    Duration
                  </span>

                  <span className="metric-row-value">
                    {formatDuration(
                      workout.total_duration_s
                    )}
                  </span>
                </div>

                <div className="metric-row">
                  <span className="metric-row-label">
                    Avg pace
                  </span>

                  <span className="metric-row-value">
                    {workout.avg_pace_display
                      ? `${workout.avg_pace_display}/500m`
                      : "—"}
                  </span>
                </div>

                <div className="metric-row">
                  <span className="metric-row-label">
                    Avg watts
                  </span>

                  <span className="metric-row-value">
                    {Math.round(workout.avg_watts)} W
                  </span>
                </div>

                <button
                  className="btn-primary"
                  style={{ marginTop: "1rem" }}
                  onClick={() =>
                    onDone(workout.id)
                  }
                >
                  View workout
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ============================================================
   MANUAL WORKOUT ENTRY
   ============================================================ */

function ManualSplitRow({
  split,
  index,
  onChange,
  onRemove,
  canRemove,
}: {
  split: ManualSplitForm;
  index: number;
  onChange: (
    patch: Partial<ManualSplitForm>
  ) => void;
  onRemove: () => void;
  canRemove: boolean;
}) {
  return (
    <tr>
      <td>{index + 1}</td>

      <td>
        <input
          type="number"
          min="1"
          step="1"
          value={split.distance_m}
          onChange={(e) =>
            onChange({
              distance_m: e.target.value,
            })
          }
          placeholder="500"
        />
      </td>

      <td>
        <input
          value={split.time}
          onChange={(e) =>
            onChange({
              time: e.target.value,
            })
          }
          placeholder="1:35.0"
        />
      </td>

      <td>
        <input
          type="number"
          min="0"
          step="1"
          value={split.watts}
          onChange={(e) =>
            onChange({
              watts: e.target.value,
            })
          }
          placeholder="300"
        />
      </td>

      <td>
        <input
          type="number"
          min="0"
          step="1"
          value={split.heart_rate}
          onChange={(e) =>
            onChange({
              heart_rate: e.target.value,
            })
          }
          placeholder="180"
        />
      </td>

      <td>
        <input
          type="number"
          min="0"
          step="0.1"
          value={split.stroke_rate}
          onChange={(e) =>
            onChange({
              stroke_rate: e.target.value,
            })
          }
          placeholder="31"
        />
      </td>

      <td>
        <input
          type="number"
          min="0"
          step="1"
          value={split.calories}
          onChange={(e) =>
            onChange({
              calories: e.target.value,
            })
          }
          placeholder=""
        />
      </td>

      <td>
        <button
          className="btn-icon-remove"
          type="button"
          onClick={onRemove}
          disabled={!canRemove}
        >
          ×
        </button>
      </td>
    </tr>
  );
}

interface ManualSplitForm {
  distance_m: string;
  time: string;
  watts: string;
  heart_rate: string;
  stroke_rate: string;
  calories: string;
}

interface ManualSegmentForm {
  type: SegmentType;
  splits: ManualSplitForm[];
}

const blankSplit = (): ManualSplitForm => ({
  distance_m: "",
  time: "",
  watts: "",
  heart_rate: "",
  stroke_rate: "",
  calories: "",
});

const blankSegment = (): ManualSegmentForm => ({
  type: "work",
  splits: [blankSplit()],
});

function parseNumber(
  value: string
): number | null {
  if (!value.trim()) {
    return null;
  }

  const n = Number(value);

  return Number.isFinite(n) ? n : null;
}

function parseTime(
  value: string
): number | null {
  const v = value.trim();

  if (!v) {
    return null;
  }

  if (!v.includes(":")) {
    const n = Number(v);

    return Number.isFinite(n) && n > 0
      ? n
      : null;
  }

  const parts = v.split(":");

  if (parts.length !== 2) {
    return null;
  }

  const min = Number(parts[0]);
  const sec = Number(parts[1]);

  if (
    !Number.isFinite(min) ||
    !Number.isFinite(sec) ||
    min < 0 ||
    sec < 0 ||
    sec >= 60
  ) {
    return null;
  }

  return min * 60 + sec;
}

function formatManualTime(
  seconds: number
): string {
  const whole = Math.floor(seconds);
  const min = Math.floor(whole / 60);
  const sec = whole % 60;

  return `${min}:${String(sec).padStart(
    2,
    "0"
  )}`;
}

function ManualEntryPanel({
  onDone,
}: {
  onDone: (workoutId: number) => void;
}) {
  const [title, setTitle] = useState("");
  const [date, setDate] = useState(
    todayLocalDatetime()
  );

  const [category, setCategory] =
    useState<WorkoutCategory>("continuous");

  const [segments, setSegments] = useState<
    ManualSegmentForm[]
  >([blankSegment()]);

  const [error, setError] =
    useState<string | null>(null);

  const [saving, setSaving] = useState(false);

  const totals = segments.reduce(
    (acc, seg) => {
      for (const sp of seg.splits) {
        acc.distance +=
          parseNumber(sp.distance_m) ?? 0;

        acc.duration +=
          parseTime(sp.time) ?? 0;
      }

      return acc;
    },
    {
      distance: 0,
      duration: 0,
    }
  );

  function updateSegment(
    i: number,
    patch: Partial<ManualSegmentForm>
  ) {
    setSegments((prev) =>
      prev.map((s, j) =>
        j === i
          ? {
              ...s,
              ...patch,
            }
          : s
      )
    );
  }

  function updateSplit(
    si: number,
    pi: number,
    patch: Partial<ManualSplitForm>
  ) {
    setSegments((prev) =>
      prev.map((seg, i) =>
        i !== si
          ? seg
          : {
              ...seg,
              splits: seg.splits.map(
                (sp, j) =>
                  j === pi
                    ? {
                        ...sp,
                        ...patch,
                      }
                    : sp
              ),
            }
      )
    );
  }

  function addSplit(si: number) {
    setSegments((prev) =>
      prev.map((seg, i) =>
        i === si
          ? {
              ...seg,
              splits: [
                ...seg.splits,
                blankSplit(),
              ],
            }
          : seg
      )
    );
  }

  function removeSplit(
    si: number,
    pi: number
  ) {
    setSegments((prev) =>
      prev.map((seg, i) =>
        i === si && seg.splits.length > 1
          ? {
              ...seg,
              splits: seg.splits.filter(
                (_, j) => j !== pi
              ),
            }
          : seg
      )
    );
  }

  function addSegment() {
    setSegments((prev) => [
      ...prev,
      blankSegment(),
    ]);
  }

  function removeSegment(i: number) {
    setSegments((prev) =>
      prev.length > 1
        ? prev.filter((_, j) => j !== i)
        : prev
    );
  }

  async function handleSubmit(
    e: FormEvent
  ) {
    e.preventDefault();

    setError(null);

    if (!title.trim()) {
      setError("Workout name is required.");
      return;
    }

    try {
      const payloadSegments = segments.map(
        (seg, si) => {
          const splits = seg.splits.map(
            (sp, pi) => {
              const distance = parseNumber(
                sp.distance_m
              );

              const elapsed = parseTime(
                sp.time
              );

              if (
                distance == null ||
                distance <= 0 ||
                elapsed == null ||
                elapsed <= 0
              ) {
                throw new Error(
                  `Segment ${si + 1}, split ${
                    pi + 1
                  }: distance and time are required. Time can be seconds or M:SS.`
                );
              }

              return {
                ordinal: pi + 1,
                distance_m: distance,
                elapsed_time_s: elapsed,
                watts: parseNumber(
                  sp.watts
                ),
                heart_rate: parseNumber(
                  sp.heart_rate
                ),
                stroke_rate: parseNumber(
                  sp.stroke_rate
                ),
                calories: parseNumber(
                  sp.calories
                ),
              };
            }
          );

          return {
            type: seg.type,
            splits,
          };
        }
      );

      setSaving(true);

      const workout =
        await workoutsApi.create({
          title: title.trim(),
          date: new Date(
            date
          ).toISOString(),
          category,
          segments: payloadSegments,
        });

      onDone(workout.id);
    } catch (err) {
      setError(
        extractErrorMessage(
          err,
          err instanceof Error
            ? err.message
            : "Couldn't save this workout."
        )
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      {error && (
        <div
          className="auth-error"
          style={{
            marginBottom: "1rem",
          }}
        >
          {error}
        </div>
      )}

      <section className="panel">
        <h3>Workout information</h3>

        <div className="form-grid">
          <label className="field">
            <span>Workout name *</span>

            <input
              value={title}
              onChange={(e) =>
                setTitle(e.target.value)
              }
              placeholder="e.g. 2K Test"
              required
            />
          </label>

          <label className="field">
            <span>Date &amp; time *</span>

            <input
              type="datetime-local"
              value={date}
              onChange={(e) =>
                setDate(e.target.value)
              }
              required
            />
          </label>

          <label className="field">
            <span>Workout type</span>

            <select
              value={category}
              onChange={(e) =>
                setCategory(
                  e.target.value as WorkoutCategory
                )
              }
            >
              <option value="continuous">
                Continuous
              </option>

              <option value="interval">
                Interval
              </option>

              <option value="mixed">
                Mixed
              </option>

              <option value="other">
                Other
              </option>
            </select>
          </label>
        </div>

        <p className="muted small manual-total">
          Current total:{" "}
          <strong>
            {Math.round(totals.distance)}m
          </strong>{" "}
          ·{" "}
          <strong>
            {formatManualTime(totals.duration)}
          </strong>
        </p>
      </section>

      {segments.map((segment, si) => (
        <section
          className="panel"
          key={si}
        >
          <div className="panel-head">
            <h3>
              Segment {si + 1}
            </h3>

            {segments.length > 1 && (
              <button
                className="btn danger"
                type="button"
                onClick={() =>
                  removeSegment(si)
                }
              >
                Remove
              </button>
            )}
          </div>

          <label
            className="field"
            style={{
              maxWidth: 260,
              marginBottom: "1rem",
            }}
          >
            <span>
              Segment type
            </span>

            <select
              value={segment.type}
              onChange={(e) =>
                updateSegment(si, {
                  type: e.target
                    .value as SegmentType,
                })
              }
            >
              <option value="work">
                Work
              </option>

              <option value="rest">
                Rest / Recovery
              </option>

              <option value="warmup">
                Warm-up
              </option>

              <option value="cooldown">
                Cool-down
              </option>

              <option value="other">
                Other
              </option>
            </select>
          </label>

          <div className="manual-split-table-wrap">
            <table className="data-table manual-split-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>
                    Distance (m) *
                  </th>
                  <th>Time *</th>
                  <th>Watts</th>
                  <th>HR</th>
                  <th>SPM</th>
                  <th>Calories</th>
                  <th></th>
                </tr>
              </thead>

              <tbody>
                {segment.splits.map(
                  (sp, pi) => (
                    <ManualSplitRow
                      key={pi}
                      split={sp}
                      index={pi}
                      onChange={(patch) =>
                        updateSplit(
                          si,
                          pi,
                          patch
                        )
                      }
                      onRemove={() =>
                        removeSplit(
                          si,
                          pi
                        )
                      }
                      canRemove={
                        segment.splits
                          .length > 1
                      }
                    />
                  )
                )}
              </tbody>
            </table>
          </div>

          <button
            className="btn-secondary"
            type="button"
            onClick={() =>
              addSplit(si)
            }
          >
            + Add split
          </button>
        </section>
      ))}

      <div className="manual-actions">
        <button
          className="btn-secondary"
          type="button"
          onClick={addSegment}
        >
          + Add segment
        </button>

        <button
          className="btn-primary"
          type="submit"
          disabled={saving}
        >
          {saving
            ? "Saving..."
            : "Save workout"}
        </button>
      </div>
    </form>
  );
}