"""
VMware Aria Operations API client.
Dynamically discovers all clusters — no hardcoded resource IDs.
Uses the Resources Stats API to fetch real time-series metric data.
Falls back to a local CSV file when running offline.
All operations are READ-ONLY — no writes or changes to Aria Operations.
"""

import os
import io
import time
import httpx
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("ARIA_BASE_URL", "")
USERNAME = os.getenv("ARIA_USERNAME", "")
PASSWORD = os.getenv("ARIA_PASSWORD", "")
DEV_MODE = os.getenv("APP_ENV", "development") == "development"

# No hardcoded cluster IDs — clusters are discovered dynamically at runtime.

# ── Curated metric catalogue (from live instance, read 2026-05-01) ────────────
# Grouped by category so the LLM and users can easily reference them.
METRIC_CATALOGUE = {
    "CPU": {
        "cpu|workload":                  "CPU workload (%)",
        "cpu|capacity_usagepct_average": "CPU capacity usage (%)",
        "cpu|demandPct":                 "CPU demand (%)",
        "cpu|usagemhz_average":          "CPU usage (MHz)",
        "cpu|demandmhz":                 "CPU demand (MHz)",
        "cpu|capacity_provisioned":      "CPU capacity provisioned (MHz)",
        "cpu|reservedCapacity_average":  "CPU reserved capacity (%)",
        "cpu|max_cpu_ready":             "Max CPU ready (%)",
        "cpu|max_cpu_costop":            "Max CPU co-stop (%)",
        "cpu|vcpus_to_cores_allocation_ratio": "vCPU to core ratio",
        "cpu|corecount_provisioned":     "CPU cores provisioned",
    },
    "Memory": {
        "mem|workload":                  "Memory workload (%)",
        "mem|host_usagePct":             "Memory host usage (%)",
        "mem|usage_average":             "Memory usage average (%)",
        "mem|consumed_average":          "Memory consumed (KB)",
        "mem|active_average":            "Memory active (KB)",
        "mem|granted_average":           "Memory granted (KB)",
        "mem|totalCapacity_average":     "Memory total capacity (KB)",
        "mem|reservedCapacity_average":  "Memory reserved capacity (%)",
        "mem|host_provisioned":          "Memory host provisioned (KB)",
        "mem|overhead_average":          "Memory overhead (KB)",
        "mem|swapoutRate_average":       "Memory swap out rate",
        "mem|max_vm_mem_contention":     "Max VM memory contention (%)",
    },
    "Disk": {
        "disk|read_average":             "Disk read rate (KBps)",
        "disk|write_average":            "Disk write rate (KBps)",
        "disk|totalReadLatency_average": "Disk read latency (ms)",
        "disk|totalWriteLatency_average":"Disk write latency (ms)",
        "disk|totalLatency_average":     "Disk total latency (ms)",
        "disk|usage_average":            "Disk usage (KBps)",
        "diskspace|used":                "Disk space used (%)",
        "diskspace|total_capacity":      "Disk space total capacity (GB)",
        "diskspace|total_usage":         "Disk space total usage (GB)",
        "diskspace|workload":            "Disk space workload (%)",
    },
    "Network": {
        "net|usage_average":             "Network usage (KBps)",
        "net|received_average":          "Network received (KBps)",
        "net|transmitted_average":       "Network transmitted (KBps)",
        "net|error_packets":             "Network error packets",
    },
    "Health & Badges": {
        "badge|health":                  "Health score",
        "badge|risk":                    "Risk score",
        "badge|efficiency":              "Efficiency score",
        "badge|workload":                "Workload badge score",
        "badge|compliance":              "Compliance score",
        "System Attributes|availability":"Availability (%)",
    },
    "Capacity & Forecast": {
        "OnlineCapacityAnalytics|timeRemaining":                        "Capacity time remaining (days)",
        "OnlineCapacityAnalytics|capacityRemainingPercentage":          "Capacity remaining (%)",
        "OnlineCapacityAnalytics|cpu|demand|timeRemaining":             "CPU capacity time remaining (days)",
        "OnlineCapacityAnalytics|mem|demand|timeRemaining":             "Memory capacity time remaining (days)",
        "OnlineCapacityAnalytics|diskspace|demand|timeRemaining":       "Disk capacity time remaining (days)",
    },
    "VMs & Inventory": {
        "summary|total_number_vms":      "Total VMs",
        "summary|number_running_vms":    "Running VMs",
        "summary|total_number_hosts":    "Total hosts",
        "summary|number_running_hosts":  "Running hosts",
        "summary|number_running_vcpus":  "Running vCPUs",
        "summary|avg_vm_density":        "Avg VM density per host",
        "summary|drs_unhappy_vms":       "DRS unhappy VMs",
    },
    "Cost & Sustainability": {
        "cost|totalCost":                "Total cost",
        "cost|totalCpuCost":             "CPU cost",
        "cost|totalMemoryCost":          "Memory cost",
        "sustainability|power_usage":    "Power usage (W)",
        "sustainability|co2_emission":   "CO2 emission (kg)",
    },
}

# Flat dict: metric_key → friendly label (for LLM context)
ALL_METRICS: dict[str, str] = {k: v for cat in METRIC_CATALOGUE.values() for k, v in cat.items()}

_token: str | None = None
_token_acquired_at: float = 0
TOKEN_TTL = 1800  # re-acquire token after 30 min


# ── Auth ──────────────────────────────────────────────────────────────────────
def _acquire_token() -> str:
    global _token, _token_acquired_at
    resp = httpx.post(
        f"{BASE_URL}/auth/token/acquire",
        json={"username": USERNAME, "password": PASSWORD},
        headers={"Accept": "application/json"},
        verify=not DEV_MODE,
        timeout=15,
    )
    resp.raise_for_status()
    _token = resp.json()["token"]
    _token_acquired_at = time.time()
    return _token


def _headers() -> dict:
    if not _token or (time.time() - _token_acquired_at) > TOKEN_TTL:
        _acquire_token()
    return {
        "Authorization": f"vRealizeOpsToken {_token}",
        "Accept": "application/json",
    }


# ── Cluster discovery ─────────────────────────────────────────────────────────
def list_clusters() -> dict[str, str]:
    """
    Dynamically fetch all ClusterComputeResource objects from Aria Operations.
    Returns a dict of {cluster_name: resource_id}.
    READ-ONLY.
    """
    resp = httpx.get(
        f"{BASE_URL}/resources",
        params={
            "resourceKind": "ClusterComputeResource",
            "pageSize":     200,
        },
        headers=_headers(),
        verify=not DEV_MODE,
        timeout=30,
    )
    resp.raise_for_status()

    clusters = {}
    for r in resp.json().get("resourceList", []):
        name = r["resourceKey"]["name"]
        rid  = r["identifier"]
        clusters[name] = rid

    if not clusters:
        raise ValueError("No clusters found in Aria Operations.")

    return clusters


# ── Core data fetch ────────────────────────────────────────────────────────────
def _fetch_cluster_metrics(
    cluster_name: str,
    cluster_id: str,
    stat_keys: list[str],
    start_ms: int,
    end_ms: int,
) -> pd.DataFrame:
    """Fetch metrics for a single cluster and return a tidy DataFrame."""
    resp = httpx.get(
        f"{BASE_URL}/resources/{cluster_id}/stats",
        params={
            "statKey":      stat_keys,
            "begin":        start_ms,
            "end":          end_ms,
            "rollUpType":   "AVG",
            "intervalType": "DAYS",
        },
        headers=_headers(),
        verify=not DEV_MODE,
        timeout=30,
    )
    resp.raise_for_status()

    values = resp.json().get("values", [])
    if not values:
        raise ValueError(f"No data returned for cluster '{cluster_name}': {stat_keys}")

    stat_list = values[0].get("stat-list", {}).get("stat", [])
    if not stat_list:
        raise ValueError(f"Empty stat-list for cluster '{cluster_name}'.")

    frames = []
    for series in stat_list:
        key   = series["statKey"]["key"]
        label = ALL_METRICS.get(key, key)
        times = series.get("timestamps", [])
        vals  = series.get("data", [])
        df_s  = pd.DataFrame({
            "timestamp": pd.to_datetime(times, unit="ms"),
            label:       vals,
        })
        frames.append(df_s.set_index("timestamp"))

    df = pd.concat(frames, axis=1).reset_index()
    df.insert(0, "Name", cluster_name)
    return df


def fetch_metrics(
    stat_keys: list[str],
    last_days: int = 30,
    selected_clusters: dict[str, str] | None = None,
) -> pd.DataFrame:
    """
    Fetch time-series stats for one or more clusters.
    selected_clusters: dict of {name: resource_id} as returned by list_clusters().
    Returns a tidy DataFrame with columns: Name, timestamp, one col per metric.
    READ-ONLY — never modifies Aria Operations.
    """
    if not selected_clusters:
        raise ValueError("No clusters provided to fetch_metrics().")

    end_ms   = int(time.time() * 1000)
    start_ms = end_ms - (last_days * 86400 * 1000)

    frames = []
    for name, cluster_id in selected_clusters.items():
        df = _fetch_cluster_metrics(name, cluster_id, stat_keys, start_ms, end_ms)
        frames.append(df)

    return pd.concat(frames, ignore_index=True)


# ── Local CSV fallback ────────────────────────────────────────────────────────
def load_local_csv(path: str) -> pd.DataFrame:
    """Load a local CSV file — used when running offline or for demo data."""
    with open(path, "rb") as f:
        return _parse_csv(f.read())


def _parse_csv(raw: bytes) -> pd.DataFrame:
    df = pd.read_csv(
        io.BytesIO(raw),
        encoding="utf-8-sig",
        na_values=["-", "", "N/A"],
    )
    df.columns = [c.strip() for c in df.columns]
    for col in df.columns:
        if any(k in col.lower() for k in ("time", "date", "stamp")):
            df[col] = pd.to_datetime(df[col], errors="coerce")
    for col in df.columns:
        if df[col].dtype == object:
            converted = pd.to_numeric(df[col], errors="coerce")
            if converted.notna().sum() > 0:
                df[col] = converted
    return df
