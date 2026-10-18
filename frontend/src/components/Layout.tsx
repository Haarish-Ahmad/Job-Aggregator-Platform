import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";

export function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  return (
    <>
      <a className="skip" href="#main">
        Skip to content
      </a>
      <header className="topbar">
        <NavLink to="/" className="brand">
          Job Aggregator
        </NavLink>
        <nav aria-label="Main">
          <NavLink to="/" end>
            Jobs
          </NavLink>
          <NavLink to="/matches">My matches</NavLink>
          <NavLink to="/analytics">Analytics</NavLink>
          <NavLink to="/profile">Profile</NavLink>
        </nav>
        <div className="who">
          <span title={user?.email}>{user?.name}</span>
          <button
            type="button"
            className="btn small"
            onClick={async () => {
              await logout();
              navigate("/login");
            }}
          >
            Sign out
          </button>
        </div>
      </header>
      <main id="main">
        <Outlet />
      </main>
      <footer className="foot">Listings are collected from public job boards and company career pages. Always confirm details on the original posting.</footer>
    </>
  );
}
