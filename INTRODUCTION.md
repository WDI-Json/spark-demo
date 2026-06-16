# Inleiding voor data engineers

Lees dit als je nieuw bent in data engineering of in deze stack, en wilt begrijpen *waarom* dit project er is en *hoe* de stukjes in elkaar passen. De `README.md` is de gebruiksaanwijzing; dit document is het verhaal eromheen.

## Waar gaat dit project over?

Iedereen die Databricks aanraakt komt op een gegeven moment tegen:
- "Hoe werkt Spark eigenlijk onder de motorkap?"
- "Wat doet dbt nou precies met mijn modellen?"
- "Waarom moet ik op een cluster werken? Kan ik niet gewoon lokaal iets proberen?"
- "Wat zijn de verschillen tussen wat ik op Databricks doe en 'echte' open source?"

Een **echte** Databricks-omgeving lokaal nadoen kan niet — die runtime is propriëtair. Maar de bouwstenen waar Databricks zélf op staat (Apache Spark, Delta Lake, een SQL-endpoint, een gRPC-protocol voor remote clients) zijn open source. Dit project zet die bouwstenen **lokaal** op je laptop neer, in een vorm die qua patronen zo dicht mogelijk bij Databricks ligt. Als je dit begrijpt, snap je 80% van wat er bij Databricks gebeurt — alleen zit daar nog een glanzende UI omheen.

Het doel is **niet**:
- Productie-klaar
- Performant
- Een vervanging van Databricks
- Iets waar je daadwerkelijk grote data op draait

Het doel is **wel**:
- Snappen waarom Spark een master + workers heeft
- Snappen wat dbt op een Spark-cluster doet
- Voelen hoe een notebook met een remote cluster praat (Spark Connect / Databricks Connect)
- Zien wat infrastructure-as-code is door het zelf te declareren
- Een kleine, repareerbare omgeving hebben om dingen in te proberen voordat je ze in productie loslaat

## De vier sleutel-concepten

Vier dingen draaien samen in dit project. Even één voor één.

### 1. Apache Spark — een distributed compute-engine

Spark is een **rekenmotor voor data**. Geef het een dataset en een SQL-query (of Python-code via de DataFrame-API), en het verdeelt het werk over meerdere machines (of in ons geval: meerdere pods).

Drie rollen die je hier ziet:

- **Master** — de manager. Houdt bij welke workers er zijn en welke applicaties er draaien.
- **Worker** — de werker. Heeft CPU + geheugen en voert daadwerkelijk taken uit.
- **Executor** — een proces dat een worker opstart voor een specifieke Spark-applicatie. Eén app = één of meer executors.
- **Driver** — het hoofdproces van een Spark-applicatie. Plant de queries, stuurt executors aan. Bij ons leven de drivers in de Thrift- en Connect-pods.

In productie kan Spark schalen naar duizenden workers; hier is het er één, met 2 cores en 2 GiB geheugen. Maar de **patterns** zijn identiek.

### 2. Delta Lake — een formaat voor tabellen

Een rauwe Parquet-tabel is een collectie bestanden in een map. Werkt fijn voor lezen, maar je kunt niet veilig schrijven terwijl iemand anders leest, en je hebt geen transactiehistorie.

**Delta Lake** voegt een logboek toe (`_delta_log/`) naast je Parquet-bestanden. Daarmee krijg je:
- ACID-transacties (zoals een database)
- Time travel (lees de tabel zoals hij gisteren was)
- Schema evolution (kolommen toevoegen zonder de tabel te herbouwen)
- MERGE / UPSERT statements

In dit project is Delta *opt-in*: je default is Parquet, en Delta krijg je per tabel met `USING DELTA`. Reden: zodra Delta het *default* catalog wordt, valt dbt-spark om met class-loader issues. Op echt Databricks is Delta hét default — daar zorgt de propriëtaire runtime dat alle randjes glad zijn.

### 3. dbt — een transformatie-framework

dbt (data build tool) draait *SQL met superkrachten*. Je schrijft normale SELECT-statements, dbt zorgt voor:
- **Materialisatie** — `SELECT ... FROM raw_orders` wordt door dbt omgezet naar `CREATE TABLE staging_orders AS SELECT ...`. Jij hoeft alleen het SELECT-deel te schrijven.
- **Dependency graph** — dbt weet dat `revenue_per_day` `stg_orders` nodig heeft (door de `{{ ref('stg_orders') }}` macro), en bouwt ze in de juiste volgorde.
- **Testen** — `unique`, `not_null` etc. worden uitgevoerd na het bouwen.
- **Documentatie** — uit je SQL + YAML genereert dbt een browsable docs-site.

dbt is **niet** een rekenmotor. Het *vertaalt* je SQL naar `CREATE TABLE` statements en stuurt die naar een database/warehouse. In ons geval gaat dat via de **Hive Thrift Server**, die SQL ontvangt en doorzet naar Spark.

In Databricks zou je `dbt-databricks` gebruiken in plaats van `dbt-spark`. De modelcode (de SELECTs, de `{{ ref(...) }}`s) is identiek — alleen het adapter-laagje verschilt.

### 4. Kubernetes — een orchestrator

Spark heeft master + worker + thrift + connect — allemaal aparte processen die met elkaar moeten praten. Hoe regel je dat?

**Kubernetes** is een systeem dat containers (pods) draait, ze automatisch herstart als ze crashen, en ze met elkaar laat communiceren via stabiele namen (Services). Voor dit project doet K8s precies dat:

- Elke Spark-component is een **Deployment** (template voor pods).
- Elke poort die je nodig hebt is een **Service** (stabiele DNS-naam in het cluster).
- De Spark-config is een **ConfigMap** die in alle pods gemount wordt.

Bij Databricks zit K8s onder de motorkap — je ziet het niet, je krijgt "clusters" voorgeschoteld. Maar het is er wel.

## Hoe past dit alles samen

```
   jij ──► tilt ──► pulumi ──► kubernetes ──► docker ──► containers met spark
                                  │
                                  └── creëert deployments + services + configmaps
```

Stap voor stap:

1. **Jij** typt `tilt up`.
2. **Tilt** is een orchestrator voor je dev-workflow. Hij leest `Tiltfile` en draait de stappen in volgorde: `uv sync`, `pulumi up`, dan port-forwards.
3. **Pulumi** is je infrastructure-as-code tool. In `pulumi/__main__.py` staat in Python beschreven welke K8s-objecten er moeten bestaan. Pulumi vergelijkt wens met realiteit en maakt het verschil aan.
4. **Kubernetes** ontvangt de K8s-manifests (Deployments etc.) en zorgt dat er pods draaien die overeenkomen met de specificatie.
5. **Docker** (via Rancher Desktop op je Mac) draait de minikube-VM én de pods daarin.
6. **De pods** zelf draaien `apache/spark:4.0.3` en runnen verschillende Spark-componenten op basis van het commando dat we meegeven.

Als één pod crasht, herstart K8s 'm. Als jij `spark-defaults.conf` aanpast, ziet Pulumi het verschil en update de ConfigMap. Als je `workerReplicas: 3` zet, schaalt K8s de worker-Deployment.

Dit is *declaratief*: jij beschrijft de **gewenste eindstaat**, en het systeem zorgt dat de werkelijkheid dat wordt. Dat is een fundamenteel verschil met *imperatief* werken (zelf bash-scripts schrijven die in volgorde dingen aanmaken).

## Wat gebeurt er als je `tilt up` doet

Concreet, in detail:

1. **`cluster-check`**: kijkt of `kubectl` op de minikube-context staat.
2. **`uv-sync`**: `uv sync` checkt of `.venv/` actueel is. Als `pyproject.toml` veranderd is wordt de venv herbouwd.
3. **`pulumi-stack`**: selecteert (of maakt) de `dev`-stack.
4. **`pulumi-up`**: roept `pulumi up` aan. Pulumi-state staat lokaal in `~/.pulumi/`. Dit doet:
   - Vergelijk huidige cluster-staat met de gewenste staat in `__main__.py`.
   - Diff toepassen: Deployments aanmaken, Services aanmaken, ConfigMap aanmaken.
5. **K8s** ontvangt manifests en begint pods te schedulen. Eerste keer pullt het `apache/spark:4.0.3` (~700 MB) van Docker Hub.
6. **Spark master-pod** start, begint te luisteren op `:7077` en `:8080`.
7. **Spark worker-pod** start, registreert zich bij de master.
8. **Spark thrift-pod** start, doet `spark-submit` met `--packages io.delta:...`. Eerste keer downloadt Ivy de Delta-jar van Maven Central (~30s). Daarna start de Thrift Server op `:10000`.
9. **Spark connect-pod** start, vergelijkbaar maar met de Spark Connect-jar erbij, op `:15002`.
10. **Port-forwards** (3 stuks) zetten de cluster-poorten op je laptop. `localhost:10000` praat nu met `spark-thrift:10000` binnen het cluster.
11. **`dbt-smoke`** staat klaar maar wacht op een handmatige trigger via de Tilt-UI.

Druk je op het play-icoontje bij `dbt-smoke`:

12. dbt verbindt met `localhost:10000` (= Thrift), draait `dbt seed` (laadt `orders.csv` als tabel), dan `dbt run` (bouwt `stg_orders` en `revenue_per_day`), dan `dbt test` (controleert `unique` + `not_null`).
13. Alles wat dbt naar Thrift stuurt → Thrift maakt er een Spark-job van → master delegeert naar de worker-executor → resultaat terug.

## Spark Connect vs Thrift — twee deuren naar hetzelfde cluster

Dit is een belangrijk concept om te begrijpen.

**Thrift Server** is een SQL-endpoint. Praat het Hive Thrift-protocol (een ouder protocol dat allerlei JDBC-clients ondersteunen). dbt-spark gebruikt het. Je stuurt SQL-strings, je krijgt rijen terug.

**Spark Connect** is een gRPC-endpoint dat lijkt op een remote PySpark-sessie. Je doet `spark.createDataFrame([...])` op je laptop, en dat object leeft in werkelijkheid op de server. Je doet `df.groupBy(...).count().show()` en alleen het *resultaat* komt terug. Dit is exact wat Databricks Connect doet, alleen met hun authentication erbij.

Belangrijke nuance: **Thrift en Connect zijn afzonderlijke Spark-applicaties.** Elk heeft een eigen in-memory catalog (lijst van bekende tabellen). Een tabel die dbt via Thrift aanmaakt is **niet zichtbaar** in een notebook via Connect, en omgekeerd. Voor gedeelde state heb je een externe metastore nodig (zoals Hive Metastore met PostgreSQL). Dat staat op de v2-roadmap, maar voor leren is het juist leerzaam om deze grens te voelen.

Op Databricks merk je dit niet, omdat Unity Catalog die metastore-rol vervult voor alle compute-runtimes binnen je workspace.

## De realiteit: wat werkt anders dan productie

Iedere shortcut die we hier nemen heeft een productie-tegenhanger. Goede leerstof.

| Hier | In productie / Databricks |
|---|---|
| 1 worker, 2 cores | Tientallen workers, autoscaling |
| State in `/tmp/` (weg bij restart) | S3/ADLS/GCS object storage |
| Geen authenticatie | OAuth/SSO, RBAC, Unity Catalog ACLs |
| Spark Connect en Thrift met aparte catalogs | Eén Unity Catalog voor de hele workspace |
| Delta als opt-in vanwege class-loader-issues | Delta default, classloader voorgeconfigureerd |
| Maven-downloads bij eerste pod-start | Pre-baked custom image of cached package-repo |
| Lokale Pulumi state | Pulumi Cloud / Terraform Cloud, met state-locking |
| Port-forward via kubectl | Ingress + DNS + TLS |
| Eén gedeelde `spark.cores.max=1` om hangen te voorkomen | Schedulers (YARN, K8s native) met queues en quota |

Geen daarvan is "fout" voor leren — je leert ze beter snappen door eerst te zien hoe het zonder kan, en dan stap voor stap toe te voegen.

## Wat zou ik hier moeten leren?

Drie niveaus van leren in dit project:

### Niveau 1 — Het pad voelen
Draai `tilt up`, kijk naar de Tilt-UI, klik door de Spark master UI (`localhost:8080`), trigger `dbt-smoke`, open de notebook. Voel hoe één commando een hele stack omhoog brengt. Welke pods draaien er? Welke poorten? Welke logs?

```sh
kubectl get all -n spark-demo
kubectl logs -n spark-demo deploy/spark-master -f
k9s -n spark-demo
```

### Niveau 2 — Dingen aanpassen
- Voeg een nieuw dbt-model toe in `dbt/models/` en draai opnieuw.
- Schrijf in de notebook een eigen aggregatie.
- Zet `workerReplicas: 2` in `Pulumi.dev.yaml`, `tilt up`, kijk in master UI of er nu 2 workers staan.
- Maak een tabel met `USING DELTA` en kijk in de pod naar `/tmp/spark-warehouse/`.

### Niveau 3 — De diagrammen verbinden met de realiteit
Lees [`docs/architecture.md`](docs/architecture.md) (de C4-diagrammen). Probeer voor elk component te benoemen:
- Welk Kubernetes-object hoort erbij?
- Welk Python-codeblok in `pulumi/__main__.py` creëert het?
- Welke poort exposet het?
- Wat is z'n productie-tegenhanger?

Als je dit niveau bereikt, kun je hetzelfde patroon op een echte cloud-Spark omgeving (Databricks, EMR, Dataproc) toepassen.

## Volgende stappen — wat te proberen

Een paar zinvolle vingeroefeningen, in volgorde van moeilijkheid:

1. **Voeg een dbt-test toe.** Bedenk een aanname over je data en test het. Hint: `dbt-utils` of een custom test.
2. **Doorbreek iets bewust en repareer het.** Zet de master-image op `apache/spark:4.0.99` (bestaat niet) en draai pulumi up. Wat gebeurt er in `kubectl describe pod`? Hoe rol je het terug?
3. **Voeg een Jupyter-notebook toe** die data van een externe bron leest (een CSV in een GitHub raw URL) en daar een aggregatie op doet. Forceer jezelf om de DataFrame-API te gebruiken in plaats van SQL.
4. **Schaal de worker omhoog en kijk naar het werk dat verdeeld wordt.** Voer een join uit op grote data (lokaal genereerd) en kijk in de Spark UI welke executors welk werk doen.
5. **Voeg een Hive Metastore + PostgreSQL toe** zodat notebooks de dbt-tabellen wél kunnen zien. Dit is een echt v2-stap en goed te doen met de bestaande Pulumi-setup.
6. **Migreer naar Databricks.** Met een gratis Community Edition kun je dezelfde dbt-modelcode oppakken, een paar adapter-instellingen veranderen, en zien hoe het identiek werkt op een echte cluster.

## Vragen die de moeite waard zijn

Tijdens het werken hiermee zul je tegen dingen aanlopen die je nieuwsgierig maken. Een paar goede vragen om je in te verdiepen:

- *Waarom is een Spark "executor" een ander proces dan een Spark "worker"?* (Worker = OS-proces dat permanente daemon is; executor = JVM-proces dat per Spark-app wordt gestart op een worker.)
- *Wat is het verschil tussen `spark.cores.max` en `spark.executor.cores`?* (Eerste = totaal voor de hele app; tweede = per executor.)
- *Waarom is Delta een "log" en niet gewoon Parquet met versies?* (Het log laat je sneller "vooruit/terug spoelen" zonder hele bestanden te kopiëren.)
- *Wat doet `--packages` precies?* (Spark resolved Maven coordinaten via Ivy en zet de jars op de classpath van zowel driver als executors.)
- *Waarom werken `kubectl port-forward` en `Service` allebei?* (Service routeert binnen het cluster; port-forward brengt cluster-poort naar je laptop.)

Veel succes met ontdekken. De fouten die je gaat maken zijn meestal het waardevolst — bij elke "hè, waarom?" leer je iets wat in een tutorial nooit had gestaan.
