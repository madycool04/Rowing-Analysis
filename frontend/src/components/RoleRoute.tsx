import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export function RoleRoute({ role, children }: { role: "athlete" | "coach"; children: ReactNode }) {
  const { user } = useAuth();
  if (!user) return null;
  if (user.role !== role) return <Navigate to={user.role === "coach" ? "/coach" : "/"} replace />;
  return <>{children}</>;
}
