#!/bin/sh
set -eu
CONFIG=/var/lib/kai-agent/config.json
STATE=/var/lib/kai-agent/leases.json
ssh-keygen -A
/usr/sbin/sshd
if [ ! -f "$CONFIG" ]; then
  : "${KAI_API_URL:?KAI_API_URL is required}"
  : "${KAI_ENROLLMENT_TOKEN:?KAI_ENROLLMENT_TOKEN is required for first start}"
  echo "Detected hardware (this is what KAI will verify):"
  kai-agent inventory
  echo "SSH service check:"
  kai-agent check
  kai-agent enroll --api-url "$KAI_API_URL" --token "$KAI_ENROLLMENT_TOKEN" --config "$CONFIG"
fi
exec kai-agent run --config "$CONFIG" --state "$STATE"
