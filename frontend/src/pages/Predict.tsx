import { useEffect, useState } from "react";
import { extractErrorMessage, predictionsApi } from "../api/client";
import { Layout } from "../components/Layout";
import { LoadingState } from "../components/LoadingState";
import type { PredictionResponse } from "../types";
import { formatDuration } from "../utils/format";

const CONFIDENCE_LABELS: Record<string, string> = {
  low: "Low confidence",
  moderate: "Moderate confidence",
  high: "High confidence",
};

const METHOD_LABELS: Record<string, string> = {
  previous_2k: "Your previous 2K result",
  pauls_law: "Paul's Law (from a longer piece)",
  ridge: "Ridge regression model",
  random_forest: "Random Forest model",
  xgboost: "XGBoost model",
};

function trendSymbol(trend: string): string {
  if (trend === "positive" || trend === "up") return "▲";
  if (trend === "negative" || trend === "down") return "▼";
  return "–";
}

function trendClass(trend: string): string {
  if (trend === "positive") return "stat-card-trend--up";
  if (trend === "negative") return "stat-card-trend--down";
  return "stat-card-trend--flat";
}

export function Predict() {
  const [prediction, setPrediction] = useState<PredictionResponse | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    predictionsApi
      .get2k()
      .then((res) => {
        if (cancelled) return;
        setPrediction(res);
        setStatus("ready");
      })
      .catch((err) => {
        if (cancelled) return;
        setError(extractErrorMessage(err, "Couldn't load your 2K prediction."));
        setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <Layout>
      <div className="page-header">
        <h1>2K Prediction</h1>
        <p className="page-subtitle">
          An advanced feature within the broader analytics platform - a model estimate, not a
          guarantee.
        </p>
      </div>

      {status === "loading" && <LoadingState status="loading" loadingLabel="Estimating your 2K..." />}
      {status === "error" && <LoadingState status="error" errorLabel={error ?? undefined} />}

      {status === "ready" && prediction && !prediction.available && (
        <LoadingState
          status="empty"
          emptyTitle="Not enough data yet"
          emptyBody={prediction.reason ?? "Log a 2K, 5K, 6K, or 10K effort to get a prediction."}
        />
      )}

      {status === "ready" && prediction && prediction.available && (
        <>
          <div className="card">
            <p className="card-title">Estimated 2K</p>
            <p className="stat-card-value" style={{ fontSize: "2.2rem" }}>
              {formatDuration(prediction.predicted_time_s!)}
            </p>
            <p className="metric-note" style={{ borderTop: "none", paddingTop: 0 }}>
              {prediction.predicted_pace_display}/500m
            </p>

            {prediction.lower_bound_s != null && prediction.upper_bound_s != null ? (
              <div className="metric-row">
                <span className="metric-row-label">Estimated range</span>
                <span className="metric-row-value">
                  {formatDuration(prediction.lower_bound_s)} – {formatDuration(prediction.upper_bound_s)}
                </span>
              </div>
            ) : (
              <div className="metric-row">
                <span className="metric-row-label">Range</span>
                <span className="metric-row-value">Not enough validation history yet</span>
              </div>
            )}

            <div className="metric-row">
              <span className="metric-row-label">Confidence</span>
              <span className="metric-row-value">{CONFIDENCE_LABELS[prediction.confidence ?? "low"]}</span>
            </div>

            {prediction.change_vs_previous_s != null && (
              <div className="metric-row">
                <span className="metric-row-label">Vs. previous estimate</span>
                <span className="metric-row-value">
                  {prediction.change_vs_previous_s > 0 ? "+" : ""}
                  {prediction.change_vs_previous_s.toFixed(1)}s
                </span>
              </div>
            )}

            <p className="metric-note">{prediction.note}</p>
          </div>

          <div className="card">
            <p className="card-title">Method</p>
            <p className="metric-card-unavailable" style={{ marginBottom: "0.5rem" }}>
              {METHOD_LABELS[prediction.method_used ?? ""] ?? prediction.method_used}
            </p>
            {!prediction.sufficient_data_for_ml && (
              <p className="metric-note">
                Based on {prediction.n_historical_2k_tests} historical 2K test
                {prediction.n_historical_2k_tests === 1 ? "" : "s"} - at least 5 are needed before an
                athlete-specific model prediction is considered reliable. Baseline methods are used
                until then.
              </p>
            )}
          </div>

          {prediction.contributing_factors.length > 0 && (
            <div className="card">
              <p className="card-title">Contributing Factors</p>
              <p className="metric-note" style={{ borderTop: "none", paddingTop: 0, marginBottom: "0.75rem" }}>
                Compared with your previous estimate:
              </p>
              {prediction.contributing_factors.map((f, i) => (
                <div className="metric-row" key={i}>
                  <span className="metric-row-label">{f.factor}</span>
                  <span className={`stat-card-trend ${trendClass(f.trend)}`}>
                    {trendSymbol(f.trend)} {f.trend}
                  </span>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </Layout>
  );
}
