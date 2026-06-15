#!/usr/bin/env bash
# Manual deploy helper. CI runs the same pull+run over SSH via deploy.apply_recipe; this is the
# hands-on equivalent: ./deploy/deploy.sh <image-tag> on a host that can reach the registry.
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "usage: deploy.sh <image-tag>" >&2
  exit 1
fi

image="${registry.image_name_base}:$1"

${container.runtime} pull "$image"
${container.runtime} rm -f ${container.image_name} 2>/dev/null || true
${container.runtime} run -d --restart=always --name ${container.image_name} -p 80:${container.exposed_port} "$image"
