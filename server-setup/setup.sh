#!/usr/bin/env bash
# Prepare this machine as the server. Run once, as your normal user (not with sudo):  bash setup.sh
set -euo pipefail

REPO=Haarish-Ahmad/Job-Aggregator-Platform
RUNNER_VERSION=2.338.2
RUNNER_SHA256=baebf204307bac6193480852732f0aba2ae97b6c5597c244f4d5558390147c40   # linux-x64, from GitHub's release notes
SERVER_DIR=$HOME/job-aggregator
RUNNER_DIR=$SERVER_DIR/actions-runner

[ "$(id -u)" -ne 0 ] || { echo "Run this as your normal user, not with sudo."; exit 1; }
[ "$(uname -m)" = x86_64 ] || { echo "This script expects a 64-bit Intel or AMD machine."; exit 1; }

echo "==> Installing git and Docker"
sudo apt-get update -qq
sudo apt-get install -y -qq ca-certificates curl git openssl >/dev/null
command -v docker >/dev/null || curl -fsSL https://get.docker.com | sudo sh
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"

echo "==> Keeping the laptop awake with the lid closed"
sudo mkdir -p /etc/systemd/logind.conf.d
printf '[Login]\nHandleLidSwitch=ignore\nHandleLidSwitchExternalPower=ignore\n' |
  sudo tee /etc/systemd/logind.conf.d/job-aggregator.conf >/dev/null
sudo systemctl kill -s HUP systemd-logind
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target >/dev/null 2>&1

echo "==> Creating the settings file with new random passwords"
mkdir -p "$SERVER_DIR"
if [ ! -f "$SERVER_DIR/deploy.env" ]; then
  ip=$(hostname -I | awk '{print $1}')
  (
    umask 077
    cat > "$SERVER_DIR/deploy.env" <<ENV
POSTGRES_PASSWORD=$(openssl rand -hex 24)
SECRET_KEY=$(openssl rand -hex 24)
INGEST_TOKEN=$(openssl rand -hex 24)
GRAFANA_ADMIN_PASSWORD=$(openssl rand -hex 24)
PUBLIC_URL=http://$ip
CORS_ORIGINS=http://$ip
ENV
  )
fi

echo "==> Connecting this machine to GitHub"
mkdir -p "$RUNNER_DIR"
cd "$RUNNER_DIR"
if [ -f .runner ]; then
  sudo ./svc.sh stop >/dev/null 2>&1 || true
  sudo ./svc.sh start >/dev/null             # restarted so it gets its Docker access
else
  echo "Open https://github.com/$REPO/settings/actions/runners/new"
  read -rsp 'Copy the token from the "./config.sh --url ... --token" line and paste it here (hidden): ' token
  echo
  archive=actions-runner-linux-x64-$RUNNER_VERSION.tar.gz
  curl -fsSL -o "$archive" "https://github.com/actions/runner/releases/download/v$RUNNER_VERSION/$archive"
  echo "$RUNNER_SHA256  $archive" | sha256sum -c --quiet -
  tar xzf "$archive"
  rm "$archive"
  sudo ./bin/installdependencies.sh >/dev/null
  ./config.sh --unattended --url "https://github.com/$REPO" --token "$token" \
    --name "$(hostname)" --labels job-aggregator --work _work --replace
  sudo ./svc.sh install "$USER" >/dev/null
  sudo ./svc.sh start >/dev/null
fi

cat <<MSG

Done. Now finish on github.com:
 1. https://github.com/$REPO/settings/variables/actions
    Add the repository variable  DEPLOY_ENABLED = true
 2. https://github.com/$REPO/settings/actions
    Choose "Require approval for all external contributors"
 3. Push to main, or press "Run workflow" on the Release workflow, to start the site.
MSG
