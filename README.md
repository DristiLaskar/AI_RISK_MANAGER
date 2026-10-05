# AI Risk Manager

Upload your payments, see which clients are about to go quiet, how much money rides on them, and what the next quarter looks like. You can also ask questions about your own numbers.

## Run it

```bash
pip install -r requirements.txt
uvicorn main:app --reload        # open http://127.0.0.1:8000
```

The React app is pre-built into `frontend/dist/app.js`, so there is nothing else to install. To edit the UI:

```bash
cd frontend && npm install && npm run build
```

### Optional: a free key for the Ask panel

Ask works with no key (it shows the matching facts). A free key makes it write a short, cited answer instead. Set one of these before starting the server:

| Provider | Get a key | Set |
|---|---|---|
| Groq (fast) | console.groq.com/keys | `GROQ_API_KEY` (uses `llama-3.3-70b-versatile`) |
| Gemini | aistudio.google.com/apikey | `GEMINI_API_KEY` (uses `gemini-2.5-flash`) |
| Anything OpenAI-compatible (OpenRouter, Cerebras, Mistral...) | their site | `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` |

```bash
export GROQ_API_KEY=your_key        # Windows PowerShell: $env:GROQ_API_KEY="your_key"
uvicorn main:app --reload
```

`LLM_MODEL` overrides the default model for any provider. If a provider is down or rate-limited, Ask falls back to showing the matching facts. Only your question and the retrieved facts are sent, never the raw files. Note that Gemini's free tier may use prompts to improve Google products, so prefer Groq if your client data is sensitive.

## How the pipeline works

```
upload / paste ─► clean ─► monthly totals ─► churn model ─► risk, value, stage ─► forecast ─► API ─► React
 (analysis.py)  (data_pipelining.py)        (churn.py)      (models.py)        (forecast.py)
```

| File | Job |
|---|---|
| `core/data_pipelining.py` | Cleaning: dates and amounts, income vs expense (labels or sign), de-duplication, missing clients kept as revenue |
| `core/churn.py` | Forward-looking churn model: *does this client pay nothing in the next 90 days?* |
| `core/models.py` | Lifecycle stage, hybrid risk, 12-month value, pricing hint, burnout |
| `core/forecast.py` | 3-month trend + seasonality forecast with a range and a backtest error |
| `core/rag.py` | Ask panel: TF-IDF retrieval over facts about your analysis, optional free-LLM answer |
| `core/analysis.py` | Orchestration and the JSON the UI reads |
| `train_model.py` | `python train_model.py [tx.csv] [invoices.csv]` prints a backtest for any dataset |

## What was wrong with the old ML pipeline, and the fix

| Problem | Fix |
|---|---|
| The label was a hand-written rule on recency, revenue drop and payment count, so the model only learned to imitate that rule. Cross-validated AUC was **0.41**, worse than a coin flip | The label is now real future behaviour: no payment in the 90 days after a cutoff date |
| Features and label were computed from the same snapshot (leakage and train/serve skew) | One function builds features strictly from data before each cutoff, used for both training and scoring |
| Random cross-validation folds on 100 rows | Rolling biweekly snapshots (about 11,500 rows on the sample data), tested on a later period with a purge gap. Reported next to a plain "overdue" rule so you can see whether the model earns its keep |
| A pickled model was trained once on the sample data and applied to any upload | The model is fitted on each upload's own history. If there is too little history, the app says so and falls back to rules |
| Sample data never contained real churn (a client skipped one month at random) | `data_generation.py` now makes clients leave for good, and is seeded so it is reproducible |
| Quiet clients were scored with their stale averages and healthy-looking features | Recency and overdue ratio are first-class features |
| CLV was a heuristic multiplier | Value is the expected 12 months of revenue, discounted by each client's churn probability |
| Forecast used Prophet (heavy, fails on short history), a partial last month skewed it, and the "confidence" was `80 + len % 10` | Light trend + seasonality model, partial months dropped, range from residuals, error from a rolling backtest |
| Missing client rows were dropped, so revenue was understated | Kept as revenue under `UNASSIGNED` and reported in the data-quality note |
| Dashboard re-ran the whole analysis on every request | Cached until the uploaded files change |

Sample data result: AUC **0.76** vs **0.55** for the overdue rule, on a period the model never saw.

## Limits worth knowing

- A client counts as churned after 90 days of silence. Change `HORIZON` in `churn.py` for other businesses.
- It needs roughly 8+ months of history and some lapsed clients to learn anything. Below that it uses rules and says so.
- The forecast is a trend model, so it will not anticipate one-off events.
