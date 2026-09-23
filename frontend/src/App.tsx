import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { RoleRoute } from "./components/RoleRoute";
import { AuthProvider } from "./context/AuthContext";
import { Dashboard } from "./pages/Dashboard";
import { History } from "./pages/History";
import { Login } from "./pages/Login";
import { Performance } from "./pages/Performance";
import { Predict } from "./pages/Predict";
import { Profile } from "./pages/Profile";
import { Register } from "./pages/Register";
import { TrainingLoad } from "./pages/TrainingLoad";
import { Trends } from "./pages/Trends";
import { Upload } from "./pages/Upload";
import { WorkoutDetail } from "./pages/WorkoutDetail";
import { CoachDashboard } from "./pages/CoachDashboard";
import { CoachAthlete } from "./pages/CoachAthlete";
import { CoachConnections } from "./pages/CoachConnections";
import { useAuth } from "./context/AuthContext";

function Home() {
  const { user } = useAuth();
  return user?.role === "coach" ? <Navigate to="/coach" replace /> : <Dashboard />;
}

function AthleteOnly({ children }: { children: ReactNode }) {
  return <ProtectedRoute><RoleRoute role="athlete">{children}</RoleRoute></ProtectedRoute>;
}

function CoachOnly({ children }: { children: ReactNode }) {
  return <ProtectedRoute><RoleRoute role="coach">{children}</RoleRoute></ProtectedRoute>;
}

function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Home />
            </ProtectedRoute>
          }
        />
        <Route
          path="/upload"
          element={
            <AthleteOnly><Upload /></AthleteOnly>
          }
        />
        <Route
          path="/history"
          element={
            <AthleteOnly><History /></AthleteOnly>
          }
        />
        <Route
          path="/workouts/:id"
          element={
            <AthleteOnly><WorkoutDetail /></AthleteOnly>
          }
        />
        <Route
          path="/trends"
          element={
            <AthleteOnly><Trends /></AthleteOnly>
          }
        />
        <Route
          path="/performance"
          element={
            <AthleteOnly><Performance /></AthleteOnly>
          }
        />
        <Route
          path="/training-load"
          element={
            <AthleteOnly><TrainingLoad /></AthleteOnly>
          }
        />
        <Route path="/profile" element={<AthleteOnly><Profile /></AthleteOnly>} />
        <Route path="/coaches" element={<AthleteOnly><CoachConnections /></AthleteOnly>} />
        <Route
          path="/predict"
          element={
            <AthleteOnly><Predict /></AthleteOnly>
          }
        />
        <Route path="/coach" element={<CoachOnly><CoachDashboard /></CoachOnly>} />
        <Route path="/coach/athletes/:athleteId" element={<CoachOnly><CoachAthlete /></CoachOnly>} />
        <Route
          path="/coach/athletes/:athleteId/workouts/:id"
          element={<CoachOnly><WorkoutDetail /></CoachOnly>}
        />
      </Routes>
    </AuthProvider>
  );
}

export default App;
