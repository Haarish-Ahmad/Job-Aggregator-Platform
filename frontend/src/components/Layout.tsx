import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { initials } from "../lib/format";
import { Icon, type IconName } from "./Icon";

const TABS: { to: string; label: string; icon: IconName; end?: boolean }[] = [
  { to: "/jobs", label: "Jobs", icon: "briefcase" },
  { to: "/matches", label: "My matches", icon: "target" },
  { to: "/dashboard", label: "Dashboard", icon: "chart" },
  { to: "/applications", label: "Applications", icon: "file" },
  { to: "/analytics", label: "Analytics", icon: "chart" },
];

export function Brand() {
  return (
    <span className="brand">
      <span className="brand-mark" aria-hidden="true">
        <Icon name="briefcase" size={18} />
      </span>
      Job Aggregator
    </span>
  );
}

export function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const tabs = user?.role === "admin" ? [...TABS, { to: "/admin", label: "Admin", icon: "user" as const }] : TABS;
  const mobileTabs = [...tabs, { to: "/profile", label: "Profile", icon: "user" as const }];
  return (
    <>
      <a className="skip" href="#main">
        Skip to content
      </a>
      <header className="topbar">
        <div className="topbar-inner">
          <NavLink to="/" className="brand-link" aria-label="Job Aggregator home">
            <Brand />
          </NavLink>
          <nav aria-label="Main" className="tabs">
            {tabs.map((t) => (
              <NavLink key={t.to} to={t.to} end={t.end}>
                <Icon name={t.icon} size={18} />
                {t.label}
              </NavLink>
            ))}
          </nav>
          <div className="who">
            <NavLink to="/profile" className="profile-pill" title={user?.email}>
              <Icon name="menu" size={16} />
              <span className="avatar" aria-hidden="true">
                {initials(user?.name ?? null).slice(0, 1)}
              </span>
              <span className="who-name">{user?.name}</span>
            </NavLink>
            <button
              type="button"
              className="btn ghost small"
              onClick={async () => {
                await logout();
                navigate("/login");
              }}
            >
              <Icon name="logout" size={16} />
              <span className="hide-sm">Sign out</span>
            </button>
          </div>
        </div>
      </header>
      <main id="main">
        <Outlet />
      </main>
      <footer className="foot">
        <div className="foot-inner">
          <span>© {new Date().getFullYear()} Job Aggregator</span>
          <span>Listings are collected from public job boards and company career pages. Always confirm details on the original posting.</span>
        </div>
      </footer>
      {/* Phones get a bottom tab bar instead of the header tabs. */}
      <nav aria-label="Main (mobile)" className="bottom-tabs">
        {mobileTabs.map((t) => (
          <NavLink key={t.to} to={t.to} end={t.end}>
            <Icon name={t.icon} size={22} />
            <span>{t.label}</span>
          </NavLink>
        ))}
      </nav>
    </>
  );
}
