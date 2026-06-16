# notebooks/

Jupyter-notebooks die via **Spark Connect** (gRPC op poort 15002) met het cluster praten.

## Waarom Spark Connect

Sinds Spark 3.4 bestaat er een client/server-protocol waarmee je vanaf je laptop tegen een remote Spark draait zonder lokale JVM. Databricks Connect gebruikt exact dit protocol — code die hier werkt is daar 1-op-1 overdraagbaar.

```python
from pyspark.sql import SparkSession
spark = SparkSession.builder.remote("sc://localhost:15002").getOrCreate()
spark.sql("SELECT 1").show()
```

## Hoe te draaien

1. `tilt up` (zorg dat `pf-connect` groen is in de Tilt-UI).
2. Open een `.ipynb` in VS Code. De Jupyter-extensie (zit al in `devsetup`) pakt automatisch de Python uit `../.venv/` op als kernel.
3. Eerste cel runt → `Spark version: 4.0.x` als verbinding goed is.

## Catalog-isolatie

Spark Connect en Spark Thrift draaien als afzonderlijke Spark-applicaties met elk een eigen in-memory catalog. Tabellen die `dbt-smoke` via Thrift maakt **zie je niet** in een notebook via Connect — ze leven in verschillende sessies. Voor gedeelde state heb je een Hive Metastore nodig (zie v2 in `../README.md`).

In de praktijk werk je dus per omgeving:
- **Notebooks** voor exploratie met eigen `createDataFrame` / `spark.read.parquet(...)`.
- **dbt** voor reproduceerbare transformaties die je later naar productie schuift (waar je wél een echte metastore hebt).

## Files

| Notebook | Wat |
|---|---|
| `01_hello_spark.ipynb` | Connect, `SHOW TABLES`, query op `revenue_per_day`, eigen `SUM` over `stg_orders`. |

Voeg eigen notebooks toe — alles wat in Spark SQL of de PySpark DataFrame-API kan, werkt hier.

## Troubleshooting

- **`Could not connect to sc://localhost:15002`**: port-forward staat niet aan. Check `pf-connect` in Tilt; herstart eventueel via Tilt-UI.
- **`Table not found`**: dbt-smoke heeft nog niet gedraaid. Trigger `dbt-smoke` in Tilt om de seeds en modellen op te bouwen.
- **Versie-mismatch**: client (`pyspark[connect]==3.5.3` in `../pyproject.toml`) moet overeenkomen met de server (image `bitnami/spark:3.5`). Bij upgrades beide aanpassen.
