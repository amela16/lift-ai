#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v k3s >/dev/null || { echo 'Install k3s first; see README.'; exit 1; }
# Docker is an image builder only; Kubernetes/containerd runs the application.
docker build -t lift-ai-backend:1 backend
docker build -t lift-ai-frontend:1 frontend
docker save lift-ai-backend:1 lift-ai-frontend:1 | k3s ctr images import -
k3s kubectl create namespace lift-ai --dry-run=client -o yaml | k3s kubectl apply -f -
if ! k3s kubectl -n lift-ai get secret database >/dev/null 2>&1; then
  python3 - <<'PY' | k3s kubectl apply -f -
import json,secrets,base64
password=secrets.token_urlsafe(32)
print(json.dumps({'apiVersion':'v1','kind':'Secret','metadata':{'name':'database','namespace':'lift-ai'},'type':'Opaque','data':{k:base64.b64encode(v.encode()).decode() for k,v in {'password':password,'url':f'postgresql+psycopg://lift:{password}@postgres:5432/lift'}.items()}}))
PY
fi
k3s kubectl apply -f deploy/kubernetes.yaml
k3s kubectl apply -f deploy/ollama.yaml
k3s kubectl -n lift-ai rollout status deployment/ollama --timeout=300s
k3s kubectl -n lift-ai exec deployment/ollama -- ollama pull qwen2.5:0.5b >/dev/null
# Optional Cloudflare named tunnel. The token is read from TUNNEL_TOKEN_FILE once and kept as a secret.
if [ -n "${TUNNEL_TOKEN_FILE:-}" ]; then
  [ -s "$TUNNEL_TOKEN_FILE" ] || { echo "TUNNEL_TOKEN_FILE is missing or empty"; exit 1; }
  k3s kubectl -n lift-ai create secret generic cloudflare-tunnel --from-literal=token="$(tr -d ' \r\n' < "$TUNNEL_TOKEN_FILE")" --dry-run=client -o yaml | k3s kubectl apply -f - >/dev/null
fi
if k3s kubectl -n lift-ai get secret cloudflare-tunnel >/dev/null 2>&1; then
  k3s kubectl apply -f deploy/cloudflare-tunnel.yaml
fi
k3s kubectl -n lift-ai rollout restart deployment/backend deployment/frontend
k3s kubectl -n lift-ai rollout status deployment/postgres --timeout=180s
k3s kubectl -n lift-ai rollout status deployment/backend --timeout=180s
k3s kubectl -n lift-ai rollout status deployment/frontend --timeout=180s
