import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

const NAV_ITEMS = [
  { to: "/", label: "Dashboard" },
  { to: "/upload", label: "Add Workout" },
  { to: "/profile", label: "Profile" },
  { to: "/history", label: "History" },
  { to: "/trends", label: "Trends" },
  { to: "/performance", label: "Performance" },
  { to: "/training-load", label: "Training Load" },
  { to: "/predict", label: "2K Prediction" },
];

export function Layout({ children }: { children: ReactNode }) {
  const { athlete, logout } = useAuth();

  return (
    <div className="layout">
      <aside className="layout-sidebar">
        <div className="brand">Rowing Performance Analytics</div>
        <nav className="layout-nav">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) => "nav-link" + (isActive ? " nav-link--active" : "")}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="layout-footer">
          <div className="athlete-chip">{athlete?.name ?? "Athlete"}</div>
          <button className="btn-link" onClick={logout} type="button">
            Log out
          </button>
        </div>
      </aside>
      <div className="layout-content">{children}</div>
    </div>
  );
}
