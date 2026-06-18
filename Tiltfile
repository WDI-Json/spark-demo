# -*- mode: Python -*-
# Tilt orchestration voor het lokale Spark + Delta cluster.
# Volgorde: cluster-check → uv sync → pulumi stack init → pulumi up → port-forwards → dbt smoke.

allow_k8s_contexts('minikube')

# 00 — prereqs
# Wait (bounded) for a running minikube and point kubectl at it. We never assert
# on the *current* context: the host default is often docker-desktop/rancher-desktop,
# and a one-shot assertion would wedge the whole pipeline (no auto-retry) the moment
# the active context isn't minikube. Instead we wait for minikube to be Running, then
# select it — self-healing if the user starts minikube alongside `tilt up`.
#
# We use `minikube update-context` rather than `kubectl config use-context minikube`:
# Rancher Desktop actively manages ~/.kube/config and intermittently prunes the
# minikube context it doesn't own, so the context may not exist when we need it.
# `minikube update-context` re-injects minikube's entry and makes it current.
local_resource(
    'cluster-check',
    cmd="""
set -eu
for i in $(seq 1 30); do
  if minikube status --format '{{.Host}}' 2>/dev/null | grep -q Running; then
    minikube update-context >/dev/null
    kubectl get nodes >/dev/null
    echo "cluster-check: minikube is Running and is the active kubectl context."
    exit 0
  fi
  [ "$i" = 1 ] && echo "cluster-check: waiting for minikube — run 'minikube start' if you haven't…" >&2
  sleep 2
done
echo "cluster-check: minikube not Running after 60s. Run 'minikube start' and re-trigger." >&2
exit 1
""",
    labels=['00-prereqs'],
)

local_resource(
    'uv-sync',
    cmd='uv sync',
    deps=['pyproject.toml', 'uv.lock'],
    labels=['00-prereqs'],
)

# 10 — infra
# PULUMI_CONFIG_PASSPHRASE is required by the local backend (the stack carries an
# encryptionsalt), but this demo has no secrets — so we default it to empty here
# instead of forcing the user to remember `export PULUMI_CONFIG_PASSPHRASE=""`.
# A passphrase already set in the launching shell is respected.
_PULUMI_ENV = 'export PULUMI_CONFIG_PASSPHRASE="${PULUMI_CONFIG_PASSPHRASE:-}"'

local_resource(
    'pulumi-stack',
    cmd=_PULUMI_ENV + ' && cd pulumi && uv run pulumi login --local && (uv run pulumi stack select dev 2>/dev/null || uv run pulumi stack init dev)',
    resource_deps=['uv-sync'],
    labels=['10-infra'],
)

local_resource(
    'pulumi-up',
    cmd=_PULUMI_ENV + ' && cd pulumi && uv run pulumi up --yes --skip-preview --stack dev --non-interactive',
    deps=[
        'pulumi/__main__.py',
        'pulumi/Pulumi.yaml',
        'pulumi/Pulumi.dev.yaml',
        'spark/spark-defaults.conf',
    ],
    resource_deps=['pulumi-stack', 'cluster-check'],
    labels=['10-infra'],
)

# 20 — port-forwards (long-running, gestart na pulumi-up)
local_resource(
    'pf-master-ui',
    serve_cmd='kubectl port-forward -n spark-demo svc/spark-master 8080:8080',
    links=['http://localhost:8080'],
    resource_deps=['pulumi-up'],
    labels=['20-ports'],
)
local_resource(
    'pf-thrift',
    serve_cmd='kubectl port-forward -n spark-demo svc/spark-thrift 10000:10000',
    resource_deps=['pulumi-up'],
    labels=['20-ports'],
)
local_resource(
    'pf-connect',
    serve_cmd='kubectl port-forward -n spark-demo svc/spark-connect 15002:15002',
    resource_deps=['pulumi-up'],
    labels=['20-ports'],
)

# 30 — smoke test (handmatige trigger via Tilt-UI; geen auto-init)
local_resource(
    'dbt-smoke',
    cmd='cd dbt && uv run dbt seed --profiles-dir . && uv run dbt run --profiles-dir . && uv run dbt test --profiles-dir .',
    resource_deps=['pf-thrift'],
    trigger_mode=TRIGGER_MODE_MANUAL,
    auto_init=False,
    labels=['30-smoke'],
)
