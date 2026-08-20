#!/usr/bin/env bash
set -euo pipefail

API_URL=""
TOKEN=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --api-url) API_URL="${2:-}"; shift 2 ;;
    --token) TOKEN="${2:-}"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ -n "${API_URL}" && -n "${TOKEN}" ]] || { echo "--api-url and --token are required" >&2; exit 2; }
[[ "$(id -u)" == "0" ]] || { echo "run this installer as root" >&2; exit 1; }

case "$(uname -m)" in
  x86_64|amd64) ARCH="amd64" ;;
  aarch64|arm64) ARCH="arm64" ;;
  *) echo "unsupported architecture: $(uname -m)" >&2; exit 1 ;;
esac

install -d -m 0700 /etc/kai-agent /var/lib/kai-agent
curl -fL "${API_URL%/}/api/v1/agent/downloads/linux/${ARCH}" -o /usr/local/bin/kai-agent
chmod 0755 /usr/local/bin/kai-agent
echo "Detected hardware (this is what KAI will verify):"
/usr/local/bin/kai-agent inventory

if ! command -v sshd >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y openssh-server
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y openssh-server
  elif command -v yum >/dev/null 2>&1; then
    yum install -y openssh-server
  else
    echo "OpenSSH Server is required; install sshd and rerun this installer." >&2
    exit 1
  fi
fi
ssh-keygen -A
if command -v systemctl >/dev/null 2>&1; then
  # Debian/Ubuntu expose sshd.service as an alias of ssh.service. Enabling an
  # alias fails even though `systemctl list-unit-files sshd.service` succeeds,
  # so prefer the real ssh.service unit when it exists.
  if systemctl list-unit-files ssh.service --no-legend 2>/dev/null \
      | grep -q '^ssh\.service[[:space:]]'; then
    systemctl enable --now ssh
  elif systemctl list-unit-files sshd.service --no-legend 2>/dev/null \
      | grep -q '^sshd\.service[[:space:]]'; then
    systemctl enable --now sshd
  else
    echo "Unable to locate ssh.service or sshd.service." >&2
    exit 1
  fi
elif ! pgrep -x sshd >/dev/null 2>&1; then
  "$(command -v sshd)"
fi
echo "SSH service check (this must succeed before enrollment):"
/usr/local/bin/kai-agent check
/usr/local/bin/kai-agent enroll --api-url "${API_URL}" --token "${TOKEN}" --config /etc/kai-agent/config.json

if command -v systemctl >/dev/null 2>&1; then
  install -m 0644 /dev/stdin /etc/systemd/system/kai-agent.service <<'UNIT'
[Unit]
Description=KAI restricted SSH lease agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/kai-agent run --config /etc/kai-agent/config.json --state /var/lib/kai-agent/leases.json
Restart=always
RestartSec=5
NoNewPrivileges=false
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/etc/kai-agent /var/lib/kai-agent /home /etc/passwd /etc/shadow /etc/group /etc/gshadow /etc/subuid /etc/subgid /var/log

[Install]
WantedBy=multi-user.target
UNIT
  systemctl daemon-reload
  systemctl enable --now kai-agent
  echo "KAI Agent installed and started with systemd."
else
  echo "Agent enrolled. Start it with: sudo /usr/local/bin/kai-agent run"
fi
