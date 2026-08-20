#!/usr/bin/env bash
set -euo pipefail

AGENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST_DIR="${AGENT_DIR}/dist"
VERSION="${KAI_AGENT_VERSION:-0.3.0}"
mkdir -p "${DIST_DIR}"

build() {
  local os="$1" arch="$2" name="$3"
  echo "building ${name}"
  (cd "${AGENT_DIR}" && CGO_ENABLED=0 GOOS="${os}" GOARCH="${arch}" \
    go build -trimpath -ldflags="-s -w -X main.version=${VERSION}" -o "${DIST_DIR}/${name}" .)
}

build linux amd64 kai-agent-linux-amd64
build linux arm64 kai-agent-linux-arm64
build windows amd64 kai-agent-windows-amd64.exe
build windows arm64 kai-agent-windows-arm64.exe
chmod 0755 "${DIST_DIR}/kai-agent-linux-amd64" "${DIST_DIR}/kai-agent-linux-arm64"

tar -C "${AGENT_DIR}" \
  --exclude='./dist' \
  --exclude='./.git' \
  -czf "${DIST_DIR}/kai-agent-docker-context.tar.gz" \
  Dockerfile docker-compose.yml go.mod main.go inventory.go service_checks.go operations_linux.go docker

echo "KAI Agent ${VERSION} artifacts are in ${DIST_DIR}"
