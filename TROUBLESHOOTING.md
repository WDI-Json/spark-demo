# Troubleshooting

Praktische gids voor als `tilt up` of een onderdeel niet doet wat je verwacht.
Per probleem: **symptoom → oorzaak → fix**. De meeste valkuilen draaien om de
kubectl-context, de Docker-daemon, of de Pulumi-state — start daar.

> **Snelste sanity-check:** draait de Docker-daemon, en wijst kubectl naar het
> juiste profiel?
>
> ```sh
> docker version                         # Server-sectie moet er zijn
> minikube update-context -p spark-demo  # pin de context op spark-demo
> kubectl get nodes                      # 1 node 'spark-demo' Ready?
> ```

---

## 1. `tilt up` start de Docker-daemon niet / minikube faalt direct

**Symptoom**

```
PROVIDER_DOCKER_VERSION_EXIT_1: ... failed to connect to the docker API at
unix:///Users/<jij>/.rd/docker.sock ... connect: no such file or directory
```

**Oorzaak** — De Docker-daemon (Rancher Desktop of Docker Desktop) draait niet.
minikube gebruikt de docker-driver en heeft een werkende daemon nodig.

**Fix** — Start Rancher/Docker Desktop en wacht tot de socket bestaat:

```sh
open -a "Rancher Desktop"     # of: open -a "Docker"
# wacht tot dit werkt:
docker version
```

---

## 2. minikube weigert te starten wegens te weinig geheugen

**Symptoom**

```
MK_USAGE: Docker Desktop has only 3918MB memory but you specified 5120MB
```

**Oorzaak** — De VM van Rancher/Docker Desktop heeft minder RAM dan `--memory=5g`
vraagt. De stack heeft ~6 GB VM-geheugen nodig (zie README → *Resources & geheugen*).

**Fix (Rancher Desktop)** — Zet de VM op minimaal 6 GB en wacht tot de daemon terug is:

```sh
rdctl set --virtual-machine.memory-in-gb 6
docker version     # poll tot de daemon weer reageert
```

In Docker Desktop: *Settings → Resources → Memory* omhoog. Daarna pas `tilt up`.

---

## 3. Alles in Tilt blijft hangen / `cluster-check` is rood

**Symptoom** — In de Tilt-UI is `cluster-check` rood (of blijft pending) en alle
resources daaronder (`pulumi-up`, port-forwards) staan op pending. Niks komt op.

**Oorzaak** — Historisch: `cluster-check` deed een harde check op de *huidige*
kube-context en faalde als die niet `spark-demo` was — en omdat het een
`local_resource` zonder deps is, probeerde Tilt het daarna niet opnieuw, dus de
hele pijplijn zat vast.

**Fix** — Dit is opgelost in de Tiltfile: `cluster-check` **maakt/start het
`spark-demo`-profiel zelf** als het mist, en zet de context erop via
`minikube update-context`. Zie je toch nog een rode `cluster-check`:

- Klik in de Tilt-UI op het trigger-icoon bij `cluster-check` om hem opnieuw te draaien.
- Controleer dat de Docker-daemon draait (zie #1).
- Draai je een oude Tiltfile? `git pull` en herstart `tilt up`.

---

## 4. kubectl wijst opeens weer naar `rancher-desktop`/`docker-desktop`

**Symptoom** — Je had de context op `spark-demo`, maar `kubectl` praat plots tegen
een andere cluster: `kubectl get pods -n spark-demo` zegt *No resources found* of
*context "spark-demo" does not exist*, terwijl de pods echt draaien.

**Oorzaak** — Rancher Desktop beheert `~/.kube/config` actief en **prunet
periodiek de minikube-context** die het niet zelf bezit. Daardoor verdwijnt de
`spark-demo`-context tussendoor uit je kubeconfig.

**Fix** — Her-injecteer de context (dit is precies waarom de Tiltfile
`minikube update-context` gebruikt i.p.v. `kubectl config use-context`):

```sh
minikube update-context -p spark-demo
```

Voor losse commando's kun je ook expliciet pinnen: `kubectl --context spark-demo …`.

---

## 5. `pulumi up` faalt op een passphrase

**Symptoom**

```
error: getting stack configuration: get stack secrets manager: passphrase must be
set with PULUMI_CONFIG_PASSPHRASE or PULUMI_CONFIG_PASSPHRASE_FILE ...
```

**Oorzaak** — De local-backend stack draagt een `encryptionsalt`, dus elke
`pulumi up`/`preview`/`destroy` wil een passphrase — ook al heeft deze demo geen
secrets.

**Fix** — De Tiltfile zet `PULUMI_CONFIG_PASSPHRASE=""` zelf, dus voor `tilt up`
hoef je niks te doen. Draai je Pulumi-commando's met de hand, zet 'm dan leeg:

```sh
export PULUMI_CONFIG_PASSPHRASE=""
```

---

## 6. `tilt up` zegt "success" maar de `spark-demo` namespace is leeg

**Symptoom** — Tilt is groen, maar `kubectl get pods -n spark-demo` geeft niks; de
pulumi-up-log zegt iets als `10 unchanged` zonder iets aan te maken.

**Oorzaak** — De Pulumi-state denkt dat de resources al bestaan (van een eerdere
cluster), terwijl de cluster opnieuw is aangemaakt en dus leeg is. Zonder refresh
vertrouwt `pulumi up` blind op de state en maakt niks aan.

**Fix** — Opgelost in de Tiltfile: `pulumi-up` draait met `--refresh`, dus Pulumi
verzoent eerst de state met de echte cluster en maakt ontbrekende resources opnieuw
aan. Zit je vast op een oude versie of wil je het handmatig forceren:

```sh
cd pulumi
PULUMI_CONFIG_PASSPHRASE="" uv run pulumi up --yes --skip-preview --refresh --stack dev --non-interactive
```

---

## 7. Verweesde resources na een `pulumi destroy`

**Symptoom** — Na opruimen draaien er nog pods in minikube die Pulumi niet meer
"kent", of een nieuwe `tilt up` botst op al-bestaande namen.

**Oorzaak** — `pulumi destroy` werkt tegen je *huidige* kube-context. Stond die op
`docker-desktop`/`rancher-desktop`, dan verwijderde destroy uit de **verkeerde**
cluster (no-op), haalde de resources uit de Pulumi-state, en bleven de échte pods in
minikube verweesd achter.

**Fix** — Pin altijd de context vóór destroy (zo staat het ook in README →
*Opruimen*):

```sh
minikube update-context -p spark-demo
cd pulumi && PULUMI_CONFIG_PASSPHRASE="" uv run pulumi destroy --yes
```

Al verweesd? Sloop de namespace direct, of gooi het hele profiel weg:

```sh
minikube update-context -p spark-demo && kubectl delete namespace spark-demo
# of, voor een gegarandeerd schone lei:
minikube delete -p spark-demo
```

---

## 8. Pulumi-state resetten na `minikube delete` (clean restart)

**Symptoom** — Je hebt het profiel weggegooid zónder eerst `pulumi destroy` te
draaien; nu denkt Pulumi dat de (verdwenen) resources nog bestaan.

**Oorzaak** — Cluster en state liepen niet gelijk leeg. Zie ook #6.

**Fix** — Reset de stack-state (of vertrouw simpelweg op `--refresh` bij de
volgende `tilt up`, zie #6). Handmatige harde reset:

```sh
cd pulumi
PULUMI_CONFIG_PASSPHRASE="" uv run pulumi stack rm dev --yes --force
git checkout -- Pulumi.dev.yaml          # stack rm verwijdert dit config-bestand
PULUMI_CONFIG_PASSPHRASE="" uv run pulumi stack init dev   # lege state, klaar voor tilt up
```

---

## 9. `tilt up`: "another process on port 10350"

**Symptoom**

```
Tilt cannot start because you already have another process on port 10350
```

**Oorzaak** — Er draait al een `tilt up`.

**Fix** — Gebruik de bestaande sessie (open <http://localhost:10350>), of stop de
oude:

```sh
lsof -nP -iTCP:10350 -sTCP:LISTEN     # vind de PID
# stop die tilt-sessie netjes (Ctrl-C in z'n terminal) of: kill <PID>
```

---

## 10. dbt-smoke faalt te verbinden met Thrift

**Symptoom** — `dbt seed/run/test` hangt of geeft een connection error op
`localhost:10000`.

**Oorzaak** — De port-forward `pf-thrift` draait niet (groen in Tilt?), of de
Thrift-pod is nog bezig met het downloaden van de Delta-packages bij het opstarten.

**Fix**

- Check in de Tilt-UI dat `pf-thrift` groen is en `spark-thrift` Running.
- Geef de pod even tijd; eerste start trekt packages via Maven (`--packages`).
- Logs: `kubectl --context spark-demo logs -n spark-demo deploy/spark-thrift -f`.

---

## 11. Notebook ziet de dbt-tabellen niet

**Symptoom** — Tabellen die `dbt-smoke` via Thrift maakt (`orders`, `stg_orders`,
`revenue_per_day`) zie je niet in `notebooks/01_hello_spark.ipynb`.

**Oorzaak** — Dit is **by design**, geen bug. Spark Connect en Spark Thrift draaien
als gescheiden Spark-applicaties met elk een eigen in-memory catalog. Zonder
gedeelde Hive Metastore zien ze elkaars tabellen niet.

**Fix** — Geen; het meegeleverde notebook is daarom self-contained. Voor gedeelde
state: zie de v2-sectie (Hive Metastore) in de README.

---

## 12. Spark master-UI (`localhost:8080`) geeft "connection refused"

**Symptoom** — De port-forward start, maar de UI laadt niet en de logs tonen:

```
kubectl port-forward -n spark-demo svc/spark-master 8080:8080
Forwarding from 127.0.0.1:8080 -> 8080
Handling connection for 8080
E... an error occurred forwarding 8080 -> 8080: ... socat[...] E connect(..., AF=2 127.0.0.1:8080, 16): Connection refused
error: lost connection to pod
```

De master-pod is `Running`, dus dit lijkt onlogisch.

**Oorzaak** — `kubectl port-forward` verbindt met de **loopback** (`127.0.0.1`)
binnen de pod. De standalone Spark-master bindt zijn web-UI (Jetty op 8080) echter
op het adres uit `SPARK_LOCAL_IP` — en dat staat op het **pod-IP** (bewust, zodat
RPC zijn pod-IP adverteert i.p.v. de pod-naam). De UI luistert dus op
`10.244.x.x:8080`, niet op loopback, en de forward wordt geweigerd. Check het bind-
adres:

```sh
kubectl exec -n spark-demo deploy/spark-master -- sh -c "ss -ltn | grep 8080"
# fout:  10.244.x.x:8080   →  alleen pod-IP, port-forward faalt
# goed:  :::8080           →  alle interfaces, port-forward werkt
```

**Fix** — Dit is opgelost in `pulumi/__main__.py`: de master draait met
`SPARK_LOCAL_IP=0.0.0.0` (UI bindt op alle interfaces) en
`SPARK_MASTER_HOST=$(POD_IP)` (RPC blijft het pod-IP adverteren) — hetzelfde
patroon als `spark.connect.grpc.binding.host=0.0.0.0` voor Spark Connect. Zie je
toch nog de oude binding: `git pull` en draai `tilt up` opnieuw zodat `pulumi-up`
de master herstart.

> **N.B.** Een stale kube-context geeft een *vergelijkbare* fout maar dan al bij
> het verbinden met de API-server — los die eerst op (zie #4 en de sanity-check
> bovenaan) voordat je naar de bind-config kijkt.

---

## Handige diagnose-commando's

```sh
minikube profile list                                   # bestaat 'spark-demo'?
minikube status -p spark-demo                            # draait het profiel?
minikube update-context -p spark-demo                    # pin de context
kubectl --context spark-demo get all -n spark-demo       # echte cluster-state
kubectl --context spark-demo logs -n spark-demo deploy/spark-master -f
cd pulumi && PULUMI_CONFIG_PASSPHRASE="" uv run pulumi stack --show-urns   # wat Pulumi denkt te beheren
```
