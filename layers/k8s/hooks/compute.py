#!/usr/bin/env python3
"""k8s compute hook: provide deploy.url honestly — empty when there is no ingress host.

deploy.url is a public capability the notify slot appends to its message. k8s only has a URL when
an ingress host is configured; with the default (no host) it must be "", not "https://" with a
dangling scheme (#43). The engine's ${...} tier carries no conditional, so this is the sanctioned
escape hatch (docs/lifecycle §1): a host yields https://<host>, no host yields "". vps-ssh provides
the same "" declaratively when it has no public URL.
"""

from __future__ import annotations

import json
import os


def main() -> None:
    host = os.environ.get("INITREE_DEPLOY_K8S_HOST", "").strip()
    print(json.dumps({"deploy.url": f"https://{host}" if host else ""}))


if __name__ == "__main__":
    main()
