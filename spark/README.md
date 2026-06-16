# spark/

Spark-cluster-configuratie die als ConfigMap in alle pods gemount wordt op `/opt/spark/conf/spark-defaults.conf`.

## Wat staat erin

- **Delta Lake** — `spark.jars.packages` haalt `io.delta:delta-spark_2.13:4.0.0` op via Maven (Spark 4 → Scala 2.13). Eerste pod-start downloadt jars (~30s); daarna gecachet in de pod totdat hij herstart. Delta is **opt-in**: tabellen krijgen pas Delta-format als je expliciet `USING DELTA` schrijft. Reden: de DeltaCatalog default-aan zetten breekt dbt-spark op classloader-niveau. Voor dbt-tabellen → Parquet (Spark default).
- **Ivy cache** — naar `/tmp/.ivy2` omdat de apache/spark container als user 185 draait zonder schrijfbare home.
- **Resource-limieten** — `spark.cores.max=1`, `spark.executor.cores=1`, `spark.executor.memory=512m`. Zonder die limieten grijpt thrift alle worker-cores en blijft connect zonder executor hangen.
- **Warehouse-pad** — tabellen landen onder `/tmp/spark-warehouse` in de pod. Geen persistent volume in v1, dus state is weg na pod-restart.
- **Thrift-auth** — `NOSASL` zodat `dbt-spark[PyHive]` zonder system-`libsasl2` kan verbinden.
- **Spark Connect-binding** — luistert op `0.0.0.0:15002` zodat `kubectl port-forward` werkt.

## Wijzigen

Bewerk `spark-defaults.conf` en draai `cd ../pulumi && uv run pulumi up`. De ConfigMap wordt vervangen, maar omdat hij via `subPath` gemount is **moet je de pods handmatig restarten**:

```sh
kubectl rollout restart -n spark-demo deploy/spark-thrift deploy/spark-connect deploy/spark-master deploy/spark-worker
```

Tilt's `pulumi-up` resource doet alleen de Pulumi-apply; pod-restart is een handmatige stap (todo voor v2: configmap-hash annotation).
