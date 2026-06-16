# dbt/

Mini dbt-project dat tegen het Spark-cluster draait. Doel: smoke-test — als `dbt run && dbt test` slaagt weet je dat het hele pad cluster ↔ Thrift Server ↔ dbt-spark ↔ Spark SQL werkt.

## Wat zit erin

| Pad | Wat |
|---|---|
| `dbt_project.yml` | Projectconfig, default materialisatie `table` (Parquet — Spark default) |
| `profiles.yml` | Verbinding: `thrift` op `localhost:10000`, `auth: NOSASL` |
| `seeds/orders.csv` | 7 testrijen — orders met customer, amount, date |
| `models/stg_orders.sql` | Cast-laag bovenop de seed |
| `models/revenue_per_day.sql` | Aggregatie: orders + revenue per dag |
| `models/schema.yml` | `unique` + `not_null` tests op beide modellen |

## Draaien

Via Tilt (handmatige trigger, vanwege `TRIGGER_MODE_MANUAL` in de Tiltfile): klik in de Tilt-UI op het play-icoon bij `dbt-smoke`.

Direct (vanuit `dbt/`):

```sh
uv run dbt seed --profiles-dir .
uv run dbt run --profiles-dir .
uv run dbt test --profiles-dir .
```

Het `--profiles-dir .`-vlag wijst dbt naar de lokale `profiles.yml` in plaats van de globale `~/.dbt/profiles.yml`.

Verwacht resultaat:

```
seed   PASS=1
run    PASS=2
test   PASS=6
```

## Tabel-format

Default is Parquet. Voor een Delta-tabel: voeg toe aan de model-config:

```sql
{{ config(materialized='table', file_format='delta', location_root='/tmp/spark-warehouse/delta') }}
```

Werkt zolang de Delta-jar aanwezig is in het Thrift Server-classpath — die wordt in de Pulumi-config al via `--packages` meegegeven.

## Resultaat bekijken

Spark master UI op <http://localhost:8080> toont de SQL-jobs.

> **Notebooks zien deze tabellen niet** omdat Spark Connect een eigen Spark-applicatie is met eigen catalog (zie `../notebooks/README.md` en `../docs/spark-connect.md`).

## Verbindings-detail

`auth: NOSASL` werkt omdat het cluster geen Kerberos/LDAP heeft en de Hive-config in `../spark/spark-defaults.conf` `hive.server2.authentication=NOSASL` zet. Bij echte Databricks zou je `dbt-databricks` gebruiken; de modelcode hier (`{{ ref(...) }}`, Spark SQL) is 1-op-1 overdraagbaar.
