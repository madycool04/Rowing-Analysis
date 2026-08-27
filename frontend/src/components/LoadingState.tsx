import type { ReactNode } from "react";

interface LoadingStateProps {
  status: "loading" | "error" | "empty";
  loadingLabel?: string;
  errorLabel?: string;
  emptyTitle?: string;
  emptyBody?: string;
  emptyAction?: ReactNode;
}

export function LoadingState({
  status,
  loadingLabel = "Loading...",
  errorLabel = "Something went wrong. Try refreshing.",
  emptyTitle = "Nothing here yet",
  emptyBody,
  emptyAction,
}: LoadingStateProps) {
  if (status === "loading") {
    return (
      <div className="inline-state">
        <span className="spinner" aria-hidden="true" />
        <p>{loadingLabel}</p>
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="inline-state inline-state--error">
        <p>{errorLabel}</p>
      </div>
    );
  }

  return (
    <div className="empty-state">
      <p className="empty-state-title">{emptyTitle}</p>
      {emptyBody && <p className="empty-state-body">{emptyBody}</p>}
      {emptyAction && <div className="empty-state-action">{emptyAction}</div>}
    </div>
  );
}
