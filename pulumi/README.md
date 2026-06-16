# pulumi/

Infrastructure-as-Code voor het lokale Spark-cluster. Python-runtime, Kubernetes-provider, lokale state.

## Structuur

| Bestand | Wat | Taal |
|---|---|---|
| `Pulumi.yaml` | Project-metadata: naam, runtime, venv-pad | YAML |
| `Pulumi.dev.yaml` | Stack-config voor de `dev`-stack (image-tag, worker-grootte) | YAML |
| `__main__.py` | De daadwerkelijke infra-definitie | **Python** |

Pulumi-projecten hebben altijd een `Pulumi.yaml`-metadata-bestand, ongeacht de gekozen taal. De échte code staat in `__main__.py`.

## Wat creëert dit programma

Eén `spark-demo` namespace met daarin:

- 1 ConfigMap `spark-conf` (mount op `/opt/bitnami/spark/conf/spark-defaults.conf` in alle pods)
- 4 Deployments: `spark-master`, `spark-worker`, `spark-thrift`, `spark-connect`
- 3 Services: `spark-master` (7077 + 8080), `spark-thrift` (10000), `spark-connect` (15002)

Per-deployment uitleg staat in `../docs/`.

## Commands (vanuit `pulumi/`)

```sh
uv run pulumi login --local              # eenmalig — geen Pulumi Cloud
uv run pulumi stack init dev             # eenmalig — stack aanmaken
uv run pulumi up --yes                   # apply
uv run pulumi preview                    # diff zonder apply
uv run pulumi destroy --yes              # cluster opruimen
uv run pulumi stack output               # toon exports (port-forward commands)
```

Tilt voert `pulumi up` automatisch uit; rechtstreeks aanroepen kan ook.

## State

`pulumi login --local` zet de state in `~/.pulumi/`. Geen account nodig, niets gaat naar buiten. Switchen naar Pulumi Cloud kan altijd via `pulumi login` (zonder `--local`).
