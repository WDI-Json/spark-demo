# spark-connect

Spark Connect Server — gRPC-endpoint voor lichtgewicht PySpark-clients. Dit is exact het protocol dat **Databricks Connect** ook gebruikt.

## Image & command

| | |
|---|---|
| Image | `apache/spark:4.0.3` |
| Command | `SPARK_NO_DAEMONIZE=1 exec /opt/spark/sbin/start-connect-server.sh --master spark://spark-master:7077 --conf spark.driver.host=$POD_IP --conf spark.driver.bindAddress=0.0.0.0 --packages org.apache.spark:spark-connect_2.13:4.0.3,io.delta:delta-spark_2.13:4.0.0 --name connect-server` |

`--packages` haalt de spark-connect jar én Delta van Maven bij eerste start (gecached in de pod tot restart).

## Poort

| Poort | Protocol |
|---|---|
| 15002 | gRPC (Spark Connect) |

In `../spark/spark-defaults.conf` staat `spark.connect.grpc.binding.host=0.0.0.0` zodat port-forward werkt.

## Bekijken

```sh
kubectl logs -n spark-demo deploy/spark-connect -f
```

Eerste opstart-logs laten zien: package download → `Spark Connect server started on port 15002`.

## Verbinden vanaf een notebook

```python
from pyspark.sql import SparkSession
spark = SparkSession.builder.remote("sc://localhost:15002").getOrCreate()
print(spark.version)        # 4.0.x
spark.sql("SELECT 1").show()
```

Client-side dependency: `pyspark[connect]==4.0.3` (zit in `../pyproject.toml`). De versie moet overeenkomen met de server.

## Catalog-isolatie

Spark Connect en Spark Thrift draaien als **gescheiden Spark-applicaties**, elk met een eigen in-memory catalog. Tabellen die dbt aanmaakt via Thrift zie je hier dus niet. Voor gedeelde state heb je een Hive Metastore nodig (zie `../README.md` → v2).

## Waarom dit Databricks-achtig is

Databricks Connect is een proprietary fork van Spark Connect — het wire-protocol is grotendeels hetzelfde. Wat je hier leert (de remote-session pattern, DataFrame-operaties die op de server uitgevoerd worden) gebruik je daar identiek. Verschil zit in authenticatie (Databricks: token/oauth, hier: niets) en het cluster zelf.

## Veel-voorkomende issues

- **`Could not connect to sc://localhost:15002`**: port-forward staat niet aan. Check `pf-connect` in Tilt.
- **`PySparkClientError: protocol mismatch`**: client- en server-versie lopen uit elkaar. Synchroniseer `pyspark[connect]` in `pyproject.toml` met het `apache/spark:X.Y.Z` image-tag.
- **Hangt bij eerste call**: package-download op de server, of geen worker-resources beschikbaar (thrift heeft alle cores gepakt). Wacht 1–2 min, check logs en `spark.cores.max` in spark-defaults.conf.
- **`TABLE_OR_VIEW_NOT_FOUND` voor een dbt-tabel**: catalog-isolatie (zie boven). Maak de data zelf aan in de notebook, of gebruik een Hive Metastore.
