import axios, { type AxiosInstance } from "axios";
import type {
  AnalyticsEnvelope,
  ApiErrorBody,
  Athlete,
  AthleteUpdatePayload,
  AuthResponse,
  PerformanceMetrics,
  PredictionResponse,
  SegmentType,
  WorkoutCategory,
  TrainingLoadMetrics,
  TrendsMetrics,
  User,
  Workout,
  WorkoutListResponse,
  WorkoutUploadResponse,
} from "../types";

const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

const TOKEN_STORAGE_KEY = "rpa_access_token";

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function setStoredToken(token: string | null): void {
  if (token) {
    localStorage.setItem(TOKEN_STORAGE_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
  }
}

const http: AxiosInstance = axios.create({ baseURL: API_BASE_URL });

http.interceptors.request.use((config) => {
  const token = getStoredToken();
  if (token) {
    config.headers = config.headers ?? {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

/** Extracts a human-readable message from a FastAPI error response. */
export function extractErrorMessage(error: unknown, fallback = "Something went wrong."): string {
  if (axios.isAxiosError<ApiErrorBody>(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      return detail.map((d) => d.msg).join(", ");
    }
  }
  return fallback;
}

export const authApi = {
  register: (email: string, password: string) =>
    http.post<AuthResponse>("/auth/register", { email, password }).then((r) => r.data),

  login: (email: string, password: string) =>
    http.post<AuthResponse>("/auth/login", { email, password }).then((r) => r.data),

  me: () => http.get<User>("/auth/me").then((r) => r.data),
};

export const athletesApi = {
  list: () => http.get<Athlete[]>("/athletes").then((r) => r.data),

  get: (athleteId: number) => http.get<Athlete>(`/athletes/${athleteId}`).then((r) => r.data),

  update: (athleteId: number, payload: AthleteUpdatePayload) =>
    http.patch<Athlete>(`/athletes/${athleteId}`, payload).then((r) => r.data),
};

export interface WorkoutListParams {
  page?: number;
  page_size?: number;
  sort?: "newest" | "oldest" | "fastest" | "highest_watts" | "longest" | "highest_load";
  has_hr?: boolean;
  has_splits?: boolean;
}

export interface ManualSplitPayload {
  ordinal: number;
  distance_m: number;
  elapsed_time_s: number;
  watts?: number | null;
  heart_rate?: number | null;
  stroke_rate?: number | null;
  calories?: number | null;
}

export interface ManualSegmentPayload {
  type: SegmentType;
  splits: ManualSplitPayload[];
}

export interface WorkoutManualCreatePayload {
  title: string;
  date: string;
  category?: WorkoutCategory;
  segments: ManualSegmentPayload[];
}

export const workoutsApi = {
  list: (params: WorkoutListParams = {}) =>
    http.get<WorkoutListResponse>("/workouts", { params }).then((r) => r.data),

  get: (workoutId: number) => http.get<Workout>(`/workouts/${workoutId}`).then((r) => r.data),

  create: (payload: WorkoutManualCreatePayload) =>
    http.post<Workout>("/workouts", payload).then((r) => r.data),

  uploadCsv: (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return http
      .post<WorkoutUploadResponse>("/workouts/upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      .then((r) => r.data);
  },

  delete: (workoutId: number) => http.delete(`/workouts/${workoutId}`).then(() => undefined),
};

export interface AnalyticsDateRangeParams {
  start_date?: string;
  end_date?: string;
}

export const analyticsApi = {
  workout: (workoutId: number) =>
    http.get<AnalyticsEnvelope>(`/analytics/workout/${workoutId}`).then((r) => r.data),

  performance: () =>
    http.get<AnalyticsEnvelope<PerformanceMetrics>>("/analytics/performance").then((r) => r.data),

  trainingLoad: (params: AnalyticsDateRangeParams = {}) =>
    http
      .get<AnalyticsEnvelope<TrainingLoadMetrics>>("/analytics/training-load", { params })
      .then((r) => r.data),

  trends: (params: AnalyticsDateRangeParams = {}) =>
    http.get<AnalyticsEnvelope<TrendsMetrics>>("/analytics/trends", { params }).then((r) => r.data),
};

export const predictionsApi = {
  get2k: () => http.get<PredictionResponse>("/predictions/2k").then((r) => r.data),
};

export default http;
