"""
GitHub Models (gpt-4o-mini via models.inference.ai.azure.com) helpers.
- parse_user_request  : natural language → chart spec (columns from DataFrame)
- match_metrics       : natural language → Aria Operations metric keys
- generate_summary    : plain-English executive summary
"""

import os
import json
import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv
from aria_client import METRIC_CATALOGUE, ALL_METRICS

load_dotenv()

client = OpenAI(
    base_url="https://models.inference.ai.azure.com",
    api_key=os.getenv("GITHUB_TOKEN"),
)
MODEL = "claude-3-5-sonnet"

def match_metrics(user_prompt: str, last_days: int = 30) -> tuple[list[str], int]:
    """
    Map a natural language request to real Aria Operations metric keys
    available on VH-Flexpod. Returns (list_of_stat_keys, last_days).
    """
    catalogue_text = ""
    for category, metrics in METRIC_CATALOGUE.items():
        catalogue_text += f"\n{category}:\n"
        for key, label in metrics.items():
            catalogue_text += f"  {key}  →  {label}\n"

    system = (
        "You are a VMware Aria Operations metric mapping assistant.\n"
        "The user will describe what data they want. Clusters have already been selected by the user.\n"
        "Return ONLY a valid JSON object — no markdown, no explanation.\n\n"
        "JSON schema:\n"
        "{\n"
        '  "stat_keys": ["exact metric key strings from the catalogue"],\n'
        '  "last_days": <integer number of days of history to fetch>\n'
        "}\n\n"
        "Rules:\n"
        "- Only use metric keys that exist in the catalogue below.\n"
        "- Pick 1-5 most relevant metrics for what the user asked.\n"
        "- Default last_days to 30 if the user does not specify a time range.\n"
        "- If user says 'last 7 days' set last_days=7, '3 months' set last_days=90, etc.\n\n"
        f"Available metric catalogue:{catalogue_text}"
    )

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0,
    )
    result = json.loads(response.choices[0].message.content)
    return result["stat_keys"], result.get("last_days", last_days)


def correct_title(title: str) -> str:
    """Fix spelling and grammar in a user-supplied report title."""
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content":
             "You are a spelling and grammar corrector for report titles.\n"
             "Correct ALL spelling mistakes, typos, and grammar errors in the given title.\n"
             "Rules:\n"
             "- Always fix misspelled words (e.g. 'Performence' → 'Performance', 'Reort' → 'Report')\n"
             "- Capitalise the first letter of each major word (title case)\n"
             "- Do not change product names, acronyms, or proper nouns (e.g. VH-Flexpod, CPU)\n"
             "- Return ONLY the corrected title — no quotes, no explanation, no extra text\n"
             "- If the title has no errors, return it exactly as given"},
            {"role": "user", "content": title},
        ],
        temperature=0,
    )
    return response.choices[0].message.content.strip()


def parse_user_request(prompt: str, available_columns: list[str], entity_names: list[str]) -> dict:
    """
    Parse a natural language request into a structured chart spec.
    Returns:
      {
        "entities": ["MDC-Stretch"],
        "columns":  ["CPU|Capacity Usage (%)"],
        "chart_type": "line",
        "title": "CPU Utilization - MDC-Stretch"
      }
    """
    system = (
        "You are a data visualization assistant for VMware Aria Operations infrastructure reports.\n"
        "The user will describe what they want to see. Return ONLY a valid JSON object — "
        "no markdown, no explanation.\n\n"
        "JSON schema:\n"
        "{\n"
        '  "entities": ["list of entity names to include, empty list means all"],\n'
        '  "columns": ["list of exact column names to plot on y-axis"],\n'
        '  "chart_type": "line | bar | area",\n'
        '  "title": "descriptive chart title",\n'
        '  "last_days": <integer number of days to look back, or null if not mentioned>,\n'
        '  "resample_freq": "daily | weekly | monthly | null — only set if the user explicitly mentions a bar/point interval, otherwise null"\n'
        "}\n\n"
        f"Available entity names: {entity_names}\n"
        f"Available columns: {available_columns}\n"
        "Rules:\n"
        "- Only pick columns that exist in the available columns list.\n"
        "- Only pick entity names that exist in the available entity names list.\n"
        "- Prefer line charts for time-series data.\n"
        "- Prefer bar charts for comparisons across entities at a point in time.\n"
        "- The timestamp column is always the x-axis — do not include it in 'columns'.\n"
        "- Always correct any spelling mistakes in the title. Write it in proper English.\n"
        "- IMPORTANT: When choosing columns, always prefer raw metric columns over derived variants. "
        "  Specifically, if a column name ending in '(Trend)', '(Forecast)', '(Projected)', or similar "
        "  exists alongside a base column without that suffix, always pick the base column unless the user "
        "  explicitly asks for trend or forecast data. For example, prefer 'CPU|Capacity Usage (%)' over "
        "  'CPU|Capacity Usage (%) (Trend)'.\n"
        "- last_days examples: 'last week' → 7, 'last month' → 30, 'last 2 months' → 60, "
        "  'last 6 months' → 180, 'last quarter' → 90. If not mentioned, set to null.\n"
        "- resample_freq: set to 'daily' if user says 'daily bars' or 'one point per day', "
        "  'weekly' if user says 'weekly bars' or 'one bar per week', "
        "  'monthly' if user says 'monthly bars' or 'one bar per month'. "
        "  If the user does not explicitly mention an interval, set to null.\n"
    )

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt},
        ],
        temperature=0,
    )
    return json.loads(response.choices[0].message.content)


def generate_summary(df: pd.DataFrame, chart_specs: list[dict]) -> str:
    """Generate a plain-English executive summary of the data and charts."""
    stats = []
    for col in df.select_dtypes(include="number").columns:
        s = df[col].dropna()
        if len(s):
            stats.append(f"{col}: min={s.min():.2f}, max={s.max():.2f}, mean={s.mean():.2f}")

    charts_desc = "\n".join(
        f"- {s['title']} ({s['chart_type']} chart, columns: {', '.join(s['columns'])})"
        for s in chart_specs
    )

    system = (
        "You are a technical writer creating executive summaries for VMware infrastructure reports.\n"
        "Write a concise summary (3-5 sentences) that:\n"
        "- States what was analyzed and the data time range if visible.\n"
        "- Highlights the most important finding or trend.\n"
        "- Flags any anomalies or concerns if present.\n"
        "- Uses plain English — no jargon.\n"
        "- Does NOT add information not present in the provided statistics.\n"
        "Output plain text only. No markdown. No bullet points."
    )

    user_msg = (
        "Data statistics:\n" + "\n".join(stats) +
        f"\n\nCharts in this report:\n{charts_desc}"
    )

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user_msg},
        ],
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()
