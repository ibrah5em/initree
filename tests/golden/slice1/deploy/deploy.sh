#!/usr/bin/env bash
# Manual deploy helper. CI runs the same pull+run over SSH via deploy.apply_recipe; this is the
# hands-on equivalent: ./deploy/deploy.sh <image-tag> on a host that can reach the registry.
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "usage: deploy.sh <image-tag>" >&2
  exit 1
fi

image="ghcr.io/your-org/myapp:$1"

docker pull "$image"
docker rm -f myapp 2>/dev/null || true
docker run -d --restart=always --name myapp -p 80:8000 "$image"
