# Data Engineering Practice Exercises

A collection of short, hands-on exercises to learn Databricks concepts, dbt, Spark, and data engineering best practices using this repository as a playground.

> **How to use this file:** Work through the exercises roughly in order. Each exercise has a goal, a hint, and a "definition of done" so you know when you've succeeded. The exercises build on each other but are also self-contained — feel free to jump around.

---

## Foundations

### Exercise 1 — Explore the running stack

**Goal:** Get comfortable with the cluster before writing any code.

1. Run `tilt up` and wait until all resources are green.
2. Open the Spark master UI at <http://localhost:8080>.
3. Answer the following questions by looking at the UI and running `kubectl` commands:
   - How many workers are registered?
   - How much memory and how many cores does each worker expose?
   - Which Spark applications are currently running?

```sh
kubectl get all -n spark-demo
kubectl logs -n spark-demo deploy/spark-master --tail=50
```

**Done when:** You can name every running pod and explain what it does.

---

### Exercise 2 — Run the smoke test and read the output

**Goal:** Understand what dbt does end-to-end.

1. In the Tilt UI, click the play button on `dbt-smoke`.
2. Watch the logs and find:
   - Which SQL statements did dbt generate?
   - In what order were the models built, and why?
   - Which tests passed?

**Done when:** You can explain the dependency order (`orders` → `stg_orders` → `revenue_per_day`) in your own words.

---

## dbt Exercises

### Exercise 3 — Add a column to staging

**Goal:** Modify an existing model without breaking the pipeline.

Open `dbt/models/stg_orders.sql` and add a derived column `amount_eur` that converts `amount` to euros by multiplying by `0.92`.

Run `dbt run && dbt test` to verify nothing breaks.

**Hint:** Add the column in the `SELECT` list. You don't need to change the schema YAML unless you want to add a test for it.

**Done when:** `dbt run` passes and the new column appears when you query the table.

---

### Exercise 4 — Write a new dbt model

**Goal:** Build a model from scratch using `{{ ref(...) }}`.

Create a new file `dbt/models/top_customers.sql` that:
- Reads from `stg_orders`
- Groups by `customer_id`
- Returns `total_revenue` and `order_count` per customer
- Orders by `total_revenue DESC`

Register the model in `dbt/models/schema.yml` with at least one test.

**Done when:** `dbt run && dbt test` all pass and the new table exists.

---

### Exercise 5 — Use a dbt materialization: view vs table

**Goal:** Understand the difference between materializations.

1. Change `top_customers.sql` to use `materialized='view'` instead of `materialized='table'`.
2. Run `dbt run` again.
3. Check the Spark UI to see how the job differs from a `table` materialization.

**Reflection questions:**
- When would you prefer a view over a table in a production pipeline?
- What happens to downstream models that depend on this model?

**Done when:** You can explain the trade-offs between `view`, `table`, and `incremental` materializations.

---

### Exercise 6 — Add a custom data test

**Goal:** Go beyond built-in `unique` / `not_null` tests.

Add a singular test that verifies no `amount` in `stg_orders` is negative. Create the file `dbt/tests/assert_positive_amount.sql`. A singular test is a SQL query that returns **zero rows** when the assertion holds.

```sql
-- dbt/tests/assert_positive_amount.sql
select * from {{ ref('stg_orders') }}
where amount < 0
```

Run `dbt test` to confirm it passes, then add a row to `orders.csv` with a negative amount and run `dbt seed && dbt test` to confirm it fails.

**Done when:** The test fails with the bad row and passes after you remove it.

---

### Exercise 7 — Introduce an incremental model

**Goal:** Understand how incremental models avoid full table rebuilds.

Create `dbt/models/orders_incremental.sql`:

```sql
{{ config(
    materialized='incremental',
    unique_key='order_id'
) }}

select * from {{ ref('stg_orders') }}

{% if is_incremental() %}
  where order_date > (select max(order_date) from {{ this }})
{% endif %}
```

Run `dbt run`, add two new rows to `orders.csv` with a future date, then run `dbt seed && dbt run` again.

**Reflection questions:**
- Did all rows get rebuilt, or only the new ones?
- What does `{{ this }}` refer to?
- When should you use `unique_key` in an incremental model?

**Done when:** Only the new rows were inserted on the second run.

---

## Bronze → Silver → Gold (Medallion Architecture)

> The **medallion architecture** is a layered data design pattern:
> - **Bronze** — raw data, loaded as-is, never deleted, append-only.
> - **Silver** — cleaned, typed, deduplicated data; one row per business entity.
> - **Gold** — aggregated, business-ready data for dashboards and analytics.
>
> This pattern is the standard in Databricks/Delta Lake environments. The exercises below map your existing models to this pattern.

---

### Exercise 8 — Identify the layers in this repo

**Goal:** Map the existing models to the medallion architecture.

| Layer  | This repo equivalent         | Explanation |
|--------|------------------------------|-------------|
| Bronze | `orders` (the seed)          | Raw data, loaded as-is from CSV |
| Silver | `stg_orders`                 | Cleaned, typed, deduplication-ready |
| Gold   | `revenue_per_day`            | Aggregated for reporting |

**Task:** Reorganise the models into sub-folders to make the layers explicit:

```
dbt/models/
  bronze/   ← (seeds are bronze; you can add a bronze passthrough model here)
  silver/   ← stg_orders.sql
  gold/     ← revenue_per_day.sql, top_customers.sql
```

Update `dbt_project.yml` to point to the new paths:

```yaml
models:
  spark_demo:
    silver:
      +materialized: table
    gold:
      +materialized: table
```

Run `dbt run` to confirm everything still works.

**Done when:** The folder structure reflects bronze/silver/gold and all models build successfully.

---

### Exercise 9 — Add a bronze passthrough model

**Goal:** Practice the "load raw, never transform in place" principle.

Create `dbt/models/bronze/raw_orders.sql` that selects everything from the seed without any transformation:

```sql
{{ config(materialized='table') }}

select * from {{ ref('orders') }}
```

Then update `stg_orders.sql` to read from `{{ ref('raw_orders') }}` instead of `{{ ref('orders') }}`.

**Reflection questions:**
- Why is it useful to have a bronze layer that mirrors the source data exactly?
- What happens in production when a source schema changes unexpectedly?

**Done when:** `dbt run` succeeds with the new dependency chain (`orders` → `raw_orders` → `stg_orders` → `revenue_per_day`).

---

### Exercise 10 — Add a Delta table (Silver layer)

**Goal:** Experience the difference between Parquet and Delta.

Change `stg_orders.sql` to use Delta format:

```sql
{{ config(
    materialized='table',
    file_format='delta'
) }}
```

After running, inspect the table directory inside the Spark pod:

```sh
kubectl exec -n spark-demo deploy/spark-thrift -- \
  ls /tmp/spark-warehouse/stg_orders
```

You should see a `_delta_log/` directory alongside the Parquet files.

**Reflection questions:**
- What does the `_delta_log/` directory contain?
- How does Delta Lake use this log for ACID transactions?
- What does "time travel" mean, and how would you query a previous version?

**Done when:** You can see the `_delta_log/` directory and explain what it contains.

---

## Apache Spark Exercises

### Exercise 11 — Run your first PySpark query in the notebook

**Goal:** Get comfortable with the DataFrame API.

Open `notebooks/01_hello_spark.ipynb`. After the first cell (which connects to Spark), add a new cell that:

1. Creates a DataFrame from a list of dictionaries (products with name and price).
2. Filters for products with price > 50.
3. Shows the result.

```python
from pyspark.sql import Row

products = [
    Row(name="Apple", price=1.5),
    Row(name="Laptop", price=999.0),
    Row(name="Coffee", price=4.5),
    Row(name="Monitor", price=299.0),
]

df = spark.createDataFrame(products)
df.filter(df.price > 50).show()
```

**Done when:** The filtered result appears in the notebook output.

---

### Exercise 12 — Understand lazy evaluation

**Goal:** Observe that Spark doesn't do work until you force it.

In the notebook, run:

```python
df = spark.range(1_000_000)
filtered = df.filter(df.id % 2 == 0)
# Nothing has been computed yet — no job in Spark UI

result = filtered.count()  # This triggers a job
print(result)
```

Open the Spark UI at <http://localhost:8080> and look at the jobs tab while running.

**Reflection questions:**
- When did the actual computation happen?
- What is the difference between a **transformation** and an **action** in Spark?

**Done when:** You can list three transformations and three actions in Spark.

---

### Exercise 13 — Read a CSV with Spark and write as Parquet

**Goal:** Practice the read/transform/write pattern that is at the heart of data engineering.

In the notebook:

```python
import io

csv_data = """id,name,sales
1,Alice,100
2,Bob,200
3,Carol,150
"""

# Write temp CSV so Spark can read it
with open("/tmp/sales.csv", "w") as f:
    f.write(csv_data)

df = spark.read.option("header", True).csv("/tmp/sales.csv")
df = df.withColumn("sales", df.sales.cast("integer"))
df.write.mode("overwrite").parquet("/tmp/sales_parquet")
df2 = spark.read.parquet("/tmp/sales_parquet")
df2.show()
df2.printSchema()
```

**Done when:** The schema shows `sales` as integer (not string) and the Parquet files exist under `/tmp/sales_parquet/`.

---

### Exercise 14 — Scale the cluster and observe parallelism

**Goal:** See Spark use multiple workers.

1. Open `pulumi/Pulumi.dev.yaml` and change `workerReplicas` from `1` to `2`.
2. Run `tilt up` (or just re-trigger `pulumi-up` in Tilt).
3. Visit <http://localhost:8080> and confirm two workers are registered.
4. In the notebook, run a more expensive aggregation and watch the Spark UI stages.

**Reflection questions:**
- How does the master distribute work across the two workers?
- What is a "stage" vs a "task" in Spark?
- What causes a "shuffle" and why is it expensive?

**Done when:** Two workers appear in the Spark UI and you can describe what a shuffle is.

---

## Data Quality & Best Practices

### Exercise 15 — Add a freshness test (data recency)

**Goal:** Learn to detect stale data before it reaches your dashboards.

In `dbt/models/schema.yml`, add a source definition (treating the seed as a source) and configure a freshness check:

```yaml
sources:
  - name: raw
    tables:
      - name: orders
        freshness:
          warn_after: {count: 7, period: day}
          error_after: {count: 30, period: day}
        loaded_at_field: order_date
```

Run `dbt source freshness` and observe the output.

**Reflection questions:**
- Why is data freshness an important data quality dimension?
- How would you alert on a freshness failure in a production pipeline?

**Done when:** `dbt source freshness` reports a status for your source.

---

### Exercise 16 — Break something intentionally and fix it

**Goal:** Build resilience by experiencing failure modes first-hand.

1. In `pulumi/Pulumi.dev.yaml`, change the Spark image tag to `apache/spark:4.0.99` (does not exist).
2. Run `tilt up` and observe what happens in `kubectl describe pod`.
3. Identify the error (`ImagePullBackOff` or `ErrImagePull`).
4. Roll back the image tag to `apache/spark:4.0.3` and confirm recovery.

**Reflection questions:**
- What does `kubectl describe pod` tell you that `kubectl get pods` does not?
- How would you implement a rollback strategy in a production IaC setup?

**Done when:** The cluster recovers to a healthy state after your rollback.

---

### Exercise 17 — Document your models with dbt docs

**Goal:** Practice the "data as a product" principle — good documentation is part of delivery.

1. Add a `description` to every column in `dbt/models/schema.yml`.
2. Run `dbt docs generate`.
3. Run `dbt docs serve` (on a free port) and explore the lineage graph.

**Reflection questions:**
- How does the dependency graph (`orders` → `stg_orders` → `revenue_per_day`) appear visually?
- Why is automatic lineage tracking valuable in large data platforms?

**Done when:** You can navigate the lineage graph in the browser and see all column descriptions.

---

### Exercise 18 — Add row-count assertions between layers

**Goal:** Practice data reconciliation — a core data engineering best practice.

Add a singular test `dbt/tests/assert_silver_row_count_matches_bronze.sql` that verifies the number of rows in `stg_orders` equals the number of rows in `raw_orders` (they should match since we don't filter in staging):

```sql
select
    (select count(*) from {{ ref('raw_orders') }})   as bronze_count,
    (select count(*) from {{ ref('stg_orders') }})   as silver_count
where bronze_count != silver_count
```

**Done when:** The test passes and you understand when it would fail (e.g., deduplication in silver).

---

## Infrastructure & IaC

### Exercise 19 — Read and understand the Pulumi code

**Goal:** Demystify infrastructure-as-code.

Open `pulumi/__main__.py` and find the code that creates the Spark master Deployment. Answer:

- What image does it use?
- What environment variables are set?
- How does the Service connect to the Deployment (what label selector is used)?
- What would you change to give the master 2 GB of memory?

**Done when:** You can explain what `pulumi/__main__.py` does line by line for one component.

---

### Exercise 20 — Add a ConfigMap entry and use it in Spark

**Goal:** Experience declarative configuration management.

1. Find the `spark-defaults.conf` ConfigMap in `pulumi/__main__.py` (or in `spark/spark-defaults.conf`).
2. Add the entry `spark.sql.shuffle.partitions=4` (the default is 200, which is wasteful for tiny datasets).
3. Run `tilt up` to apply the change.
4. In the notebook, run `spark.conf.get("spark.sql.shuffle.partitions")` to confirm the setting is active.

**Reflection questions:**
- What is the default value of `spark.sql.shuffle.partitions` and why is 200 wasteful on a tiny cluster?
- How does Kubernetes propagate a ConfigMap change to running pods?

**Done when:** The notebook confirms the new value is in effect.

---

## Stretch Goals

These exercises go beyond the current repo setup and require a bit more exploration.

### Exercise 21 — Add a Hive Metastore (shared catalog)

**Goal:** Understand why notebooks can't see dbt tables today — and fix it.

Currently, Spark Connect and Spark Thrift have separate in-memory catalogs. Add a PostgreSQL + Hive Metastore to `pulumi/__main__.py` so both applications share one catalog.

**Hint:** Look at the v2 roadmap in `README.md` and `INTRODUCTION.md`. You'll need to:
- Add a PostgreSQL Deployment and Service.
- Add a Hive Metastore Service (or configure the embedded Derby metastore to use JDBC).
- Point both Spark applications at the shared metastore via `spark-defaults.conf`.

**Done when:** A table created by dbt (via Thrift) is visible in the notebook (via Connect).

---

### Exercise 22 — Migrate your dbt project to Databricks Community Edition

**Goal:** Confirm that the patterns you learned locally apply to the real platform.

1. Sign up for [Databricks Community Edition](https://community.cloud.databricks.com/).
2. Copy your dbt models to a new dbt project configured with `dbt-databricks`.
3. Run `dbt run` against your Community Edition cluster.

**Reflection questions:**
- What configuration changed between `dbt-spark` and `dbt-databricks`?
- What works identically, and what is different or easier on the real platform?

**Done when:** Your models run successfully on Databricks Community Edition.

---

## Quick Reference

### Key dbt commands

```sh
dbt seed           # load CSV seeds into the warehouse
dbt run            # build all models
dbt test           # run all tests
dbt docs generate  # generate documentation site
dbt docs serve     # serve documentation in browser
dbt source freshness  # check source data recency
```

### Key kubectl commands

```sh
kubectl get all -n spark-demo                        # list all resources
kubectl logs -n spark-demo deploy/spark-master -f    # stream master logs
kubectl describe pod -n spark-demo <pod-name>        # detailed pod info
kubectl exec -n spark-demo deploy/spark-thrift -- ls /tmp/spark-warehouse
```

### Medallion architecture cheat sheet

| Layer  | Naming convention | Characteristics |
|--------|-------------------|-----------------|
| Bronze | `raw_*` / `bronze_*` | Append-only, unmodified source data, never delete |
| Silver | `stg_*` / `int_*`    | Cleaned, typed, deduplicated, one row per entity |
| Gold   | `mart_*` / `<domain>_<metric>` | Aggregated, business-ready, optimised for reads |

### Data quality dimensions

| Dimension   | Question to ask |
|-------------|-----------------|
| Completeness | Are there unexpected NULLs? |
| Uniqueness   | Are primary keys truly unique? |
| Freshness    | Is the data recent enough? |
| Validity     | Are values within expected ranges/formats? |
| Consistency  | Do counts match between layers (bronze vs silver)? |
