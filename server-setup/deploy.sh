#!/usr/bin/env bash
# Start or update Firecrawl and the app on this machine. GitHub runs this on every push to main.
set -euo pipefail

FIRECRAWL_VERSION=v2.11.454   # change this and push to upgrade Firecrawl
SERVER_DIR=$HOME/job-aggregator
REPO_DIR=$(cd "$(dirname "$0")/.." && pwd)
export IMAGE_TAG=sha-${GITHUB_SHA::7}   # the images Release just published for this commit

echo "==> Firecrawl $FIRECRAWL_VERSION"
[ -d "$SERVER_DIR/firecrawl" ] ||
  git clone --quiet --depth 1 --branch "$FIRECRAWL_VERSION" https://github.com/firecrawl/firecrawl.git "$SERVER_DIR/firecrawl"
cd "$SERVER_DIR/firecrawl"
build=()
if [ "$(cat .deployed-version 2>/dev/null || true)" != "$FIRECRAWL_VERSION" ]; then
  git fetch --quiet --depth 1 origin "refs/tags/$FIRECRAWL_VERSION:refs/tags/$FIRECRAWL_VERSION"
  git checkout --quiet --force --detach "$FIRECRAWL_VERSION"
  build=(--build)   # the first build can take a long time
fi
# Firecrawl has no login: publish it only on Docker's own network, where the scraper reaches it.
printf 'PORT=%s:3002\n' "$(docker network inspect bridge -f '{{(index .IPAM.Config 0).Gateway}}')" > .env
# Firecrawl has no restart policy: without this it stays down after a reboot.
cat > docker-compose.override.yaml <<'YAML'
services:
  api: { restart: unless-stopped }
  playwright-service: { restart: unless-stopped }
  redis: { restart: unless-stopped }
  rabbitmq: { restart: unless-stopped }
  nuq-postgres: { restart: unless-stopped }
  foundationdb: { restart: unless-stopped }
YAML
docker compose up -d "${build[@]}"
echo "$FIRECRAWL_VERSION" > .deployed-version

echo "==> The app, version $IMAGE_TAG"
# Run from a fixed folder: the running containers read their monitoring settings from here.
mkdir -p "$SERVER_DIR/app"
cp "$REPO_DIR/docker-compose.yml" "$REPO_DIR/docker-compose.prod.yml" "$SERVER_DIR/app/"
cp -R "$REPO_DIR/monitoring" "$SERVER_DIR/app/"
cd "$SERVER_DIR/app"
compose() { docker compose --env-file ../deploy.env -f docker-compose.yml -f docker-compose.prod.yml "$@"; }
compose pull --quiet
compose up -d --remove-orphans --wait --wait-timeout 420   # fails if a service does not become healthy
compose restart prometheus grafana                         # pick up any changed monitoring settings

# Each deploy adds images: remove the older ones so the disk does not fill up.
docker images --format '{{.Repository}}:{{.Tag}}' | grep -F 'job-aggregator-platform-' | grep -vF ":$IMAGE_TAG" |
  xargs -r docker rmi >/dev/null 2>&1 || true
compose ps --format 'table {{.Service}}\t{{.Status}}'
