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
  CoachAthleteSummary,
  WorkoutComment,
  CoachInvitation,
  CoachConnection,
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
  register: (
    email: string,
    password: string,
    role: "athlete" | "coach" = "athlete",
    displayName?: string,
  ) =>
    http
      .post<AuthResponse>("/auth/register", {
        email,
        password,
        role,
        display_name: displayName || undefined,
      })
      .then((r) => r.data),

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

export const commentsApi = {
  list: (workoutId: number) =>
    http.get<WorkoutComment[]>(`/workouts/${workoutId}/comments`).then((r) => r.data),
};

export const coachApi = {
  athletes: () => http.get<CoachAthleteSummary[]>("/coach/athletes").then((r) => r.data),
  invitations: () =>
    http.get<CoachInvitation[]>("/coach/invitations").then((r) => r.data),
  inviteAthlete: (athleteEmail: string) =>
    http
      .post<CoachInvitation>("/coach/invitations", { athlete_email: athleteEmail })
      .then((r) => r.data),
  cancelInvitation: (invitationId: number) =>
    http.delete(`/coach/invitations/${invitationId}`).then(() => undefined),
  removeAthlete: (athleteId: number) =>
    http.delete(`/coach/athletes/${athleteId}`).then(() => undefined),
  athlete: (athleteId: number) =>
    http.get<Athlete>(`/coach/athletes/${athleteId}`).then((r) => r.data),
  workouts: (athleteId: number, page = 1, pageSize = 20) =>
    http
      .get<WorkoutListResponse>(`/coach/athletes/${athleteId}/workouts`, {
        params: { page, page_size: pageSize },
      })
      .then((r) => r.data),
  workout: (athleteId: number, workoutId: number) =>
    http
      .get<Workout>(`/coach/athletes/${athleteId}/workouts/${workoutId}`)
      .then((r) => r.data),
  workoutAnalytics: (athleteId: number, workoutId: number) =>
    http
      .get<AnalyticsEnvelope>(`/coach/athletes/${athleteId}/workouts/${workoutId}/analytics`)
      .then((r) => r.data),
  performance: (athleteId: number) =>
    http
      .get<AnalyticsEnvelope<PerformanceMetrics>>(
        `/coach/athletes/${athleteId}/analytics/performance`,
      )
      .then((r) => r.data),
  trainingLoad: (athleteId: number) =>
    http
      .get<AnalyticsEnvelope<TrainingLoadMetrics>>(
        `/coach/athletes/${athleteId}/analytics/training-load`,
      )
      .then((r) => r.data),
  trends: (athleteId: number) =>
    http
      .get<AnalyticsEnvelope<TrendsMetrics>>(`/coach/athletes/${athleteId}/analytics/trends`)
      .then((r) => r.data),
  prediction: (athleteId: number) =>
    http
      .get<PredictionResponse>(`/coach/athletes/${athleteId}/predictions/2k`)
      .then((r) => r.data),
  addComment: (athleteId: number, workoutId: number, body: string) =>
    http
      .post<WorkoutComment>(
        `/coach/athletes/${athleteId}/workouts/${workoutId}/comments`,
        { body },
      )
      .then((r) => r.data),
  downloadReport: async (athleteId: number): Promise<void> => {
    const response = await http.get<Blob>(`/coach/athletes/${athleteId}/report.pdf`, {
      responseType: "blob",
    });
    const disposition = response.headers["content-disposition"] as string | undefined;
    const match = disposition?.match(/filename="([^"]+)"/);
    const filename = match?.[1] ?? "oarsight-athlete-report.pdf";
    const url = URL.createObjectURL(response.data);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  },
};

export const athleteCoachApi = {
  invitations: () =>
    http.get<CoachInvitation[]>("/athlete/coaches/invitations").then((r) => r.data),
  connected: () =>
    http.get<CoachConnection[]>("/athlete/coaches").then((r) => r.data),
  accept: (invitationId: number) =>
    http
      .post<CoachConnection>(`/athlete/coaches/invitations/${invitationId}/accept`)
      .then((r) => r.data),
  reject: (invitationId: number) =>
    http.post(`/athlete/coaches/invitations/${invitationId}/reject`).then(() => undefined),
  disconnect: (coachId: number) =>
    http.delete(`/athlete/coaches/${coachId}`).then(() => undefined),
};

export default http;
