# spark-master

De cluster-manager. Houdt bij welke workers er zijn, accepteert applicaties (Thrift, Connect, eigen `spark-submit`-jobs) en deelt taken uit.

## Image & command

| | |
|---|---|
| Image | `apache/spark:4.0.3` |
| Command | `SPARK_NO_DAEMONIZE=1 exec /opt/spark/sbin/start-master.sh` |

`SPARK_NO_DAEMONIZE=1` zorgt dat het proces in de foreground draait — anders zou Spark zichzelf naar de achtergrond forken en de container exit'en.

## Poorten

| Poort | Protocol | Gebruik |
|---|---|---|
| 7077 | Spark RPC | Workers, Thrift, Connect verbinden hier |
| 8080 | HTTP | Web UI — workers, applications, completed jobs |

## Env-vars

- `POD_IP` → ingevuld door K8s `fieldRef: status.podIP`
- `SPARK_LOCAL_IP=$(POD_IP)` → laat Spark zijn pod-IP adverteren i.p.v. de pod-naam (workaround voor opdringerige DNS-search-domains)

## Resources & state

- Standaard requests/limits: geen (laat K8s schedulen op alles beschikbaar)
- State: alleen in-memory; bij pod-restart vergeet de master alle running applicaties (workers re-registreren binnen seconden)

## Bekijken

```sh
kubectl logs -n spark-demo deploy/spark-master -f
kubectl port-forward -n spark-demo svc/spark-master 8080:8080   # Tilt doet dit al
open http://localhost:8080
```

## Veel-voorkomende issues

- **Worker komt niet "Alive"**: master ziet hem pas na ~10s heartbeat. Check `kubectl logs -n spark-demo deploy/spark-worker` voor `Successfully registered with master`.
- **Out-of-memory bij job-submit**: Spark Connect en Thrift draaien als drivers tegen deze master; bij te veel parallelle queries crasht de driver, niet de master. Master zelf is licht.
