# VMware Aria Operations — AI-Powered Reporting

An AI-powered CLI tool that generates professional PDF performance reports from VMware Aria Operations data. Uses natural language prompts to select metrics, build charts, and write executive summaries automatically.

---

## What It Does

- **Option 1 — Local CSV**: Load CSV files from the built-in `data/` folder → describe charts in plain English → generate PDF report. Simply drop any CSV file into the `data/` folder and it will be available to select when you run the tool.
- **Option 2 — Live Aria Operations**: Connect to Aria Operations API → select clusters → describe what you want → fetch live metrics → generate PDF report

Charts are built using Plotly and the PDF is rendered with ReportLab. An LLM (via GitHub Models) handles natural language parsing, metric matching, and executive summary writing.

---

## How to Open a Terminal

All setup and run commands are typed into a terminal (also called a command prompt). Here is how to open one:

**macOS:**
1. Press `Cmd + Space` to open Spotlight
2. Type `Terminal` and press `Enter`

**Windows:**
1. Press the `Windows` key
2. Type `PowerShell` or `cmd` and press `Enter`

---

## Prerequisites

- **Python 3.14.3 or later**

  ⚠️ Only follow the steps below if you do not have Python installed on your machine.
  To check, open terminal and run:
  ```bash
  python3 --version
  ```

  **macOS (via Homebrew):**
  ```bash
  # Only install Homebrew if you don't have it AND want to install Python via Homebrew:
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

  # Then install Python:
  brew install python@3.14
  ```

  **Direct download (macOS and Windows):**
  https://www.python.org/downloads/release/python-3143/

- A GitHub account (for the free GitHub Models API — no paid subscription needed)
- Access to VMware Aria Operations (only required for Option 2 / live data)

---

## Setup

### 1. Clone or unzip the project

```bash
cd ai-x-vmware
```

### 2. Create a virtual environment and install dependencies

A virtual environment is an isolated workspace for this project's Python dependencies — it keeps them separate from other Python programs on your machine. Think of it as a clean folder just for this project.

```bash
python3 -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows

pip install -r requirements.txt
```

> **Windows note:** If `python3` is not recognised, try `python` instead:
> ```bash
> python -m venv .venv
> ```

**What gets installed:**

| Package | What it does |
|---|---|
| `openai` | SDK to communicate with the GitHub Models API (GPT-4o-mini) |
| `pandas` | Loads and processes CSV data and time-series metrics |
| `plotly` | Builds the charts (bar, line, area) |
| `kaleido` | Exports Plotly charts as PNG images for embedding in the PDF |
| `reportlab` | Generates the professional PDF report |
| `httpx` | Makes HTTP requests to the VMware Aria Operations API |
| `python-dotenv` | Loads your `.env` file (credentials and config) |
| `pillow` | Reads image dimensions when embedding charts into the PDF |
| `questionary` | Powers the interactive checkbox for CSV file selection |

### 3. Configure environment variables

```bash
cp .env.example .env
```

The `.env` file is a private configuration file that stores your credentials and settings. It lives only on your machine and is never shared or uploaded anywhere. The `.env.example` file is a blank template — you copy it to `.env` and fill in your own values.

Edit `.env` and fill in your values:

```
# GitHub Models (required — get your token at github.com → Settings → Developer settings → Personal access tokens)
GITHUB_TOKEN=your_github_token_here

# VMware Aria Operations (only required for Option 2 — live data)
ARIA_BASE_URL=https://<your-aria-host>/suite-api/api
ARIA_USERNAME=your_username
ARIA_PASSWORD=your_password

# App
APP_ENV=development
```

**How to get a GitHub token:**
1. Go to [github.com](https://github.com) → Sign in
2. Profile picture → **Settings** → **Developer settings** → **Personal access tokens** → **Tokens (classic)**
3. Click **Generate new token (classic)**
4. Give it a name, set an expiry — **no scopes needed**, leave all boxes unchecked
5. Copy the token and paste it as `GITHUB_TOKEN` in your `.env`

### 4. (Optional) Add local CSV files for Option 1

Place any exported CSV files in the `data/` folder. The tool will detect and list them automatically.

---

## Running the Tool

```bash
source .venv/bin/activate
python main.py
```

You will be prompted to choose a data source:

```
  1. Load local CSV file(s)  (offline / demo)
  2. Fetch live data from Aria Operations  ⚠  READ-ONLY
```

### Option 1 — Local CSV

> **Before running:** place your CSV file(s) in the `data/` folder at the root of the project. The tool automatically detects all CSV files in that folder and lists them for selection.

1. Select one or more CSV files from the `data/` folder
2. Describe the chart(s) you want in plain English, for example:
   - `"Bar graph of CPU and memory usage per month for the last 6 months"`
   - `"Line chart of CPU usage over time"`
3. Confirm the chart spec, add more charts if needed, then type `done`
4. Enter a report title — the PDF opens automatically

### Option 2 — Live Aria Operations

1. Approve the connection when prompted (read-only, no changes made)
2. Select which clusters to include
3. Describe the data and chart you want, for example:
   - `"Bar chart of CPU and memory workload per month for the last 6 months"`
   - `"Line chart of disk read and write latency for the last 2 weeks"`
4. Confirm the metrics to fetch, then confirm the chart spec
5. Add more charts if needed, then type `done`
6. Enter a report title — the PDF opens automatically

---

## Output

PDF reports are saved to the `outputs/` folder with versioned filenames:

```
outputs/
  Performance_Report_v1.pdf
  Performance_Report_v2.pdf   ← auto-incremented if title is reused
```

Each report includes:
- **Cover page** with title, date, and report description
- **Executive Summary** with AI-generated narrative and chart index
- **One chart per page** with title, chart, and caption

**To find and open your PDF:**

- **macOS:** Open Finder → navigate to the `ai-x-vmware` folder → open the `outputs` folder. The PDF will open automatically after generation, or you can double-click it to open in Preview.
- **Windows:** Open File Explorer → navigate to the `ai-x-vmware` folder → open the `outputs` folder. The PDF will open automatically after generation, or you can double-click it to open in your default PDF viewer.

---

## Project Structure

```
ai-x-vmware/
├── main.py          # CLI entry point and user interaction flow
├── aria_client.py   # VMware Aria Operations API client (read-only)
├── llm.py           # GitHub Models (GPT-4o-mini) — NL parsing, metric matching, summary
├── chart.py         # Plotly chart builder → PNG export
├── report.py        # ReportLab PDF generator
├── requirements.txt
├── .env.example     # Template — copy to .env and fill in your values
└── data/            # Place local CSV files here for Option 1
```

---

## Changing the AI Model

The model is set in a single line in `llm.py`:

```python
MODEL = "claude-3-5-sonnet"
```

To switch to a different model, replace that value with any model name supported by GitHub Models. Some options:

| Model | Description |
|---|---|
| `gpt-4o-mini` | ✅ Default — lightweight, fast, and great for JSON parsing and summaries |
| `gpt-4o` | More powerful — better for complex or nuanced requests |
| `Meta-Llama-3.1-405B-Instruct` | Meta's largest open model — strong general-purpose |
| `Meta-Llama-3.1-8B-Instruct` | Meta's smaller open model — faster and lighter |

> **No other code changes needed.** The GitHub token and API endpoint stay the same regardless of which model you pick — GitHub Models routes all of them through the same endpoint.

To browse all available models, visit: [github.com/marketplace/models](https://github.com/marketplace/models)

---

## Troubleshooting

**`GITHUB_TOKEN` error / authentication failed**
- Make sure you have copied `.env.example` to `.env` and filled in your GitHub token
- Check that the token is pasted correctly with no extra spaces
- Tokens expire — if yours has expired, generate a new one at github.com → Settings → Developer settings → Personal access tokens

**`python3: command not found` (Windows)**
- Try using `python` instead of `python3` in all commands

**`pip: command not found`**
- Make sure you have activated the virtual environment first:
  - macOS / Linux: `source .venv/bin/activate`
  - Windows: `.venv\Scripts\activate`
- You should see `(.venv)` at the start of your terminal line when it is active

**`ModuleNotFoundError` when running `python main.py`**
- The virtual environment is not active — run the activate command above first, then retry

**PDF does not open automatically**
- Navigate to the `outputs/` folder inside the project directory and double-click the PDF to open it manually

**Charts missing from the PDF / "Chart skipped" warning**
- This can happen if the described metric does not match available data — try rephrasing your chart description to match the available columns more closely

---

## Notes

- All Aria Operations access is **read-only** — the tool never modifies your environment
- SSL verification is disabled in `APP_ENV=development` (self-signed certs). Set `APP_ENV=production` for verified SSL
- The LLM is used only for: metric matching, chart spec parsing, title correction, and executive summary generation — it never sees your raw infrastructure data
