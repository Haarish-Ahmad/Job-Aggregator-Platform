#!/bin/sh
# Writes the runtime config the SPA reads (window.__APP_CONFIG__). API_BASE defaults to the same-origin /api.
set -eu
API_BASE="${API_BASE:-/api}"
# Allow only a path or an http(s) URL; anything else would end up inside a <script>.
case "$API_BASE" in
  /*|http://*|https://*) ;;
  *) echo "API_BASE must be a path (/api) or an http(s) URL, got: $API_BASE" >&2; exit 1 ;;
esac
case "$API_BASE" in *\"*|*\\*|*\<*|*\>*|*\ *) echo "API_BASE contains forbidden characters" >&2; exit 1 ;; esac
printf 'window.__APP_CONFIG__ = { apiBase: "%s" };\n' "$API_BASE" > /usr/share/nginx/html/config.js
