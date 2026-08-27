export type Sex = "male" | "female" | "other";

export type TrainingLevel = "beginner" | "intermediate" | "advanced" | "elite";

export interface HrZone {
  zone: number;
  label: string;
  lower_pct: number;
  upper_pct: number;
}

export interface HrZoneConfig {
  model: string;
  zones: HrZone[];
}

export interface User {
  id: number;
  email: string;
  created_at: string;
}

export interface Athlete {
  id: number;
  user_id: number;
  name: string;
  date_of_birth: string | null;
  sex: Sex | null;
  weight_kg: number | null;
  height_cm: number | null;
  resting_hr: number | null;
  max_hr: number | null;
  best_2k_seconds: number | null;
  training_level: TrainingLevel | null;
  hr_zone_config: HrZoneConfig;
  created_at: string;
  updated_at: string;
}

export interface AthleteUpdatePayload {
  name?: string;
  date_of_birth?: string | null;
  sex?: Sex | null;
  weight_kg?: number | null;
  height_cm?: number | null;
  resting_hr?: number | null;
  max_hr?: number | null;
  best_2k_seconds?: number | null;
  training_level?: TrainingLevel | null;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
  athlete: Athlete;
}

export type SegmentType = "work" | "rest" | "warmup" | "cooldown" | "other";

export type WorkoutCategory =
  | "continuous"
  | "interval"
  | "mixed"
  | "other";

export type WorkoutSource =
  | "concept2_csv_summary"
  | "concept2_csv_detailed"
  | "manual"
  | "generated_sample";

export interface Split {
  id: number;
  ordinal: number;
  distance_m: number;
  elapsed_time_s: number;
  pace_s_per_500: number | null;
  watts: number | null;
  stroke_rate: number | null;
  heart_rate: number | null;
  calories: number | null;
}

export interface Segment {
  id: number;
  ordinal: number;
  type: SegmentType;
  start_time_s: number;
  duration_s: number;
  distance_m: number;
  splits: Split[];
}

export interface WorkoutListItem {
  id: number;
  title: string;
  date: string;
  category: WorkoutCategory;
  total_distance_m: number;
  total_duration_s: number;
  avg_pace_s_per_500: number;
  avg_pace_display: string | null;
  avg_watts: number;
  avg_hr: number | null;
  avg_stroke_rate: number | null;
  has_hr: boolean;
  has_splits: boolean;
  has_power: boolean;
  has_stroke_rate: boolean;
}

export interface Workout extends WorkoutListItem {
  source: WorkoutSource;
  hr_coverage_pct: number | null;
  split_granularity: string | null;
  has_distance: boolean;
  created_at: string;
  segments: Segment[];
}

export interface WorkoutListResponse {
  items: WorkoutListItem[];
  total: number;
  page: number;
  page_size: number;
}

/*
 * CSV upload can now return multiple workouts.
 *
 * Previously:
 *   workout: Workout
 *
 * Now:
 *   workouts: Workout[]
 */
export interface WorkoutUploadResponse {
  workouts: Workout[];
  warnings: string[];
}

export interface AnalyticsEnvelope<TMetrics = Record<string, unknown>> {
  metrics: TMetrics;
  data_quality: Record<string, unknown>;
  insights: string[];
}

export interface PersonalBestEntry {
  distance_m: number;
  duration_s: number;
  pace_display: string | null;
  avg_watts: number;
  date: string | null;
  workout_id: number;
}

export interface PersonalBest {
  current: PersonalBestEntry;
  previous: PersonalBestEntry | null;
  improvement_s: number | null;
}

export interface PerformanceMetrics {
  personal_bests: Record<string, PersonalBest>;
}

export interface DailyLoadPoint {
  date: string;
  daily_load: number;
  rolling_7_day: number;
  rolling_28_day: number;
  acwr: number | null;
}

export interface TrainingLoadMetrics {
  daily_series: DailyLoadPoint[];
  reference_2k_watts: number | null;
}

export interface ProgressionPoint {
  date: string | null;
  duration_s: number;
  pace_display: string | null;
  avg_watts: number;
  workout_id: number;
}

export interface TrendsMetrics {
  performance_2k: ProgressionPoint[];
  performance_5k: ProgressionPoint[];
  avg_watts: {
    date: string;
    avg_watts: number;
    workout_id: number;
  }[];
  avg_hr: {
    date: string;
    avg_hr: number;
    workout_id: number;
  }[];
  efficiency_factor: {
    date: string;
    efficiency_factor: number;
    workout_id: number;
  }[];
  training_load: DailyLoadPoint[];
  pacing_consistency: {
    date: string;
    pacing_cv_pct: number;
    workout_id: number;
  }[];
  interval_decay: {
    date: string;
    slope_watts_per_interval: number;
    workout_id: number;
  }[];
}

export interface ContributingFactor {
  factor: string;
  trend: "positive" | "negative" | "unchanged" | "up" | "down";
}

export interface PredictionResponse {
  available: boolean;
  reason: string | null;
  predicted_time_s: number | null;
  predicted_pace_display: string | null;
  target_distance_m: number | null;
  lower_bound_s: number | null;
  upper_bound_s: number | null;
  confidence: "low" | "moderate" | "high" | null;
  method_used: string | null;
  n_historical_2k_tests: number;
  sufficient_data_for_ml: boolean;
  change_vs_previous_s: number | null;
  contributing_factors: ContributingFactor[];
  note: string | null;
}

export interface ApiErrorBody {
  detail?: string | { msg: string; loc: (string | number)[] }[];
}