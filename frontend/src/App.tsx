import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Loading } from "./components/States";
import { useAuth } from "./lib/auth";
import { AnalyticsPage } from "./pages/Analytics";
import { LoginPage, RegisterPage } from "./pages/Auth";
import { HomePage } from "./pages/Home";
import { JobDetailPage } from "./pages/JobDetail";
import { ListingsPage } from "./pages/Listings";
import { MatchesPage } from "./pages/Matches";
import { ProfilePage } from "./pages/Profile";

function RequireAuth() {
  const { user, checking } = useAuth();
  const location = useLocation();
  if (checking) return <Loading label="Checking your session…" />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  return <Layout />;
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route index element={<HomePage />} />
      <Route element={<RequireAuth />}>
        <Route path="jobs" element={<ListingsPage />} />
        <Route path="jobs/:id" element={<JobDetailPage />} />
        <Route path="matches" element={<MatchesPage />} />
        <Route path="profile" element={<ProfilePage />} />
        <Route path="analytics/*" element={<AnalyticsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
