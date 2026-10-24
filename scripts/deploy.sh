#!/usr/bin/env bash
# Copy the sources to a k3s server and deploy them there.
#   DEPLOY_HOST        required, e.g. root@your-server
#   DEPLOY_KEY         optional SSH private key (default: your SSH agent/config)
#   DEPLOY_DIR         optional install directory on the server (default: /opt/lift-ai)
#   TUNNEL_TOKEN_FILE  optional path *on the server* to a Cloudflare tunnel token
set -euo pipefail
cd "$(dirname "$0")/.."
: "${DEPLOY_HOST:?Set DEPLOY_HOST, e.g. root@your-server}"
DEPLOY_DIR="${DEPLOY_DIR:-/opt/lift-ai}"
TUNNEL_TOKEN_FILE="${TUNNEL_TOKEN_FILE:-}"
[[ "$DEPLOY_HOST" =~ ^[a-zA-Z0-9_.@:-]+$ ]] || { echo 'Invalid DEPLOY_HOST'; exit 1; }
for path in "$DEPLOY_DIR" "$TUNNEL_TOKEN_FILE"; do
  [[ -z "$path" || "$path" =~ ^/[a-zA-Z0-9_./-]+$ ]] || { echo "Invalid path: $path"; exit 1; }
done
ssh_cmd=(ssh)
[[ -n "${DEPLOY_KEY:-}" ]] && ssh_cmd+=(-i "$DEPLOY_KEY")
"${ssh_cmd[@]}" "$DEPLOY_HOST" "mkdir -p '$DEPLOY_DIR'"
tar --exclude=node_modules --exclude=.venv --exclude=.git --exclude=dist --exclude='*.db' --exclude=__pycache__ --exclude=.pytest_cache --exclude=test-results --exclude=.env -czf - frontend backend deploy scripts | "${ssh_cmd[@]}" "$DEPLOY_HOST" "tar -xzf - -C '$DEPLOY_DIR'"
"${ssh_cmd[@]}" "$DEPLOY_HOST" "TUNNEL_TOKEN_FILE='$TUNNEL_TOKEN_FILE' bash '$DEPLOY_DIR/scripts/deploy-remote.sh'"
