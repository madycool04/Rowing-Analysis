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
   CSV FORMAT GUIDE
   ============================================================ */

function downloadCsvTemplate(
  filename: string,
  content: string
) {
  const blob = new Blob([content], {
    type: "text/csv;charset=utf-8;",
  });

  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");

  link.href = url;
  link.download = filename;

  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);

  URL.revokeObjectURL(url);
}

/*
 * This is the actual canonical SUMMARY format supported by the
 * backend parser.
 *
 * One row = one complete workout.
 */
const SUMMARY_CSV_TEMPLATE = `Date,Description,Time,Distance,Avg Heart Rate
2026-06-01,2K Test,7:05.2,2000,172
`;

/*
 * This is the actual canonical DETAILED format used by the
 * rowing dataset.
 *
 * Continuous workout:
 * Rest_Time = 0
 * Rest_Distance = 0
 */
const CONTINUOUS_CSV_TEMPLATE = `Date,Description,Time,Distance,Pace,Watts,SPM,HR,Calories,Rest_Time,Rest_Distance
2026-06-01,Steady State 6K,1:57.3,500,1:57.3,217,21,140,23,0,0
2026-06-01,Steady State 6K,1:57.6,500,1:57.6,215,21,141,24,0,0
2026-06-01,Steady State 6K,1:58.0,500,1:58.0,213,21,143,24,0,0
2026-06-01,Steady State 6K,1:58.4,500,1:58.4,211,22,144,24,0,0
`;

/*
 * This is the same DETAILED format, but with recovery values.
 *
 * Any non-zero Rest_Time OR Rest_Distance causes the backend
 * to classify the workout as an INTERVAL workout.
 */
const INTERVAL_CSV_TEMPLATE = `Date,Description,Time,Distance,Pace,Watts,SPM,HR,Calories,Rest_Time,Rest_Distance
2026-06-01,4 x 1000m,3:35.0,1000,1:47.5,195,28,175,100,180,0
2026-06-01,4 x 1000m,3:33.0,1000,1:46.5,200,29,180,102,180,0
2026-06-01,4 x 1000m,3:31.0,1000,1:45.5,205,30,183,104,180,0
2026-06-01,4 x 1000m,3:30.0,1000,1:45.0,210,31,185,106,0,0
`;

function CsvFormatGuide() {
  return (
    <div
      style={{
        marginTop: "1rem",
        borderTop: "1px solid var(--color-border)",
        paddingTop: "1rem",
      }}
    >
      <details>
        <summary
          style={{
            cursor: "pointer",
            fontWeight: 600,
            color: "var(--color-text-primary)",
            padding: "0.25rem 0",
          }}
        >
          What format should my CSV have?
        </summary>

        <div
          style={{
            marginTop: "1rem",
            color: "var(--color-text-secondary)",
            lineHeight: 1.6,
          }}
        >
          <p>
            The app supports Concept2 workout CSV files in two
            formats:
          </p>

          <ul style={{ paddingLeft: "1.25rem" }}>
            <li>
              <strong>Summary CSV</strong> — one row for the
              complete workout.
            </li>

            <li>
              <strong>Detailed CSV</strong> — one row for each
              split or interval.
            </li>
          </ul>

          <p>
            <strong>
              You do not need to add a "Workout Type" column.
            </strong>{" "}
            The app automatically determines whether a detailed
            workout is continuous or interval based on the
            <code> Rest_Time</code> and{" "}
            <code>Rest_Distance</code> columns.
          </p>

          {/* ==================================================
              SUMMARY
             ================================================== */}

          <div style={{ marginTop: "1.5rem" }}>
            <h3
              style={{
                color: "var(--color-text-primary)",
                fontSize: "1rem",
                marginBottom: "0.5rem",
              }}
            >
              1. Summary workout
            </h3>

            <p>
              Use a summary CSV when you have{" "}
              <strong>one row containing the entire workout</strong>.
            </p>

            <p>
              Example: a 2K test where you only want to import the
              total distance and total time.
            </p>

            <p>
              <strong>Required columns:</strong>
            </p>

            <pre
              style={{
                overflowX: "auto",
                background: "var(--color-surface-raised)",
                border: "1px solid var(--color-border)",
                borderRadius: "8px",
                padding: "0.75rem",
                fontSize: "0.78rem",
              }}
            >
{`Date,Description,Time,Distance,Avg Heart Rate`}
            </pre>

            <p>
              <strong>Example:</strong>
            </p>

            <pre
              style={{
                overflowX: "auto",
                background: "var(--color-surface-raised)",
                border: "1px solid var(--color-border)",
                borderRadius: "8px",
                padding: "0.75rem",
                fontSize: "0.78rem",
              }}
            >
{`Date,Description,Time,Distance,Avg Heart Rate
2026-06-01,2K Test,7:05.2,2000,172`}
            </pre>

            <p className="muted small">
              Summary workouts do not contain split-level data,
              so the Splits table will not be available for them.
            </p>

            <button
              type="button"
              className="btn-link"
              onClick={() =>
                downloadCsvTemplate(
                  "summary-workout-template.csv",
                  SUMMARY_CSV_TEMPLATE
                )
              }
            >
              Download summary template
            </button>
          </div>

          {/* ==================================================
              DETAILED / CONTINUOUS
             ================================================== */}

          <div style={{ marginTop: "1.5rem" }}>
            <h3
              style={{
                color: "var(--color-text-primary)",
                fontSize: "1rem",
                marginBottom: "0.5rem",
              }}
            >
              2. Continuous workout
            </h3>

            <p>
              Use the detailed format when your workout is broken
              into multiple splits.
            </p>

            <p>
              Example: a <strong>6K steady-state row</strong> with
              one row for every 500m.
            </p>

            <p>
              Use these columns:
            </p>

            <pre
              style={{
                overflowX: "auto",
                background: "var(--color-surface-raised)",
                border: "1px solid var(--color-border)",
                borderRadius: "8px",
                padding: "0.75rem",
                fontSize: "0.78rem",
              }}
            >
{`Date,Description,Time,Distance,Pace,Watts,SPM,HR,Calories,Rest_Time,Rest_Distance`}
            </pre>

            <p>
              For a continuous workout:
            </p>

            <ul style={{ paddingLeft: "1.25rem" }}>
              <li>
                <code>Rest_Time</code> should be{" "}
                <strong>0</strong>.
              </li>

              <li>
                <code>Rest_Distance</code> should be{" "}
                <strong>0</strong>.
              </li>

              <li>
                Each row represents one split.
              </li>
            </ul>

            <p>
              <strong>Example:</strong>
            </p>

            <pre
              style={{
                overflowX: "auto",
                background: "var(--color-surface-raised)",
                border: "1px solid var(--color-border)",
                borderRadius: "8px",
                padding: "0.75rem",
                fontSize: "0.78rem",
              }}
            >
{`Date,Description,Time,Distance,Pace,Watts,SPM,HR,Calories,Rest_Time,Rest_Distance
2026-06-01,Steady State 6K,1:57.3,500,1:57.3,217,21,140,23,0,0
2026-06-01,Steady State 6K,1:57.6,500,1:57.6,215,21,141,24,0,0
2026-06-01,Steady State 6K,1:58.0,500,1:58.0,213,21,143,24,0,0
2026-06-01,Steady State 6K,1:58.4,500,1:58.4,211,22,144,24,0,0`}
            </pre>

            <button
              type="button"
              className="btn-link"
              onClick={() =>
                downloadCsvTemplate(
                  "continuous-workout-template.csv",
                  CONTINUOUS_CSV_TEMPLATE
                )
              }
            >
              Download continuous template
            </button>
          </div>

          {/* ==================================================
              INTERVAL
             ================================================== */}

          <div style={{ marginTop: "1.5rem" }}>
            <h3
              style={{
                color: "var(--color-text-primary)",
                fontSize: "1rem",
                marginBottom: "0.5rem",
              }}
            >
              3. Interval workout
            </h3>

            <p>
              Interval workouts use the{" "}
              <strong>same detailed CSV format</strong> as
              continuous workouts.
            </p>

            <p>
              Example: <strong>4 × 1000m</strong> with 3 minutes
              recovery between intervals.
            </p>

            <p>
              The difference is that{" "}
              <code>Rest_Time</code> and/or{" "}
              <code>Rest_Distance</code> contains a non-zero value.
            </p>

            <p>
              <strong>Example:</strong>
            </p>

            <pre
              style={{
                overflowX: "auto",
                background: "var(--color-surface-raised)",
                border: "1px solid var(--color-border)",
                borderRadius: "8px",
                padding: "0.75rem",
                fontSize: "0.78rem",
              }}
            >
{`Date,Description,Time,Distance,Pace,Watts,SPM,HR,Calories,Rest_Time,Rest_Distance
2026-06-01,4 x 1000m,3:35.0,1000,1:47.5,195,28,175,100,180,0
2026-06-01,4 x 1000m,3:33.0,1000,1:46.5,200,29,180,102,180,0
2026-06-01,4 x 1000m,3:31.0,1000,1:45.5,205,30,183,104,180,0
2026-06-01,4 x 1000m,3:30.0,1000,1:45.0,210,31,185,106,0,0`}
            </pre>

            <p>
              In this example:
            </p>

            <ul style={{ paddingLeft: "1.25rem" }}>
              <li>
                <code>180</code> in <code>Rest_Time</code> means{" "}
                <strong>180 seconds / 3 minutes</strong>.
              </li>

              <li>
                <code>0</code> in <code>Rest_Distance</code> means
                there is no distance-based recovery.
              </li>

              <li>
                The final interval has zero rest because it is the
                last repetition.
              </li>
            </ul>

            <p className="muted small">
              The app automatically detects this as an interval
              workout because at least one row has a non-zero rest
              value.
            </p>

            <button
              type="button"
              className="btn-link"
              onClick={() =>
                downloadCsvTemplate(
                  "interval-workout-template.csv",
                  INTERVAL_CSV_TEMPLATE
                )
              }
            >
              Download interval template
            </button>
          </div>

          {/* ==================================================
              COLUMN REFERENCE
             ================================================== */}

          <div style={{ marginTop: "1.5rem" }}>
            <h3
              style={{
                color: "var(--color-text-primary)",
                fontSize: "1rem",
                marginBottom: "0.5rem",
              }}
            >
              CSV column reference
            </h3>

            <div
              style={{
                overflowX: "auto",
              }}
            >
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Column</th>
                    <th>What it means</th>
                    <th>Example</th>
                  </tr>
                </thead>

                <tbody>
                  <tr>
                    <td>
                      <code>Date</code>
                    </td>
                    <td>
                      Date of the workout
                    </td>
                    <td>
                      <code>2026-06-01</code>
                    </td>
                  </tr>

                  <tr>
                    <td>
                      <code>Description</code>
                    </td>
                    <td>
                      Workout name/description
                    </td>
                    <td>
                      <code>Steady State 6K</code>
                    </td>
                  </tr>

                  <tr>
                    <td>
                      <code>Time</code>
                    </td>
                    <td>
                      Time for the row/split, or total time
                      for a summary
                    </td>
                    <td>
                      <code>1:57.3</code>
                    </td>
                  </tr>

                  <tr>
                    <td>
                      <code>Distance</code>
                    </td>
                    <td>
                      Distance in metres
                    </td>
                    <td>
                      <code>500</code>
                    </td>
                  </tr>

                  <tr>
                    <td>
                      <code>Pace</code>
                    </td>
                    <td>
                      Pace per 500m
                    </td>
                    <td>
                      <code>1:57.3</code>
                    </td>
                  </tr>

                  <tr>
                    <td>
                      <code>Watts</code>
                    </td>
                    <td>
                      Power for the row/split
                    </td>
                    <td>
                      <code>217</code>
                    </td>
                  </tr>

                  <tr>
                    <td>
                      <code>SPM</code>
                    </td>
                    <td>
                      Strokes per minute
                    </td>
                    <td>
                      <code>21</code>
                    </td>
                  </tr>

                  <tr>
                    <td>
                      <code>HR</code>
                    </td>
                    <td>
                      Heart rate in BPM
                    </td>
                    <td>
                      <code>140</code>
                    </td>
                  </tr>

                  <tr>
                    <td>
                      <code>Calories</code>
                    </td>
                    <td>
                      Calories for the row/split
                    </td>
                    <td>
                      <code>23</code>
                    </td>
                  </tr>

                  <tr>
                    <td>
                      <code>Rest_Time</code>
                    </td>
                    <td>
                      Recovery time in seconds
                    </td>
                    <td>
                      <code>180</code>
                    </td>
                  </tr>

                  <tr>
                    <td>
                      <code>Rest_Distance</code>
                    </td>
                    <td>
                      Recovery distance in metres
                    </td>
                    <td>
                      <code>0</code>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* ==================================================
              IMPORTANT
             ================================================== */}

          <div
            style={{
              marginTop: "1.5rem",
              padding: "1rem",
              borderRadius: "8px",
              border: "1px solid var(--color-border)",
            }}
          >
            <strong>Quick rule:</strong>

            <p
              style={{
                marginBottom: "0.5rem",
              }}
            >
              If your CSV has multiple rows:
            </p>

            <ul
              style={{
                paddingLeft: "1.25rem",
                marginBottom: 0,
              }}
            >
              <li>
                <strong>Rest_Time = 0</strong> and{" "}
                <strong>Rest_Distance = 0</strong> → Continuous
              </li>

              <li>
                <strong>Rest_Time &gt; 0</strong> or{" "}
                <strong>Rest_Distance &gt; 0</strong> → Interval
              </li>
            </ul>
          </div>
        </div>
      </details>
    </div>
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
       * A CSV can contain:
       *
       *   1 workout -> immediately open its workout page.
       *
       *   Multiple workouts -> stay here and show all imported
       *   workouts.
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

      {status !== "done" && <CsvFormatGuide />}

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
          {result.warnings.map((w, i) => (
            <div
              className="upload-warning"
              key={i}
            >
              {w}
            </div>
          ))}

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