"""
Streamlit UI — AI-powered VMware Aria Operations reporting.
Run with: streamlit run app.py
All Aria Operations access is READ-ONLY.
"""

import os
import pandas as pd
import streamlit as st
from PIL import Image as PILImage

import aria_client
import llm
import chart
import report

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="VMware Aria Operations — AI Reporting",
    page_icon="📊",
    layout="wide",
)

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .block-container { padding-top: 2rem; }
    .stButton > button {
        background-color: #1d4ed8;
        color: white;
        border: none;
        border-radius: 6px;
        padding: 0.5rem 1.5rem;
        font-weight: 600;
        font-size: 0.95rem;
    }
    .stButton > button:hover { background-color: #1e40af; color: white; }
    .metric-box {
        background: #eff6ff;
        border-left: 4px solid #1d4ed8;
        padding: 0.75rem 1rem;
        border-radius: 4px;
        margin: 0.5rem 0;
        font-size: 0.9rem;
        color: #1e3a5f;
    }
    .success-box {
        background: #ecfdf5;
        border-left: 4px solid #059669;
        padding: 0.75rem 1rem;
        border-radius: 4px;
        margin: 0.5rem 0;
        color: #065f46;
        font-weight: 600;
    }
    .warning-box {
        background: #fffbeb;
        border-left: 4px solid #d97706;
        padding: 0.75rem 1rem;
        border-radius: 4px;
        margin: 0.5rem 0;
        color: #78350f;
    }
    .section-header {
        font-size: 1.1rem;
        font-weight: 700;
        color: #0f2d55;
        margin-bottom: 0.75rem;
        padding-bottom: 0.4rem;
        border-bottom: 2px solid #1d4ed8;
    }
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div style='background: linear-gradient(135deg, #0f2d55 0%, #1d4ed8 100%);
            padding: 1.75rem 2rem; border-radius: 10px; margin-bottom: 1.5rem;'>
    <h2 style='color: white; margin: 0; font-size: 1.8rem;'>VMware Aria Operations</h2>
    <p style='color: #93c5fd; margin: 0.25rem 0 0 0; font-size: 1rem;'>AI-Powered Infrastructure Reporting</p>
</div>
""", unsafe_allow_html=True)

st.divider()

# ── Session state init ────────────────────────────────────────────────────────
for key, default in {
    "df": None,
    "chart_paths": [],
    "chart_specs": [],
    "chart_images": [],
    "data_loaded": False,
    "source": None,
    "clusters": {},
    "summary": "",
    "pdf_path": "",
    "step": "source",
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


# ── Step 1: Choose data source ────────────────────────────────────────────────
if st.session_state.step == "source":
    st.markdown('<div class="section-header">Step 1 — Choose Data Source</div>', unsafe_allow_html=True)
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("""
        <div style='border:1px solid #bfdbfe; border-radius:10px; padding:1.75rem; background:white; height:240px;
                    box-shadow: 0 2px 8px rgba(15,45,85,0.08);'>
            <h4 style='color:#0f2d55; margin:0 0 0.75rem 0; font-size:1.1rem;'>📁 Option 1 — Local CSV</h4>
            <p style='color:#374151; font-size:0.92rem; margin:0; line-height:1.6;'>
                Load exported CSV files from the <code>data/</code> folder.<br><br>
                No network connection required. Ideal for offline demos and testing.
            </p>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("")
        if st.button("Load Local CSV File", use_container_width=True):
            st.session_state.source = "csv"
            st.session_state.step = "csv_load"
            st.rerun()

    with col2:
        st.markdown("""
        <div style='border:1px solid #bfdbfe; border-radius:10px; padding:1.75rem; background:white; height:240px;
                    box-shadow: 0 2px 8px rgba(15,45,85,0.08);'>
            <h4 style='color:#0f2d55; margin:0 0 0.75rem 0; font-size:1.1rem;'>🔌 Option 2 — Live Aria Operations</h4>
            <p style='color:#374151; font-size:0.92rem; margin:0; line-height:1.6;'>
                Connect live to VMware Aria Operations and fetch real-time metrics from your clusters.<br><br>
                <strong style='color:#059669;'>READ-ONLY</strong> — no changes are made to your environment.
            </p>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("")
        if st.button("Connect to Aria Operations", use_container_width=True):
            st.session_state.source = "aria"
            st.session_state.step = "aria_connect"
            st.rerun()


# ── Step 2a: Load CSV ─────────────────────────────────────────────────────────
elif st.session_state.step == "csv_load":
    st.markdown('<div class="section-header">Step 2 — Select CSV File(s)</div>', unsafe_allow_html=True)

    os.makedirs(DATA_DIR, exist_ok=True)
    csv_files = sorted([f for f in os.listdir(DATA_DIR) if f.endswith(".csv")])

    if not csv_files:
        st.error(f"No CSV files found in the `data/` folder. Please add CSV files and refresh.")
        if st.button("← Back"):
            st.session_state.step = "source"
            st.rerun()
    else:
        selected = st.multiselect(
            "Select one or more CSV files to load:",
            options=csv_files,
        )

        col_back, col_load = st.columns([1, 3])
        with col_back:
            if st.button("← Back"):
                st.session_state.step = "source"
                st.rerun()
        with col_load:
            if st.button("Load Selected Files", use_container_width=True) and selected:
                with st.spinner("Loading CSV files..."):
                    frames = []
                    for filename in selected:
                        path = os.path.join(DATA_DIR, filename)
                        df = aria_client.load_local_csv(path)
                        if not any(c.lower() == "name" for c in df.columns):
                            df.insert(0, "Name", os.path.splitext(filename)[0])
                        frames.append(df)
                    st.session_state.df = pd.concat(frames, ignore_index=True)
                    st.session_state.data_loaded = True
                    st.session_state.step = "chart"
                    st.rerun()


# ── Step 2b: Connect to Aria Operations ──────────────────────────────────────
elif st.session_state.step == "aria_connect":
    st.markdown('<div class="section-header">Step 2 — Connect to Aria Operations</div>', unsafe_allow_html=True)

    st.markdown(f"""
    <div class="warning-box">
        ⚠️ This will connect to <strong>{aria_client.BASE_URL}</strong> using stored credentials.<br>
        All operations are <strong>READ-ONLY</strong> — no changes will be made to your environment.
    </div>
    """, unsafe_allow_html=True)

    col_back, col_approve = st.columns([1, 3])
    with col_back:
        if st.button("← Back"):
            st.session_state.step = "source"
            st.rerun()
    with col_approve:
        if st.button("✓ Approve Connection (Read-Only)", use_container_width=True):
            with st.spinner("Discovering clusters from Aria Operations..."):
                try:
                    clusters = aria_client.list_clusters()
                    st.session_state.clusters = clusters
                    st.session_state.step = "aria_clusters"
                    st.rerun()
                except Exception as e:
                    st.error(f"Connection failed: {e}")


# ── Step 2c: Select clusters ──────────────────────────────────────────────────
elif st.session_state.step == "aria_clusters":
    st.markdown('<div class="section-header">Step 3 — Select Clusters</div>', unsafe_allow_html=True)

    cluster_names = list(st.session_state.clusters.keys())
    st.success(f"✓ Connected — found {len(cluster_names)} cluster(s)")

    selected_names = st.multiselect(
        "Select clusters to include in the report:",
        options=cluster_names,
        default=cluster_names,
    )

    col_back, col_next = st.columns([1, 3])
    with col_back:
        if st.button("← Back"):
            st.session_state.step = "aria_connect"
            st.rerun()
    with col_next:
        if st.button("Continue →", use_container_width=True) and selected_names:
            st.session_state.step = "aria_prompt"
            st.session_state.selected_clusters = {
                name: st.session_state.clusters[name] for name in selected_names
            }
            st.rerun()


# ── Step 2d: Aria prompt + fetch ──────────────────────────────────────────────
elif st.session_state.step == "aria_prompt":
    st.markdown('<div class="section-header">Step 4 — Describe Your Data</div>', unsafe_allow_html=True)

    selected = st.session_state.get("selected_clusters", {})
    st.markdown(f"**Selected clusters:** {', '.join(selected.keys())}")

    st.markdown("Describe the data and chart you want in plain English:")
    examples = [
        "Bar graph of CPU and memory workload per month for the last 6 months",
        "Line chart of disk read and write latency for the last 2 weeks",
        "Bar chart of health score and risk score for the last month",
    ]
    for ex in examples:
        st.markdown(f"- *{ex}*")

    user_prompt = st.text_input("Your description:", placeholder="e.g. Bar chart of CPU and memory workload per month for the last 6 months")

    col_back, col_fetch = st.columns([1, 3])
    with col_back:
        if st.button("← Back"):
            st.session_state.step = "aria_clusters"
            st.rerun()
    with col_fetch:
        if st.button("Identify Metrics →", use_container_width=True) and user_prompt:
            with st.spinner("AI is identifying the right metrics..."):
                try:
                    stat_keys, last_days = llm.match_metrics(user_prompt)
                    st.session_state.stat_keys = stat_keys
                    st.session_state.last_days = last_days
                    st.session_state.initial_prompt = user_prompt
                    st.session_state.step = "aria_confirm"
                    st.rerun()
                except Exception as e:
                    st.error(f"Error identifying metrics: {e}")


# ── Step 2e: Confirm metrics and fetch ───────────────────────────────────────
elif st.session_state.step == "aria_confirm":
    st.markdown('<div class="section-header">Step 5 — Confirm Metrics</div>', unsafe_allow_html=True)

    stat_keys = st.session_state.get("stat_keys", [])
    last_days = st.session_state.get("last_days", 30)

    st.markdown(f"**AI selected the following metrics** ({last_days} days of history):")
    for key in stat_keys:
        label = aria_client.ALL_METRICS.get(key, key)
        st.markdown(f'<div class="metric-box">• {label}</div>', unsafe_allow_html=True)

    col_back, col_fetch = st.columns([1, 3])
    with col_back:
        if st.button("← Back"):
            st.session_state.step = "aria_prompt"
            st.rerun()
    with col_fetch:
        if st.button("✓ Fetch Data from Aria Operations (Read-Only)", use_container_width=True):
            selected = st.session_state.get("selected_clusters", {})
            with st.spinner(f"Fetching data from {', '.join(selected.keys())}..."):
                try:
                    df = aria_client.fetch_metrics(
                        stat_keys,
                        last_days=last_days,
                        selected_clusters=selected,
                    )
                    st.session_state.df = df
                    st.session_state.data_loaded = True
                    st.session_state.step = "chart"
                    st.rerun()
                except Exception as e:
                    st.error(f"Error fetching data: {e}")


# ── Step 3: Build charts ──────────────────────────────────────────────────────
elif st.session_state.step == "chart":
    df = st.session_state.df
    cols = [c for c in df.columns if c.lower() not in ("name", "timestamp")]
    name_col = next((c for c in df.columns if c.lower() == "name"), None)
    entities = sorted(df[name_col].dropna().unique().tolist()) if name_col else []

    # Left: chart builder | Right: chart preview
    col_left, col_right = st.columns([2, 3])

    with col_left:
        st.markdown('<div class="section-header">Build Charts</div>', unsafe_allow_html=True)

        st.markdown(f"**Available entities:** {', '.join(str(e) for e in entities) or 'N/A'}")
        st.markdown(f"**Available metrics:** {len(cols)} columns loaded")

        with st.expander("View available metrics"):
            for c in cols:
                st.markdown(f"• `{c}` — {df[c].notna().sum()} data points")

        st.markdown("---")
        st.markdown("**Describe a chart in plain English:**")
        st.caption("Examples:")

        examples = [
            "Bar graph of CPU and memory usage per month for the last 6 months",
            "Line chart of CPU usage over time",
        ]
        for ex in examples:
            st.markdown(f"- *{ex}*")

        initial = st.session_state.get("initial_prompt", "")
        chart_prompt = st.text_input(
            "Chart description:",
            value=initial if initial and not st.session_state.chart_specs else "",
            placeholder="Describe your chart...",
            key="chart_input",
        )
        if "initial_prompt" in st.session_state:
            st.session_state.initial_prompt = ""

        if st.button("Build Chart →", use_container_width=True) and chart_prompt:
            with st.spinner("AI is building your chart..."):
                try:
                    spec = llm.parse_user_request(chart_prompt, cols, entities)
                    png_path = chart.build_chart(df, spec)
                    st.session_state.chart_paths.append(png_path)
                    st.session_state.chart_specs.append(spec)
                    img = PILImage.open(png_path)
                    st.session_state.chart_images.append(img)
                    st.rerun()
                except Exception as e:
                    st.error(f"Chart skipped: {e}")

        if st.session_state.chart_specs:
            st.markdown("---")
            st.markdown(f'<div class="success-box">✓ {len(st.session_state.chart_specs)} chart(s) built</div>', unsafe_allow_html=True)

            if st.button("Generate PDF Report →", use_container_width=True):
                st.session_state.step = "report"
                st.rerun()

    with col_right:
        st.markdown('<div class="section-header">Chart Preview</div>', unsafe_allow_html=True)
        if st.session_state.chart_images:
            for i, (img, spec) in enumerate(zip(st.session_state.chart_images, st.session_state.chart_specs), 1):
                st.markdown(f"**Chart {i} — {spec.get('title', '')}**")
                st.image(img, use_container_width=True)
                st.markdown("---")
        else:
            st.markdown("""
            <div style='color:#9ca3af; text-align:center; padding:3rem 0;'>
                Charts will appear here as you build them
            </div>
            """, unsafe_allow_html=True)


# ── Step 4: Generate report ───────────────────────────────────────────────────
elif st.session_state.step == "report":
    st.markdown('<div class="section-header">Generate PDF Report</div>', unsafe_allow_html=True)

    df = st.session_state.df

    if not st.session_state.summary:
        with st.spinner("AI is writing the executive summary..."):
            st.session_state.summary = llm.generate_summary(df, st.session_state.chart_specs)

    st.markdown("**Executive Summary Preview:**")
    st.info(st.session_state.summary)

    st.markdown("---")
    title = st.text_input("Report title:", value="Infrastructure Performance Report")

    col_back, col_gen = st.columns([1, 3])
    with col_back:
        if st.button("← Add More Charts"):
            st.session_state.step = "chart"
            st.rerun()
    with col_gen:
        if st.button("Generate & Download PDF", use_container_width=True) and title:
            with st.spinner("Building PDF report..."):
                corrected = llm.correct_title(title)
                pdf_path = report.generate_pdf(
                    st.session_state.chart_paths,
                    st.session_state.chart_specs,
                    st.session_state.summary,
                    corrected,
                )
                st.session_state.pdf_path = pdf_path
                st.session_state.step = "done"
                st.rerun()


# ── Step 5: Done ──────────────────────────────────────────────────────────────
elif st.session_state.step == "done":
    st.markdown('<div class="success-box" style="font-size:1.1rem;">✓ Report generated successfully</div>', unsafe_allow_html=True)
    st.markdown("")

    pdf_path = st.session_state.pdf_path
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    filename = os.path.basename(pdf_path)
    st.download_button(
        label="⬇ Download PDF Report",
        data=pdf_bytes,
        file_name=filename,
        mime="application/pdf",
        use_container_width=True,
    )

    st.markdown("---")
    st.markdown("**Charts in this report:**")
    for i, spec in enumerate(st.session_state.chart_specs, 1):
        st.markdown(f"{i}. {spec.get('title', '')}")

    st.markdown("---")
    st.markdown("**Executive Summary:**")
    st.info(st.session_state.summary)

    st.markdown("---")
    if st.button("Start New Report", use_container_width=True):
        for key in ["df", "chart_paths", "chart_specs", "chart_images", "data_loaded",
                    "source", "clusters", "summary", "pdf_path", "initial_prompt",
                    "stat_keys", "last_days", "selected_clusters"]:
            if key in st.session_state:
                del st.session_state[key]
        st.session_state.step = "source"
        st.rerun()
