# spark-thrift

Hive Thrift Server — een SQL-endpoint waar JDBC/ODBC-clients (zoals **dbt-spark**) tegen praten. Draait als Spark-applicatie op de master.

## Image & command

| | |
|---|---|
| Image | `apache/spark:4.0.3` |
| Command | `SPARK_NO_DAEMONIZE=1 exec /opt/spark/sbin/start-thriftserver.sh --master spark://spark-master:7077 --conf spark.driver.host=$POD_IP --conf spark.driver.bindAddress=0.0.0.0 --packages io.delta:delta-spark_2.13:4.0.0 --name thrift-server` |

`SPARK_NO_DAEMONIZE=1` houdt het proces foreground. De `--conf` flags zorgen dat de driver zijn pod-IP adverteert (anders breken executor-verbindingen door DNS-search-domain-issues). Delta wordt expliciet als package geladen zodat tabellen met `USING DELTA` werken.

## Poort

| Poort | Protocol |
|---|---|
| 10000 | Hive Thrift binary protocol (NOSASL) |

## Authenticatie

`hive.server2.authentication=NOSASL` (gezet in `../spark/spark-defaults.conf`). Reden: zonder SASL/Kerberos heeft dbt-spark[PyHive] geen system-`libsasl2` nodig om te verbinden. Voor productie zou je hier LDAP/Kerberos gebruiken.

## Bekijken

```sh
kubectl logs -n spark-demo deploy/spark-thrift -f
```

Eerste opstart-logs (~30–60s) laten zien:
- Ivy resolutie van `delta-spark_2.13:4.0.0`
- "Starting ThriftBinaryCLIService on port 10000"
- "HiveThriftServer2 started"

In de master UI staat hij als applicatie "Thrift JDBC/ODBC Server".

## Verbinden vanaf dbt

`../dbt/profiles.yml`:

```yaml
type: spark
method: thrift
host: localhost
port: 10000
auth: NOSASL
```

Port-forward (door Tilt automatisch) maakt `spark-thrift:10000` in het cluster bereikbaar als `localhost:10000` op je laptop.

## Veel-voorkomende issues

- **`Connection refused`**: pod nog niet klaar. Eerste start duurt 1–2 min omdat Delta-jars vanaf Maven gepulld worden. Check `kubectl logs`.
- **`Could not connect` vanuit dbt met SASL-fout**: `auth: NOSASL` ontbreekt in `profiles.yml`, of `hive.server2.authentication` is niet `NOSASL` in `spark-defaults.conf`.
- **`Table not found`**: de Thrift Server heeft een eigen catalog-sessie. Run `dbt seed` om de seed-tabel aan te maken. Spark Connect ziet deze tabel **niet** (eigen catalog) — zie `notebooks/README.md`.
