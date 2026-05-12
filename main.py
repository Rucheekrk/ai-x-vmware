"""
Demo CLI — AI-powered VMware Aria Operations reporting.
All Aria Operations access is READ-ONLY.

Flow:
  Option 1 — Local CSV
    Load CSV(s) from data/ folder → user describes charts → build → PDF

  Option 2 — Live Aria Operations (READ-ONLY, requires user approval each time)
    Discover clusters → user selects clusters →
    user describes what data + chart they want →
    GPT fetches right metrics from Aria →
    GPT auto-builds chart spec from same prompt →
    User confirms → build → add more charts or done → PDF
"""

import os
import sys
import pandas as pd
import questionary
import aria_client
import llm
import chart
import report

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def _divider():
    print("\n─────────────────────────────────────────")


def pick_data_source():
    _divider()
    print("  VMware Aria Operations — AI Demo")
    _divider()
    print("\nData source:")
    print("  1. Load local CSV file(s)  (offline / demo)")
    print("  2. Fetch live data from Aria Operations  ⚠  READ-ONLY, requires your approval")
    choice = input("\nChoice [1/2]: ").strip()

    if choice == "2":
        print(
            "\n⚠  This will connect to https://10.89.19.50 using stored credentials."
            "\n   All operations are READ-ONLY — no changes will be made to Aria Operations."
            "\n   Clusters will be listed for your selection."
        )
        confirm = input("   Do you approve this connection? [yes/no]: ").strip().lower()
        if confirm != "yes":
            print("Connection not approved. Falling back to local CSV.")
            choice = "1"

    if choice == "2":
        return _fetch_from_aria()
    else:
        return _load_local_csv(), None


def _select_clusters() -> dict[str, str]:
    """Discover all clusters from Aria Operations and let the user pick."""
    print("\nDiscovering clusters from Aria Operations...")
    all_clusters = aria_client.list_clusters()

    cluster_list = list(all_clusters.items())  # [(name, id), ...]
    print(f"\nFound {len(cluster_list)} cluster(s):")
    for i, (name, _) in enumerate(cluster_list, 1):
        print(f"  {i}. {name}")

    print("\nSelect clusters to include (e.g. '1', '1,2', or 'all'):")
    choice = input("> ").strip().lower()

    if choice == "all":
        selected = dict(cluster_list)
    else:
        indices = [int(x.strip()) - 1 for x in choice.split(",")]
        selected = {cluster_list[i][0]: cluster_list[i][1] for i in indices}

    print(f"\nSelected: {', '.join(selected.keys())}")
    return selected


def _fetch_from_aria():
    selected_clusters = _select_clusters()

    print("\nWhat do you want to see? Describe the data AND the chart in one sentence.")
    print("Examples:")
    print('  "Bar graph of CPU and memory workload per month for the last 6 months"')
    print('  "Line chart of disk read and write latency for the last 2 weeks"')
    print('  "Bar chart of health score and risk score for the last month"')
    user_prompt = input("\n> ").strip()

    print("\nIdentifying the right metrics...")
    stat_keys, last_days = llm.match_metrics(user_prompt)

    print(f"\nMetrics selected ({last_days} days of history):")
    for key in stat_keys:
        label = aria_client.ALL_METRICS.get(key, key)
        print(f"  • {label}")

    confirm = input("\nFetch this data from Aria Operations? [yes/no]: ").strip().lower()
    if confirm != "yes":
        print("Cancelled.")
        sys.exit(0)

    print(f"\nFetching data from {', '.join(selected_clusters.keys())} (READ-ONLY)...")
    df = aria_client.fetch_metrics(stat_keys, last_days=last_days, selected_clusters=selected_clusters)
    print(f"✓ Fetched {len(df)} rows, {len(df.columns)-2} metrics")

    return df, user_prompt


def _load_local_csv():
    os.makedirs(DATA_DIR, exist_ok=True)
    csv_files = sorted([f for f in os.listdir(DATA_DIR) if f.endswith(".csv")])

    if not csv_files:
        print(f"\nNo CSV files found in {DATA_DIR}/")
        print("Add CSV files to the data/ folder and try again.")
        sys.exit(1)

    print(f"\nFound {len(csv_files)} CSV file(s) in data/")
    selected = questionary.checkbox(
        "Select CSV file(s) to load  (Space to select, Enter to confirm):",
        choices=csv_files,
    ).ask()

    if not selected:
        print("No files selected. Exiting.")
        sys.exit(0)

    frames = []
    for filename in selected:
        path = os.path.join(DATA_DIR, filename)
        df   = aria_client.load_local_csv(path)
        # If the CSV has no Name column, use the filename (without extension) as Name
        if not any(c.lower() == "name" for c in df.columns):
            df.insert(0, "Name", os.path.splitext(filename)[0])
        frames.append(df)
        print(f"  ✓ Loaded {len(df)} rows from {filename}")

    combined = pd.concat(frames, ignore_index=True)
    print(f"\n✓ Total: {len(combined)} rows across {len(selected)} file(s)")
    return combined


def _build_chart_from_prompt(user_input, cols, entities):
    """Parse a chart spec and confirm with user before building."""
    print("\nBuilding chart spec...")
    try:
        spec = llm.parse_user_request(user_input, cols, entities)
    except Exception as e:
        print(f"  Error parsing request: {e}")
        return None

    print(f"\n  Chart type : {spec.get('chart_type')}")
    print(f"  Entities   : {', '.join(spec.get('entities') or ['all'])}")
    print(f"  Metrics    : {', '.join(spec.get('columns', []))}")
    print(f"  Title      : {spec.get('title')}")

    confirm = input("\nBuild this chart? [yes/no]: ").strip().lower()
    if confirm != "yes":
        print("  Skipped.")
        return None
    return spec


def main():
    result = pick_data_source()

    # pick_data_source returns (df, prompt) for Aria path, (df, None) for CSV path
    if isinstance(result, tuple):
        df, initial_prompt = result
    else:
        df, initial_prompt = result, None

    cols     = [c for c in df.columns if c.lower() not in ("name", "timestamp")]
    name_col = next((c for c in df.columns if c.lower() == "name"), None)
    entities = sorted(df[name_col].dropna().unique().tolist()) if name_col else []

    print(f"\nEntities : {', '.join(str(e) for e in entities) or 'N/A'}")
    print(f"Metrics available:")
    for c in cols:
        print(f"  • {c}  ({df[c].notna().sum()} data points)")

    chart_paths = []
    chart_specs = []

    # For Aria path: reuse the initial prompt to auto-build the first chart
    # For CSV path: ask the user what chart they want first
    if not initial_prompt:
        _divider()
        print("Examples:")
        print('  "Bar graph of CPU and memory usage per month for the last 6 months"')
        print('  "Line chart of CPU usage over time"')
        initial_prompt = input(
            "\nDescribe the first chart you want:\n> "
        ).strip()

    if initial_prompt:
        _divider()
        print(f"Building chart from: \"{initial_prompt}\"")
        spec = _build_chart_from_prompt(initial_prompt, cols, entities)
        if spec:
            try:
                png_path = chart.build_chart(df, spec)
                chart_paths.append(png_path)
                chart_specs.append(spec)
                print(f"  ✓ Chart built")
            except Exception as e:
                print(f"  ⚠ Chart skipped: {e}")

    # Loop for additional charts
    while True:
        _divider()
        user_input = input(
            "Add another chart  (or 'done' to generate PDF report):\n> "
        ).strip()

        if user_input.lower() in ("done", "exit", "quit", ""):
            break

        spec = _build_chart_from_prompt(user_input, cols, entities)
        if spec:
            try:
                png_path = chart.build_chart(df, spec)
                chart_paths.append(png_path)
                chart_specs.append(spec)
                print(f"  ✓ Chart built")
            except Exception as e:
                print(f"  ⚠ Chart skipped: {e}")

    if not chart_paths:
        print("\nNo charts built — nothing to report. Exiting.")
        return

    print("\nGenerating executive summary...")
    summary = llm.generate_summary(df, chart_specs)

    title = input("\nReport title [Infrastructure Performance Report]: ").strip()
    if not title:
        title = "Infrastructure Performance Report"
    else:
        corrected = llm.correct_title(title)
        if corrected != title:
            print(f"  Title corrected to: \"{corrected}\"")
        title = corrected

    print("Building PDF report...")
    pdf_path = report.generate_pdf(chart_paths, chart_specs, summary, title)
    print(f"\n✓ PDF report saved: {pdf_path}")
    os.system(f"open '{pdf_path}'")


if __name__ == "__main__":
    main()
