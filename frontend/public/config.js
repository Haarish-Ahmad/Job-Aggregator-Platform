// Runtime configuration. The container rewrites this file from environment variables at start-up
// (see docker-entrypoint.sh), so one image can point at any API without a rebuild.
window.__APP_CONFIG__ = { apiBase: "/api" };
