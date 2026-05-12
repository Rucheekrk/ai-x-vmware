# ai-x-vmware — Claude Code Project Instructions

## Project Overview

**Goal**: Build an AI-powered reporting system that accepts natural language prompts, extracts CSV data from VMware vRealize Orchestrator (vRO) 8.x APIs, dynamically builds custom charts and visualizations, and generates professional PDF reports for executive/management consumption.

**Core User Interaction**:
- User provides a natural language prompt such as: *"Get CPU utilization data from cluster-A and memory usage from cluster-B over the last 7 days, and generate a weekly performance report with trend charts."*
- The system interprets intent, fetches relevant CSVs from vRO, processes the data, builds appropriate visualizations, and outputs a polished PDF report.

---

## Architecture

```
User Prompt (natural language)
        ↓
Intent Parser (Claude API — claude-sonnet-4-20250514)
  ├── Which datasets/views to fetch?
  ├── What is the report goal / audience context?
  └── Are chart type + metrics specified, or should AI infer them?
        ↓
vRO API Layer
  └── Authenticate → fetch CSV data (direct response or file attachment)
        ↓
Data Processing Layer (Pandas)
  └── Schema-agnostic: infer columns dynamically at runtime
        ↓
Chart Decision Engine (Claude API)
  ├── Path A — User specified chart type + metrics → build exactly that
  └── Path B — User did not specify → LLM analyzes data schema + report goal
                    → Suggests chart type, metrics, rationale
                    → User approves (CLI confirmation or API callback)
                    → Build chart
        ↓
Visualization Layer (Plotly)
  └── Export charts as static PNG images for PDF embedding
        ↓
Report Generator (WeasyPrint: HTML/CSS → PDF)
  └── Embed charts, narrative summaries, data tables
        ↓
PDF Report Output
```

---

## Tech Stack

| Layer | Library/Tool | Version |
|---|---|---|
| Backend framework | FastAPI | latest |
| LLM | Anthropic Python SDK | latest |
| vRO API client | httpx | latest (async) |
| Data processing | Pandas | latest |
| Visualization | Plotly | latest |
| PDF generation | WeasyPrint | latest |
| HTML templating | Jinja2 | latest |
| Config management | python-dotenv | latest |
| Data validation | Pydantic v2 | latest |
| Testing | pytest + pytest-asyncio | latest |

---

## Project Structure

```
ai-x-vmware/
├── CLAUDE.md                    # This file — always read first
├── .env                         # Secrets — never commit
├── .env.example                 # Template for .env
├── .gitignore
├── requirements.txt
├── README.md
│
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app entry point
│   ├── config.py                # Settings via pydantic-settings
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── report.py        # POST /report/generate
│   │       └── health.py        # GET /health
│   │
│   ├── vro/
│   │   ├── __init__.py
│   │   ├── client.py            # vRO API client (httpx, async)
│   │   ├── auth.py              # Auth handler (bearer / basic / oauth2)
│   │   └── models.py            # Pydantic models for vRO responses
│   │
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── client.py            # Anthropic API wrapper
│   │   ├── intent_parser.py     # Prompt → structured intent extraction
│   │   └── chart_advisor.py     # Data schema → chart type + metric suggestion
│   │
│   ├── data/
│   │   ├── __init__.py
│   │   └── processor.py         # Schema-agnostic CSV processing (Pandas)
│   │
│   ├── visualization/
│   │   ├── __init__.py
│   │   └── chart_builder.py     # Plotly chart generation → PNG export
│   │
│   ├── report/
│   │   ├── __init__.py
│   │   ├── generator.py         # Orchestrates full report pipeline
│   │   ├── renderer.py          # Jinja2 → HTML → WeasyPrint → PDF
│   │   └── templates/
│   │       ├── base_report.html # Master report layout
│   │       └── components/
│   │           ├── chart_section.html
│   │           ├── summary_section.html
│   │           └── data_table.html
│   │
│   └── models/
│       ├── __init__.py
│       ├── intent.py            # ParsedIntent, ChartSpec pydantic models
│       └── report.py            # ReportRequest, ReportOutput models
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_intent_parser.py
│   ├── test_chart_advisor.py
│   ├── test_data_processor.py
│   └── test_vro_client.py
│
└── outputs/                     # Generated PDFs (gitignored)
```

---

## Environment Variables

`.env` file (never commit):
```
# Anthropic
ANTHROPIC_API_KEY=your_key_here

# vRO Connection
VRO_BASE_URL=https://<your-vro-host>/vco/api     # vRO 8.x base URL
VRO_AUTH_TYPE=bearer                              # Options: bearer | basic | oauth2
VRO_BEARER_TOKEN=                                 # If auth_type=bearer
VRO_USERNAME=                                     # If auth_type=basic
VRO_PASSWORD=                                     # If auth_type=basic
VRO_CLIENT_ID=                                    # If auth_type=oauth2
VRO_CLIENT_SECRET=                                # If auth_type=oauth2
VRO_TOKEN_URL=                                    # If auth_type=oauth2

# App
APP_ENV=development
LOG_LEVEL=INFO
OUTPUT_DIR=outputs
```

`.env.example` should be committed with empty values and comments for every variable above.

---

## Module Responsibilities

### `app/config.py`
- Use `pydantic-settings` `BaseSettings` to load all env vars.
- Expose a single `settings` singleton imported everywhere.
- Validate that required vars are present at startup.

### `app/vro/auth.py`
- Implement `VROAuthHandler` class.
- Support three auth strategies via `VRO_AUTH_TYPE`:
  - `bearer`: Attach `Authorization: Bearer <token>` header directly.
  - `basic`: POST credentials to vRO token endpoint, cache the returned token.
  - `oauth2`: POST client credentials to `VRO_TOKEN_URL`, cache with expiry.
- Expose `async def get_headers() -> dict` used by the client.
- Token caching: store token + expiry in memory, auto-refresh 60s before expiry.

### `app/vro/client.py`
- `VROClient` using `httpx.AsyncClient`.
- Key methods:
  - `async def list_datasets() -> list[str]` — discover available data sources.
  - `async def fetch_csv(dataset_id: str, params: dict) -> pd.DataFrame` — fetch and parse CSV. Handle both inline response body and file attachment (check `Content-Disposition` header to detect attachment).
  - `async def list_workflows() -> list[dict]` — list available vRO workflows if needed.
- All requests go through `VROAuthHandler.get_headers()`.
- Raise typed exceptions (`VROAuthError`, `VRONotFoundError`, `VROAPIError`) for clean error handling upstream.

### `app/llm/intent_parser.py`
- `async def parse_intent(user_prompt: str) -> ParsedIntent`
- Calls Claude API with a structured system prompt that extracts:
  - `datasets_requested: list[str]` — names/IDs of datasets or views mentioned.
  - `report_goal: str` — what management needs to understand from this report.
  - `time_range: dict | None` — e.g. `{"last_days": 7}` or `{"start": "...", "end": "..."}`.
  - `chart_specs: list[ChartSpec] | None` — only populated if the user explicitly specified chart type and metrics. Empty list if user left it to the AI.
  - `additional_context: str | None` — any extra instructions the user gave.
- Return a `ParsedIntent` Pydantic model.
- System prompt must instruct Claude to return **only valid JSON**, no markdown fences, no preamble.

### `app/llm/chart_advisor.py`
- `async def suggest_charts(df_schemas: list[dict], report_goal: str) -> list[ChartSpec]`
- Called only when `parsed_intent.chart_specs` is empty (Path B).
- Each `df_schema` is `{"dataset_name": str, "columns": list[str], "sample_rows": int, "dtypes": dict}`.
- Claude analyzes schemas + report goal and returns a list of `ChartSpec`:
  - `dataset_name: str`
  - `chart_type: str` — one of: `line`, `bar`, `grouped_bar`, `scatter`, `heatmap`, `area`, `pie`, `table`.
  - `x_column: str`
  - `y_columns: list[str]`
  - `title: str`
  - `rationale: str` — why this chart type suits the data and the goal.
- System prompt: return only valid JSON list of chart specs.

### `app/data/processor.py`
- `class DataProcessor`
- `def load_dataframe(raw: str | bytes, source_hint: str = "") -> pd.DataFrame`
  - Handles CSV as string or bytes.
  - Infers delimiter (comma vs tab vs semicolon).
  - Parses datetime columns automatically.
  - Strips whitespace from column names.
  - Returns clean DataFrame.
- `def get_schema(df: pd.DataFrame, dataset_name: str) -> dict`
  - Returns `{"dataset_name", "columns", "dtypes", "sample_rows", "shape"}` for the chart advisor.
- `def merge_datasets(dfs: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]`
  - Returns the dict as-is for now; future: allow join hints from intent.
- **Schema-agnostic**: never hardcode column names. All column operations must use dynamic inference.

### `app/visualization/chart_builder.py`
- `class ChartBuilder`
- `def build_chart(df: pd.DataFrame, spec: ChartSpec) -> str` — returns absolute path to saved PNG.
- Use Plotly `go` (graph objects) not `px` (express) — more control for professional output.
- Chart style requirements:
  - Clean white background.
  - Anthropic-neutral color palette: `["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]` or similar professional set.
  - Font: Arial or sans-serif, 12px axis labels, 14px title.
  - Grid lines: light gray (`#e0e0e0`), 0.5px.
  - Legend: inside chart, top-right.
  - Export via `fig.write_image(path, format="png", width=900, height=500, scale=2)`.
- Handle each `chart_type` in `ChartSpec` explicitly. Raise `UnsupportedChartTypeError` for unknown types.
- Save PNGs to `outputs/charts/` with a UUID filename.

### `app/report/generator.py`
- `async def generate_report(request: ReportRequest) -> ReportOutput`
- Orchestrates the full pipeline:
  1. Parse intent → `ParsedIntent`
  2. Fetch CSVs from vRO for each requested dataset → list of DataFrames
  3. Process DataFrames → clean + extract schemas
  4. Determine chart path (A or B):
     - Path A: use `parsed_intent.chart_specs` directly.
     - Path B: call `chart_advisor.suggest_charts()` → present suggestions to caller (return them in `ReportOutput.pending_approval` state).
  5. Build charts → list of PNG paths.
  6. Generate narrative summary via Claude (executive-friendly plain English).
  7. Render PDF via `renderer.py`.
  8. Return `ReportOutput` with PDF path and metadata.
- For Path B approval flow: `ReportOutput` should include a `status` field: `"pending_approval"` or `"complete"`. The API caller handles the approval loop.

### `app/report/renderer.py`
- `def render_pdf(context: dict) -> str` — returns absolute path to output PDF.
- Context dict includes: `report_title`, `generated_at`, `executive_summary`, `sections` (list of chart+description pairs), `data_tables` (optional).
- Render `base_report.html` with Jinja2 → pass HTML string to WeasyPrint → save PDF to `outputs/`.
- PDF design requirements:
  - Clean, professional layout. White background. No decorative gradients.
  - Header: report title + generated timestamp + company/environment name.
  - Each section: chart image (full width), followed by 2-3 sentence plain English description.
  - Footer: page numbers.
  - Font: system sans-serif (Arial fallback).

### `app/api/routes/report.py`
- `POST /report/generate` — accepts `ReportRequest`, returns `ReportOutput` JSON.
- `POST /report/approve` — accepts `approval_id + approved_specs`, continues pipeline from Path B.
- `GET /report/download/{report_id}` — streams the PDF file.

---

## Two-Path Chart Flow (Critical Logic)

```
ParsedIntent.chart_specs populated?
        │
       YES ─────────────────────────────────────────────────────────►  Path A
        │                                                               Build charts exactly as specified.
        │                                                               No LLM involvement in chart decision.
       NO
        │
        ▼
Path B: chart_advisor.suggest_charts(schemas, report_goal)
        │
        ▼
Return ChartSuggestions to caller with status="pending_approval"
        │
  Caller reviews suggestions (CLI print / API response)
        │
        ▼
POST /report/approve with approved chart specs
        │
        ▼
Build charts → generate narrative → render PDF
```

**Important**: Never skip the approval step in Path B. The LLM suggestion is a proposal, not a decision. The human confirms before charts are built.

---

## vRO API Integration Notes

### Known vRO 8.x Endpoints (verify against your lab instance)
- `GET /vco/api/workflows` — list available workflows.
- `POST /vco/api/workflows/{id}/executions` — execute a workflow.
- `GET /vco/api/workflows/{id}/executions/{execId}/state` — poll execution state.
- `GET /vco/api/workflows/{id}/executions/{execId}/logs` — fetch logs/output.
- Data export endpoints may vary — discover via `GET /vco/api/resources` or workflow output inspection.

### CSV Delivery — Two Modes (determine on first API access)
1. **Inline response body**: `Content-Type: text/csv` — read `response.text` directly.
2. **File attachment**: `Content-Disposition: attachment; filename="..."` — read `response.content` as bytes.

The `VROClient.fetch_csv()` method must handle both transparently by inspecting the `Content-Type` and `Content-Disposition` headers.

### SSL/TLS
- Lab environments often use self-signed certs. Add `verify=False` to `httpx.AsyncClient` in development (`APP_ENV=development`). Always `verify=True` in production.
- Log a warning when SSL verification is disabled.

---

## LLM Prompt Engineering Guidelines

### Intent Parser System Prompt Pattern
```
You are an AI assistant that extracts structured information from VMware operations report requests.

Given a natural language prompt, extract:
- datasets_requested: list of dataset or view names mentioned
- report_goal: what management needs to understand (one sentence)
- time_range: time period if mentioned, else null
- chart_specs: list of explicit chart specifications if the user specified chart type AND metrics, else empty list
- additional_context: any other user instructions

Respond ONLY with a valid JSON object. No markdown. No explanation. No preamble.

JSON schema:
{
  "datasets_requested": ["string"],
  "report_goal": "string",
  "time_range": {"type": "last_days", "value": 7} | {"type": "range", "start": "ISO date", "end": "ISO date"} | null,
  "chart_specs": [{"dataset_name": "string", "chart_type": "string", "x_column": "string", "y_columns": ["string"], "title": "string"}],
  "additional_context": "string | null"
}
```

### Chart Advisor System Prompt Pattern
```
You are a data visualization expert for VMware infrastructure reports targeting executive audiences.

Given dataset schemas and a report goal, suggest the most effective chart type and metric combination for each dataset.

Rules:
- Choose chart types that non-technical executives can immediately understand.
- Prefer: line charts for time series, bar charts for comparisons, heatmaps for utilization matrices.
- Avoid: scatter plots unless correlation is the explicit goal.
- Select only columns that exist in the provided schema.
- Write concise rationale (1 sentence) explaining why this chart suits the data and goal.

Respond ONLY with a valid JSON array. No markdown. No preamble.
```

### Narrative Summary Prompt Pattern
```
You are a technical writer creating executive summaries for VMware infrastructure reports.

Given chart descriptions and processed data statistics, write a concise executive summary (3-5 sentences) that:
- States what was analyzed and over what time period.
- Highlights the most important finding or trend.
- Flags any anomalies or concerns if present.
- Uses plain English — no jargon, no acronyms without explanation.
- Does NOT add any information not present in the provided data.

Output plain text only. No markdown. No bullet points.
```

---

## Data Processing Rules

- **Never hardcode column names** anywhere in the codebase.
- All column selection is driven by `ChartSpec.x_column` and `ChartSpec.y_columns` at runtime.
- Datetime parsing: attempt `pd.to_datetime()` on any column whose name contains: `time`, `date`, `timestamp`, `created`, `updated` (case-insensitive).
- Numeric coercion: use `pd.to_numeric(errors='coerce')` on y-axis columns. Drop NaN rows after coercion and log a warning with count.
- Do not drop or summarize data beyond what is needed for charting. Preserve raw data fidelity.
- Report narrative must reflect what is in the data — the LLM must not invent metrics or trends.

---

## Error Handling

Every layer must raise typed exceptions. Never let raw exceptions bubble to the API response.

| Exception | Where raised | HTTP status |
|---|---|---|
| `VROAuthError` | vro/auth.py | 401 |
| `VRONotFoundError` | vro/client.py | 404 |
| `VROAPIError` | vro/client.py | 502 |
| `IntentParseError` | llm/intent_parser.py | 422 |
| `ChartAdvisorError` | llm/chart_advisor.py | 500 |
| `UnsupportedChartTypeError` | visualization/chart_builder.py | 422 |
| `DataProcessingError` | data/processor.py | 422 |
| `ReportRenderError` | report/renderer.py | 500 |

FastAPI exception handlers in `main.py` catch each type and return structured JSON error responses.

---

## Testing Strategy

- Mock vRO API responses using `httpx.MockTransport` or `respx`.
- Mock Anthropic API using `unittest.mock.patch`.
- Use sample CSV strings (generated in `conftest.py`) for data processing tests — do not use real vRO data in tests.
- Test both Path A and Path B chart decision flows explicitly.
- Test each auth strategy (`bearer`, `basic`, `oauth2`) in `test_vro_client.py`.
- All async tests use `pytest-asyncio`.

---

## Development Setup (macOS)

```bash
# Python 3.11+ required
python3 --version

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# WeasyPrint system dependencies (macOS)
brew install pango libffi gdk-pixbuf

# Plotly static image export dependency
pip install kaleido

# Copy and fill env
cp .env.example .env
# Edit .env with your actual keys

# Run development server
uvicorn app.main:app --reload --port 8000

# Run tests
pytest tests/ -v
```

---

## Current Constraints & Decisions

- **Frontend**: None for now. FastAPI serves JSON + PDF download endpoints only.
- **Auth type**: Unknown until lab access. Auth module supports all three — configure via `VRO_AUTH_TYPE` env var.
- **CSV schema**: Fully dynamic. No hardcoded column names anywhere.
- **Chart approval (Path B)**: Handled via API round-trip (`/report/generate` → `/report/approve`). No interactive UI.
- **LLM model**: `claude-sonnet-4-20250514` for all LLM calls.
- **PDF only**: No interactive HTML dashboard for now. Plotly charts are exported as static PNGs and embedded in PDF.
- **SSL**: `verify=False` in dev, `verify=True` in prod — controlled by `APP_ENV` env var.
- **Report fidelity**: The LLM must never remove or omit details from fetched data. Summarization is additive (adds narrative context), never reductive.

---

## What To Build First (Recommended Order)

1. Project scaffolding — directory structure, `requirements.txt`, `config.py`, `.env.example`.
2. `app/models/` — Pydantic models for `ParsedIntent`, `ChartSpec`, `ReportRequest`, `ReportOutput`.
3. `app/vro/auth.py` + `app/vro/client.py` — with mock mode when `VRO_BASE_URL` is not set.
4. `app/llm/intent_parser.py` — test with sample prompts.
5. `app/data/processor.py` — schema-agnostic CSV processing.
6. `app/llm/chart_advisor.py` — test with sample schemas.
7. `app/visualization/chart_builder.py` — test with sample DataFrames.
8. `app/report/renderer.py` + HTML templates — test PDF output.
9. `app/report/generator.py` — wire all layers together.
10. `app/api/routes/` — expose FastAPI endpoints.
11. `tests/` — add tests alongside each module.
