# -*- mode: Python -*-
# Tilt orchestration voor het lokale Spark + Delta cluster.
# Volgorde: cluster-check → uv sync → pulumi stack init → pulumi up → port-forwards → dbt smoke.

# This demo runs on its own minikube profile (a dedicated cluster) named
# 'spark-demo', not the default 'minikube' profile. That keeps the cluster, its
# kube-context, and the k8s namespace all under one 'spark-demo' name and fully
# isolated from any other minikube/rancher-desktop work. The profile's
# kube-context is also called 'spark-demo'.
MINIKUBE_PROFILE = 'spark-demo'

allow_k8s_contexts(MINIKUBE_PROFILE)

# 00 — prereqs
# Ensure the 'spark-demo' minikube profile is running and is the active kube-context,
# so `tilt up` alone spins everything up from nothing — no separate `minikube start`
# step to remember. If the profile is missing or stopped, we start it here (idempotent:
# a no-op when it's already Running, so re-runs are cheap). First creation pulls images
# and can take a few minutes.
#
# We never assert on the *current* context: the host default is often
# docker-desktop/rancher-desktop, and a one-shot assertion would wedge the whole
# pipeline (no auto-retry) the moment the active context isn't ours. And we select the
# profile with `minikube update-context` rather than `kubectl config use-context`:
# Rancher Desktop actively manages ~/.kube/config and intermittently prunes the
# minikube context it doesn't own, so the context may not exist when we need it.
# `minikube update-context -p spark-demo` re-injects the entry and makes it current.
local_resource(
    'cluster-check',
    cmd="""
set -eu
P=spark-demo
if ! minikube status -p "$P" --format '{{.Host}}' 2>/dev/null | grep -q Running; then
  echo "cluster-check: minikube profile '$P' not running — starting it (first run pulls images, can take a few minutes)…"
  minikube start -p "$P" --memory=5g --cpus=2
fi
minikube update-context -p "$P" >/dev/null
kubectl get nodes >/dev/null
echo "cluster-check: minikube profile '$P' is Running and is the active kubectl context."
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

# --refresh reconciles Pulumi state with the live cluster before applying. Without
# it, if the cluster was recreated (e.g. cluster-check made a fresh profile) while
# the stack still tracks the old resources, `pulumi up` sees "no changes" and deploys
# nothing — leaving an empty namespace. --refresh detects the resources are gone and
# recreates them, so `tilt up` is self-correcting after any cluster rebuild.
local_resource(
    'pulumi-up',
    cmd=_PULUMI_ENV + ' && cd pulumi && uv run pulumi up --yes --skip-preview --refresh --stack dev --non-interactive',
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
