import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { initials } from "../lib/format";
import { Icon, type IconName } from "./Icon";

// Header links: text only, centred. "end" keeps Home from matching every page.
const NAV: { to: string; label: string; end?: boolean }[] = [
  { to: "/", label: "Home", end: true },
  { to: "/jobs", label: "Jobs" },
  { to: "/matches", label: "My matches" },
  { to: "/applications", label: "Applications" },
  { to: "/analytics", label: "Analytics" },
];
// Phones get a bottom tab bar instead of the header links (the logo goes Home).
const MOBILE_TABS: { to: string; label: string; icon: IconName }[] = [
  { to: "/jobs", label: "Jobs", icon: "briefcase" },
  { to: "/matches", label: "My matches", icon: "target" },
  { to: "/applications", label: "Applications", icon: "bookmark" },
  { to: "/analytics", label: "Analytics", icon: "chart" },
  { to: "/profile", label: "Profile", icon: "user" },
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

/** The one site header, used by the signed-in pages (via Layout) and the public home page. */
export function SiteHeader() {
  const { user, checking, logout } = useAuth();
  const navigate = useNavigate();
  const onHome = useLocation().pathname === "/";
  return (
    <header className="topbar">
      <div className="topbar-inner">
        <NavLink to="/" className="brand-link" aria-label="Job Aggregator home">
          <Brand />
        </NavLink>
        <nav aria-label="Main" className="tabs">
          {NAV.map((t) => (
            <NavLink key={t.to} to={t.to} end={t.end}>
              {t.label}
            </NavLink>
          ))}
        </nav>
        <div className="who">
          {checking ? null : user ? (
            <>
              <NavLink to="/profile" className="profile-pill" title={user.email}>
                <Icon name="menu" size={16} />
                <span className="avatar" aria-hidden="true">
                  {initials(user.name).slice(0, 1)}
                </span>
                <span className="who-name">{user.name}</span>
              </NavLink>
              <button
                type="button"
                className="btn ghost small"
                onClick={async () => {
                  await logout();
                  // The home page is public, so signing out there just stays on it.
                  if (!onHome) navigate("/login");
                }}
              >
                <Icon name="logout" size={16} />
                <span className="hide-sm">Sign out</span>
              </button>
            </>
          ) : (
            <>
              <Link to="/login" className="btn ghost small">Log in</Link>
              <Link to="/register" className="btn primary small">Sign up</Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}

export function BottomTabs() {
  return (
    <nav aria-label="Main (mobile)" className="bottom-tabs">
      {MOBILE_TABS.map((t) => (
        <NavLink key={t.to} to={t.to}>
          <Icon name={t.icon} size={22} />
          <span>{t.label}</span>
        </NavLink>
      ))}
    </nav>
  );
}

export function Layout() {
  return (
    <>
      <a className="skip" href="#main">
        Skip to content
      </a>
      <SiteHeader />
      <main id="main">
        <Outlet />
      </main>
      <footer className="foot">
        <div className="foot-inner">
          <span>© {new Date().getFullYear()} Job Aggregator</span>
          <span>Listings are collected from public job boards and company career pages. Always confirm details on the original posting.</span>
        </div>
      </footer>
      <BottomTabs />
    </>
  );
}
