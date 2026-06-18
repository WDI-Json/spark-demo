# spark-demo

Lokaal Spark + Delta Lake-cluster, opgezet met **Pulumi** (IaC) en **Tilt** (orchestratie) op **minikube**, plus een mini **dbt**-project en een notebook via **Spark Connect**. Bedoeld om Databricks-concepten lokaal te oefenen.

> Nieuw in deze stack? Begin bij [INTRODUCTION.md](INTRODUCTION.md) — een uitleg voor data engineers over wat dit project probeert te bereiken en hoe de stukjes in elkaar passen.

## Wat dit wel/niet is

> **Dit is geen Databricks.** Er is geen open-source Databricks-runtime; we draaien gewone Apache Spark. Wat je hier oefent is overdraagbaar, maar Databricks-specifieke lagen ontbreken.

| In | Niet in |
|---|---|
| Apache Spark 4.0.3 (master + worker) | Unity Catalog UI |
| Delta Lake (opt-in via `USING DELTA`) | Photon engine |
| Hive Thrift Server (dbt-spark via SQL) | Delta Live Tables |
| Spark Connect (notebooks zoals Databricks Connect) | Databricks Workflows / Jobs UI |
| dbt-on-Spark | MLflow-integratie |

Voor Databricks-eigen UI/features: gebruik de gratis **Databricks Community Edition** online.

## Stack

```
┌──────────────────────────────────────────────────────┐
│  tilt up                                             │
│    │                                                 │
│    ├─► pulumi up  ──► minikube (spark-demo ns)       │
│    │                    ├─ spark-master              │
│    │                    ├─ spark-worker  ×N          │
│    │                    ├─ spark-thrift   :10000     │
│    │                    └─ spark-connect  :15002     │
│    │                                                 │
│    ├─► port-forwards (8080, 10000, 15002)            │
│    └─► dbt-smoke (handmatige trigger)                │
└──────────────────────────────────────────────────────┘
```

Image: `apache/spark:4.0.3` (multi-arch, draait op M-series Mac). Master en worker zijn Spark-daemons; Thrift en Connect zijn Spark-applicaties die als driver op het cluster runnen.

## Vereisten (één keer installeren)

Brew-formulae: `pulumi`, `minikube`, `tilt`, `kubernetes-cli`, `uv`, `k9s`. Plus een werkende Docker-daemon (Rancher Desktop of Docker Desktop).

```sh
brew install pulumi minikube tilt kubernetes-cli uv k9s
```

## Eenmalige setup

```sh
git clone <deze-repo> ~/GITHUB/spark-demo
cd ~/GITHUB/spark-demo

uv sync                                       # creëert .venv/ met alle deps

minikube start -p spark-demo --memory=5g --cpus=2   # eigen 'spark-demo' cluster
                                              # (meer mag, mits je docker-daemon
                                              # voldoende resources heeft)

export PULUMI_CONFIG_PASSPHRASE=""            # geen secrets in deze demo
pulumi login --local                          # state in ~/.pulumi/, geen account
cd pulumi && uv run pulumi stack init dev && cd ..
```

## Dagelijks gebruik

```sh
minikube start -p spark-demo    # als hij nog niet draait
tilt up                         # browser opent http://localhost:10350
```

> Deze demo draait op een **eigen minikube-profiel** `spark-demo` (een aparte
> cluster), niet op het default `minikube`-profiel. Zo heten de cluster, de
> kube-context én de namespace allemaal `spark-demo` en staat alles los van ander
> minikube/rancher-desktop-werk.
>
> `cluster-check` wacht zelf tot het `spark-demo`-profiel draait en zet de
> kubectl-context erop (ook als je default-context `docker-desktop`/`rancher-desktop`
> is). De `PULUMI_CONFIG_PASSPHRASE=""` wordt door Tilt zelf gezet — geen handmatige
> export meer nodig voor `tilt up`.

Wacht tot alle resources groen zijn in de Tilt-UI:

| Resource | Wat |
|---|---|
| `cluster-check` | Sanity: profiel `spark-demo` draait en is de actieve context |
| `uv-sync` | venv up-to-date |
| `pulumi-stack` / `pulumi-up` | K8s-resources applied |
| `pf-master-ui` | Port-forward 8080 → master web UI |
| `pf-thrift` | Port-forward 10000 → Thrift (dbt) |
| `pf-connect` | Port-forward 15002 → Spark Connect (notebooks) |
| `dbt-smoke` | **Handmatig** — klik op play in Tilt om te draaien |

### Endpoints

| URL | Wat |
|---|---|
| <http://localhost:10350> | Tilt-dashboard |
| <http://localhost:8080>  | Spark master UI |
| `localhost:10000`        | Hive Thrift (dbt) |
| `localhost:15002`        | Spark Connect (notebooks) |

### Smoke-test

In de Tilt-UI bij `dbt-smoke` op het play-icoon klikken. Dit draait:

```sh
dbt seed && dbt run && dbt test
```

Verwacht resultaat: seed `PASS 1/1`, run `PASS 2/2`, test `PASS 6/6`. Tabellen `orders`, `stg_orders`, `revenue_per_day` worden als Parquet aangemaakt door de Thrift Server.

### Notebook

Open `notebooks/01_hello_spark.ipynb` in VS Code. De Jupyter-extensie pakt automatisch `.venv/` als kernel. De eerste cel verbindt via Spark Connect en print de Spark-versie.

> **Let op:** Spark Connect en Spark Thrift draaien als gescheiden Spark-applicaties met elk een eigen in-memory catalog. Tabellen die `dbt-smoke` via Thrift maakt, zie je dus **niet** in de notebook. Voor gedeelde state heb je een Hive Metastore nodig (zie v2 hieronder). Het meegeleverde notebook is daarom self-contained.

## Cluster bekijken (kubectl / k9s)

```sh
kubectl get all -n spark-demo
kubectl logs -n spark-demo deploy/spark-master -f
kubectl describe pod -n spark-demo -l app=spark-thrift
k9s -n spark-demo                    # TUI
```

Architectuur in drie zoom-niveaus (C4-model): [docs/architecture.md](docs/architecture.md).

Per-deployment uitleg in `docs/`:

| Component | Doc |
|---|---|
| Master | [docs/spark-master.md](docs/spark-master.md) |
| Worker | [docs/spark-worker.md](docs/spark-worker.md) |
| Thrift Server | [docs/spark-thrift.md](docs/spark-thrift.md) |
| Connect Server | [docs/spark-connect.md](docs/spark-connect.md) |

Per-directory README's: [pulumi/](pulumi/README.md), [spark/](spark/README.md), [dbt/](dbt/README.md), [notebooks/](notebooks/README.md).

## Opruimen

```sh
tilt down                                       # stopt port-forwards
minikube update-context -p spark-demo           # PIN de kubectl-context op spark-demo
cd pulumi && PULUMI_CONFIG_PASSPHRASE="" uv run pulumi destroy --yes
minikube stop -p spark-demo                      # of: minikube delete -p spark-demo
```

> **Let op — `minikube update-context -p spark-demo` is geen detail.** `pulumi
> destroy` werkt tegen je *huidige* kubectl-context. Staat die op
> `docker-desktop`/`rancher-desktop` (vaak de default), dan verwijdert destroy de
> resources uit de **verkeerde** cluster als no-op, gooit ze uit de Pulumi-state, en
> laten de échte pods verweesd achter — een latere `pulumi up`/`tilt up` botst dan op
> bestaande namen.
>
> Verweesde boel toch te pakken? Pin de context en sloop de namespace direct:
>
> ```sh
> minikube update-context -p spark-demo && kubectl delete namespace spark-demo
> ```
>
> Voor een **clean restart** is het hele profiel weggooien het zekerst — dan kan er
> aan *cluster*-kant niets verweesd achterblijven:
>
> ```sh
> minikube delete -p spark-demo        # wist de hele spark-demo cluster
> ```
>
> **Let op:** als je het profiel weggooit *zonder* eerst `pulumi destroy` te draaien,
> blijft de Pulumi-state de (nu verdwenen) resources nog "kennen". Een volgende
> `tilt up` denkt dan dat alles al bestaat en maakt niets opnieuw aan. Reset daarom
> ook de stack-state:
>
> ```sh
> cd pulumi
> PULUMI_CONFIG_PASSPHRASE="" uv run pulumi stack rm dev --yes --force
> git checkout -- Pulumi.dev.yaml          # stack rm verwijdert dit config-bestand
> PULUMI_CONFIG_PASSPHRASE="" uv run pulumi stack init dev   # lege state, klaar voor tilt up
> ```
>
> Draai je netjes `pulumi destroy` vóór `minikube delete` (zoals hierboven), dan is
> deze reset niet nodig — dan loopt state en cluster gelijk leeg.

## Resources & geheugen

- Minikube: `--memory=5g --cpus=2` is minimaal werkend op een Rancher-Docker-daemon van 6 GB.
- Per Spark-applicatie staat ingesteld: `cores.max=1`, `executor.cores=1`, `executor.memory=512m` (in `spark/spark-defaults.conf`). Zonder die limieten grijpt de eerste app (thrift) alle worker-cores en hangt connect zonder executor.
- Bij meer cluster-resources (workermemory + cores omhoog in `pulumi/Pulumi.dev.yaml`) kun je deze limieten verhogen.

## Bekende beperkingen & v2

Niet in v1, gemakkelijk toe te voegen door Pulumi-bestanden uit te breiden:

- **Hive Metastore + PostgreSQL** — gedeelde catalog zodat Connect en Thrift dezelfde tabellen zien (en dichter bij Unity-Catalog-gevoel). Dit is de meest impactvolle v2-toevoeging.
- **MinIO** als S3-compat object storage (Delta tables op object storage i.p.v. emptyDir/`/tmp`).
- **Persistent Volume Claims** zodat tabellen pod-restarts overleven.
- **Delta-catalog default** — kan aan zodra de Hive Metastore er is; nu uit omdat dbt-spark anders class-loader-issues krijgt.
- **Meerdere workers** met autoscaling-demo.

## Verzwakkingen ten opzichte van Databricks

Naast wat hierboven al staat:

- `spark.cores.max=1` betekent dat één query exclusief één core gebruikt — geen parallelisme binnen één query.
- Geen historie-server (Spark History Server) voor afgesloten apps.
- Geen UI authenticatie — alles open op localhost.
