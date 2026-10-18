import { useState } from "react";
import { Link } from "react-router-dom";
import { JobCard } from "../components/JobCard";
import { EmptyState, ErrorState, Loading } from "../components/States";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useAsync } from "../lib/useAsync";

export function MatchesPage() {
  const { user } = useAuth();
  const [minScore, setMinScore] = useState(0);
  const [unmatched, setUnmatched] = useState(false);
  const { data, error, loading, reload } = useAsync(() => api.matches({ min_score: minScore, include_unmatched: unmatched }), [minScore, unmatched]);
  const hasProfile = !!user && (user.skills.length > 0 || user.cgpa !== null);
  return (
    <>
      <h1>My matches</h1>
      <p className="lead">
        Jobs you are eligible for (deadline, CGPA, branch, graduation year), ranked by how many of the required skills you have.
        Keep your <Link to="/profile">profile</Link> up to date for better results.
      </p>
      <div className="filters card">
        <label className="grow">
          Minimum match: <strong>{minScore}%</strong>
          <input type="range" min={0} max={100} step={10} value={minScore} onChange={(e) => setMinScore(Number(e.target.value))} />
        </label>
        <label className="check">
          <input type="checkbox" checked={unmatched} onChange={(e) => setUnmatched(e.target.checked)} />
          Include jobs with 0% skills match
        </label>
      </div>
      {loading && !data && <Loading label="Finding your matches…" />}
      {error && <ErrorState error={error} onRetry={reload} />}
      {data &&
        (data.length === 0 ? (
          <EmptyState title="No matches yet">
            {hasProfile ? "Nothing fits your profile right now. Lower the minimum match or check back after the next scrape." : "Add your skills and CGPA on your profile to see matches."}
          </EmptyState>
        ) : (
          <div className="grid">{data.map((m) => <JobCard key={m.job.id} job={m.job} score={m.score} />)}</div>
        ))}
    </>
  );
}
