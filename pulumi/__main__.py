"""Pulumi-programma: lokaal Spark + Delta cluster.

Creëert een namespace en vier Deployments (met Services):
- spark-master   : cluster manager + web UI (8080)
- spark-worker   : compute, schaalbaar via workerReplicas
- spark-thrift   : Hive Thrift Server op 10000 (dbt-spark)
- spark-connect  : Spark Connect Server op 15002 (notebooks)

Alle vier gebruiken hetzelfde apache/spark-image; verschillen zitten in command
en argumenten. Spark-config (incl. Delta-packages) komt uit een ConfigMap die
in elke pod wordt gemount.
"""

from pathlib import Path

import pulumi
from pulumi_kubernetes.apps.v1 import Deployment
from pulumi_kubernetes.core.v1 import ConfigMap, Namespace, Service

cfg = pulumi.Config()
NS = cfg.get("namespace") or "spark-demo"
IMAGE = cfg.get("sparkImage") or "apache/spark:4.0.3"
WORKER_REPLICAS = cfg.get_int("workerReplicas") or 1
WORKER_MEMORY = cfg.get("workerMemory") or "2g"
WORKER_CORES = cfg.get("workerCores") or "2"

SPARK_HOME = "/opt/spark"
# Spark 4 → Scala 2.13.
DELTA_PKG = "io.delta:delta-spark_2.13:4.0.0"
# Spark Connect heeft eigen package nodig + Delta voor de catalog.
SPARK_CONNECT_PKG = f"org.apache.spark:spark-connect_2.13:4.0.3,{DELTA_PKG}"
MASTER_URL = "spark://spark-master:7077"

ns = Namespace("spark-demo-ns", metadata={"name": NS})

_conf_path = Path(__file__).parent.parent / "spark" / "spark-defaults.conf"
spark_conf = ConfigMap(
    "spark-conf",
    metadata={"name": "spark-conf", "namespace": NS},
    data={"spark-defaults.conf": _conf_path.read_text()},
    opts=pulumi.ResourceOptions(depends_on=[ns]),
)


def _volume_mounts() -> list[dict]:
    return [
        {
            "name": "spark-conf",
            "mount_path": f"{SPARK_HOME}/conf/spark-defaults.conf",
            "sub_path": "spark-defaults.conf",
        }
    ]


def _volumes() -> list[dict]:
    return [{"name": "spark-conf", "config_map": {"name": "spark-conf"}}]


def make_deployment(
    name: str,
    *,
    command: list[str],
    env: dict[str, str] | None = None,
    ports: list[tuple[str, int]] | None = None,
    replicas: int = 1,
    local_ip: str = "$(POD_IP)",
) -> Deployment:
    labels = {"app": name}
    # POD_IP wordt door K8s ingevuld; SPARK_LOCAL_IP zorgt dat Spark zijn pod-IP
    # adverteert i.p.v. de pod-naam (die anders via search-domain corporate-DNS
    # zou raken). Voor zowel master, worker, thrift als connect identiek.
    #
    # Uitzondering: de master zet local_ip="0.0.0.0" zodat de web-UI (Jetty op
    # 8080) op alle interfaces bindt — anders bindt Spark de UI alleen op het
    # pod-IP en weigert `kubectl port-forward` (loopback) de verbinding. De
    # master adverteert zijn RPC-adres dan los via SPARK_MASTER_HOST=$(POD_IP),
    # dus pod-IP-advertentie blijft intact. Zelfde patroon als Spark Connect
    # (`spark.connect.grpc.binding.host=0.0.0.0`) in spark-defaults.conf.
    base_env: list[dict] = [
        {"name": "POD_IP", "value_from": {"field_ref": {"field_path": "status.podIP"}}},
        {"name": "SPARK_LOCAL_IP", "value": local_ip},
    ]
    extra_env = [{"name": k, "value": v} for k, v in (env or {}).items()]
    container: dict = {
        "name": name,
        "image": IMAGE,
        "command": command,
        "env": base_env + extra_env,
        "volume_mounts": _volume_mounts(),
    }
    if ports:
        container["ports"] = [{"name": pn, "container_port": pp} for pn, pp in ports]
    return Deployment(
        name,
        metadata={"name": name, "namespace": NS},
        spec={
            "replicas": replicas,
            "selector": {"match_labels": labels},
            "template": {
                "metadata": {"labels": labels},
                "spec": {
                    "enable_service_links": False,
                    # ndots:2 voorkomt dat externe hosts zoals repo1.maven.org
                    # eerst via de search-domain (bv. corporate DNS) worden geprobeerd.
                    "dns_config": {
                        "options": [{"name": "ndots", "value": "2"}],
                    },
                    "containers": [container],
                    "volumes": _volumes(),
                },
            },
        },
        opts=pulumi.ResourceOptions(depends_on=[ns, spark_conf]),
    )


def make_service(name: str, ports: list[tuple[str, int]]) -> Service:
    return Service(
        f"{name}-svc",
        metadata={"name": name, "namespace": NS},
        spec={
            "selector": {"app": name},
            "ports": [{"name": pn, "port": pp, "target_port": pp} for pn, pp in ports],
        },
        opts=pulumi.ResourceOptions(depends_on=[ns]),
    )


def _foreground(script: str, *args: str) -> list[str]:
    """Run a Spark sbin/*.sh in the foreground (SPARK_NO_DAEMONIZE)."""
    # HOME=/tmp zodat Ivy zijn cache kan schrijven — apache/spark draait als user 185
    # zonder schrijfbare home, wat package-resolutie via --packages anders breekt.
    cmd = (
        f"export HOME=/tmp && SPARK_NO_DAEMONIZE=1 exec "
        f"{SPARK_HOME}/sbin/{script} " + " ".join(args)
    )
    return ["/bin/bash", "-c", cmd]


# Master
# local_ip=0.0.0.0 bindt de web-UI op alle interfaces (port-forward werkt);
# SPARK_MASTER_HOST=$(POD_IP) houdt de RPC-advertentie op het pod-IP.
make_deployment(
    "spark-master",
    command=_foreground("start-master.sh"),
    env={"SPARK_MASTER_HOST": "$(POD_IP)"},
    ports=[("rpc", 7077), ("ui", 8080)],
    local_ip="0.0.0.0",
)
make_service("spark-master", [("rpc", 7077), ("ui", 8080)])

# Worker(s)
make_deployment(
    "spark-worker",
    command=_foreground(
        "start-worker.sh",
        f"--memory {WORKER_MEMORY}",
        f"--cores {WORKER_CORES}",
        MASTER_URL,
    ),
    replicas=WORKER_REPLICAS,
)

# --conf flags zorgen dat de driver zijn pod-IP adverteert i.p.v. de pod-naam,
# zodat executors niet via DNS hoeven te resolven (anders breekt het op
# hosts met een opdringerige search-domain).
_DRIVER_HOST_FLAGS = (
    "--conf spark.driver.host=$POD_IP "
    "--conf spark.driver.bindAddress=0.0.0.0"
)

# Thrift Server (dbt verbindt hier op 10000)
make_deployment(
    "spark-thrift",
    command=_foreground(
        "start-thriftserver.sh",
        f"--master {MASTER_URL}",
        _DRIVER_HOST_FLAGS,
        f"--packages {DELTA_PKG}",
        "--name thrift-server",
    ),
    ports=[("hive", 10000)],
)
make_service("spark-thrift", [("hive", 10000)])

# Spark Connect Server (notebooks verbinden hier op 15002)
make_deployment(
    "spark-connect",
    command=_foreground(
        "start-connect-server.sh",
        f"--master {MASTER_URL}",
        _DRIVER_HOST_FLAGS,
        f"--packages {SPARK_CONNECT_PKG}",
        "--name connect-server",
    ),
    ports=[("grpc", 15002)],
)
make_service("spark-connect", [("grpc", 15002)])

pulumi.export("namespace", NS)
pulumi.export("master_ui_pf", f"kubectl port-forward -n {NS} svc/spark-master 8080:8080")
pulumi.export("thrift_pf", f"kubectl port-forward -n {NS} svc/spark-thrift 10000:10000")
pulumi.export("connect_pf", f"kubectl port-forward -n {NS} svc/spark-connect 15002:15002")
