import { Link } from "react-router-dom";
import { JobCard } from "../components/JobCard";
import { EmptyState, ErrorState, Loading } from "../components/States";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useAsync } from "../lib/useAsync";

export function MatchesPage() {
  const { user } = useAuth();
  const { data, error, loading, reload } = useAsync(() => api.matches(), []);
  const hasProfile = !!user && (user.skills.length > 0 || user.cgpa !== null);
  return (
    <>
      <section className="page-head">
        <h1>My matches</h1>
        <p className="lead">
          Jobs you are eligible for (deadline, CGPA, branch, graduation year), ranked by how many of the required skills you have.
          Keep your <Link to="/profile">profile</Link> up to date for better results.
        </p>
      </section>
      {loading && !data && <Loading label="Finding your matches…" />}
      {error && <ErrorState error={error} onRetry={reload} />}
      {data &&
        (data.length === 0 ? (
          <EmptyState title="No matches yet">
            {hasProfile ? "Nothing fits your profile right now. Check back after the next scrape." : "Add your skills and CGPA on your profile to see matches."}
          </EmptyState>
        ) : (
          <div className="grid">{data.map((m) => <JobCard key={m.job.id} job={m.job} score={m.score} />)}</div>
        ))}
    </>
  );
}
