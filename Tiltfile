# -*- mode: Python -*-
# Tilt orchestration voor het lokale Spark + Delta cluster.
# Volgorde: cluster-check → uv sync → pulumi stack init → pulumi up → port-forwards → dbt smoke.

allow_k8s_contexts('minikube')

# 00 — prereqs
local_resource(
    'cluster-check',
    cmd="kubectl config current-context | grep -q '^minikube$' && kubectl get nodes >/dev/null",
    labels=['00-prereqs'],
)

local_resource(
    'uv-sync',
    cmd='uv sync',
    deps=['pyproject.toml', 'uv.lock'],
    labels=['00-prereqs'],
)

# 10 — infra
local_resource(
    'pulumi-stack',
    cmd='cd pulumi && (uv run pulumi stack select dev 2>/dev/null || uv run pulumi stack init dev)',
    resource_deps=['uv-sync'],
    labels=['10-infra'],
)

local_resource(
    'pulumi-up',
    cmd='cd pulumi && uv run pulumi up --yes --skip-preview --stack dev --non-interactive',
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
