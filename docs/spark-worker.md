# spark-worker

Compute-node. Verbindt met de master en draait taken (executors) die door applicaties (Thrift, Connect, eigen jobs) worden ingediend.

## Image & command

| | |
|---|---|
| Image | `apache/spark:4.0.3` |
| Command | `SPARK_NO_DAEMONIZE=1 exec /opt/spark/sbin/start-worker.sh --memory 2g --cores 2 spark://spark-master:7077` |

## Env-vars

- `POD_IP` → K8s `fieldRef: status.podIP`
- `SPARK_LOCAL_IP=$(POD_IP)` → worker adverteert zijn pod-IP

## Resources

Configurabel via stack-config (`pulumi/Pulumi.dev.yaml`):

| Config-key | Default | Doel |
|---|---|---|
| `workerReplicas` | `1` | Aantal worker-pods |
| `workerMemory` | `2g` | Geheugen per worker |
| `workerCores` | `2` | Cores per worker |

Aanpassen en `tilt up` opnieuw (of `cd pulumi && uv run pulumi up`) past de Deployment aan.

## Bekijken

```sh
kubectl logs -n spark-demo deploy/spark-worker -f
kubectl get pods -n spark-demo -l app=spark-worker
```

In de master UI (<http://localhost:8080>) staan alle workers als "Alive" met hun cores + memory.

## Schaal verhogen

Snel via Pulumi-config:

```sh
cd pulumi
uv run pulumi config set workerReplicas 3
uv run pulumi up --yes
```

Of via `kubectl scale` (tijdelijk — Pulumi corrigeert dit terug bij volgende `up`):

```sh
kubectl scale -n spark-demo deploy/spark-worker --replicas=3
```

## Veel-voorkomende issues

- **Worker registreert niet**: master is misschien nog niet `Alive`. Check master logs eerst.
- **Executor OOM**: standaard limieten in `spark/spark-defaults.conf` zijn klein (512m per executor) om in 2 GB worker te passen. Verhoog `workerMemory` én pas de executor-instellingen aan voor zwaardere workloads.
