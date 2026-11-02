import type { ReactNode } from "react";
import { ApiError } from "../lib/api";
import { Icon } from "./Icon";

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="state" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      {label}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="state empty">
      <span className="state-icon" aria-hidden="true">
        <Icon name="search" size={26} />
      </span>
      <strong>{title}</strong>
      {children && <p>{children}</p>}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  const forbidden = error instanceof ApiError && error.status === 403;
  return (
    <div className="state error" role="alert">
      <strong>{forbidden ? "Not available for your account" : "Something went wrong"}</strong>
      <p>{error.message}</p>
      {onRetry && !forbidden && (
        <button type="button" className="btn" onClick={onRetry}>
          <Icon name="refresh" size={16} />
          Try again
        </button>
      )}
    </div>
  );
}
