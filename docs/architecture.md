# Architectuur (C4-model)

Drie zoom-niveaus volgens [C4](https://c4model.com): context, container en component. Mermaid-blokken renderen op GitHub.

## Level 1 — System Context

Wie/wat raakt `spark-demo` aan?

```mermaid
C4Context
    title spark-demo — System Context

    Person(dev, "Developer", "Schrijft dbt-modellen en notebooks op een MacBook")

    System(sparkdemo, "spark-demo", "Lokaal Apache Spark 4 + Delta cluster op minikube. dbt-on-Spark via Thrift, notebooks via Spark Connect.")

    System_Ext(maven, "Maven Central", "Bron van delta-spark + spark-connect jars")
    System_Ext(dockerhub, "Docker Hub", "apache/spark:4.0.3 image")
    System_Ext(github, "GitHub", "Code-hosting + versioning")
    System_Ext(databricks, "Databricks Cloud", "Productie-target (referentie) — niet verbonden")

    Rel(dev, sparkdemo, "Schrijft dbt-modellen, queries via notebook", "uv, tilt, kubectl")
    Rel(dev, github, "Push code", "git+ssh")
    Rel(sparkdemo, maven, "Pull jars (eerste pod-start)", "HTTPS")
    Rel(sparkdemo, dockerhub, "Pull image bij scheduling", "HTTPS")

    Rel(dev, databricks, "Concepten 1-op-1 overdraagbaar", "spark-connect protocol")

    UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="2")
```

**Wat dit zegt:** `spark-demo` staat lokaal op je laptop, leunt op publieke registries voor zijn dependencies en is bewust **niet** verbonden met Databricks Cloud — de waarde zit erin dat het *concept*-niveau identiek is.

## Level 2 — Container

Wat draait er, en in welke runtime?

```mermaid
C4Container
    title spark-demo — Container Diagram

    Person(dev, "Developer")

    System_Boundary(laptop, "MacBook") {
        Container(vscode, "VS Code", "Editor + Jupyter ext", "Notebooks, kernel uit .venv")
        Container(terminal, "Terminal", "zsh", "tilt, pulumi, uv, kubectl, dbt")
        Container(venv, ".venv", "Python 3.13 (uv)", "pyspark[connect], dbt-spark, pulumi")

        Container(docker, "Docker Daemon", "Rancher Desktop", "Container runtime")

        Container_Boundary(mk, "minikube VM (in Docker)") {
            Container(k8s, "Kubernetes API", "v1.33", "Schedulet pods, beheert state")

            Container_Boundary(ns, "namespace: spark-demo") {
                Container(master, "spark-master", "Spark 4.0.3 daemon", "Cluster manager + UI :8080")
                Container(worker, "spark-worker", "Spark 4.0.3 daemon", "Compute (cores, memory)")
                Container(thrift, "spark-thrift", "Spark application", "Hive JDBC :10000 (voor dbt)")
                Container(connect, "spark-connect", "Spark application", "gRPC :15002 (voor notebooks)")
            }
        }
    }

    System_Ext(maven, "Maven Central")
    System_Ext(dockerhub, "Docker Hub")

    Rel(dev, vscode, "Opent .ipynb")
    Rel(dev, terminal, "Runs cmds")
    Rel(vscode, venv, "kernel")
    Rel(terminal, venv, "uv run")
    Rel(terminal, k8s, "kubectl / k9s")

    Rel(venv, connect, "PySpark", "gRPC :15002")
    Rel(venv, thrift, "dbt-spark / PyHive", "Thrift :10000")

    Rel(k8s, master, "create/manage")
    Rel(k8s, worker, "create/manage")
    Rel(k8s, thrift, "create/manage")
    Rel(k8s, connect, "create/manage")

    Rel(worker, master, "register + heartbeat", "RPC :7077")
    Rel(thrift, master, "submit driver", "RPC :7077")
    Rel(connect, master, "submit driver", "RPC :7077")
    Rel(thrift, worker, "launch executor", "RPC")
    Rel(connect, worker, "launch executor", "RPC")

    Rel(thrift, maven, "Delta jar", "HTTPS")
    Rel(connect, maven, "Connect + Delta jars", "HTTPS")
    Rel(docker, dockerhub, "image pull", "HTTPS")

    UpdateLayoutConfig($c4ShapeInRow="4", $c4BoundaryInRow="2")
```

**Wat dit zegt:**
- Op de laptop draaien tools (terminal, VS Code) en één gedeelde Python-venv.
- De `.venv` is de client-side voor zowel notebooks (via Spark Connect) als dbt (via Thrift).
- In minikube draaien vier Spark-onderdelen die elk met de master praten.
- Workers krijgen taken via spark-submit van Thrift en Connect.
- Maven en Docker Hub zijn de enige externe afhankelijkheden bij opstart.

## Level 3 — Component (Pulumi-managed K8s resources)

Wat Pulumi precies in de cluster zet:

```mermaid
C4Component
    title spark-demo — Components (Kubernetes resources in namespace `spark-demo`)

    Container_Boundary(ns, "namespace: spark-demo") {
        Component(cm, "ConfigMap: spark-conf", "K8s ConfigMap", "spark-defaults.conf: Delta package, Ivy cache pad, resource-limieten, NOSASL, Connect-binding")

        Component(svc_master, "Service: spark-master", "ClusterIP", ":7077 (RPC) + :8080 (UI)")
        Component(svc_thrift, "Service: spark-thrift", "ClusterIP", ":10000 (Hive Thrift)")
        Component(svc_connect, "Service: spark-connect", "ClusterIP", ":15002 (gRPC)")

        Component(dep_master, "Deployment: spark-master", "1 replica", "start-master.sh in foreground")
        Component(dep_worker, "Deployment: spark-worker", "N replicas", "start-worker.sh + master URL")
        Component(dep_thrift, "Deployment: spark-thrift", "1 replica", "start-thriftserver.sh + Delta package")
        Component(dep_connect, "Deployment: spark-connect", "1 replica", "start-connect-server.sh + Connect + Delta packages")
    }

    Rel(svc_master, dep_master, "selector app=spark-master")
    Rel(svc_thrift, dep_thrift, "selector app=spark-thrift")
    Rel(svc_connect, dep_connect, "selector app=spark-connect")

    Rel(cm, dep_master, "mount /opt/spark/conf/spark-defaults.conf")
    Rel(cm, dep_worker, "mount")
    Rel(cm, dep_thrift, "mount")
    Rel(cm, dep_connect, "mount")

    UpdateLayoutConfig($c4ShapeInRow="2", $c4BoundaryInRow="1")
```

**Wat dit zegt:**
- Eén ConfigMap (`spark-conf`) die door alle vier Deployments wordt gemount.
- Drie Services exposen poorten naar de port-forward-keten.
- Worker heeft geen eigen Service (workers worden via de master gevonden).
- Alle vier Deployments delen hetzelfde `apache/spark:4.0.3` image; verschil zit alleen in `command` + `args`.

## Wat NIET in een C4 zit (maar wel het noemen waard)

- **Tilt** zelf is geen component in de cluster — het is een orchestratie-tool op de laptop die `pulumi up` aanroept, K8s-resources observeert en port-forwards opzet. Conceptueel zit hij naast "Terminal" in Level 2.
- **uv** is een dependency-manager voor de venv, niet een service.
- **Pulumi state** leeft in `~/.pulumi/` lokaal (geen externe backend).
