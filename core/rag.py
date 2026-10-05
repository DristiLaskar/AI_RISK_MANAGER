"""Small RAG layer: retrieve facts about the user's own analysis, then answer from them.

Retrieval is TF-IDF (scikit-learn, no downloads). If a free LLM key is set, only the retrieved facts and the
question are sent to it to write the answer; otherwise the top facts are returned directly (still grounded).
Providers (first key found wins): GROQ_API_KEY, GEMINI_API_KEY, or any OpenAI-compatible service via
LLM_API_KEY + LLM_BASE_URL + LLM_MODEL (OpenRouter, Cerebras, Mistral, ...). LLM_MODEL overrides the default.
"""
import json
import os
import re
import urllib.request

from sklearn.feature_extraction.text import TfidfVectorizer

PLAYBOOK = [
    ("playbook:quiet-client", "Playbook for a client who has gone quiet or is overdue: reach out within a week "
     "with a short personal message, ask about upcoming budgets, offer a small scoped project or a check-in call, "
     "and only discount as a last resort."),
    ("playbook:concentration", "Playbook for concentration risk, one client is too large a share of revenue: "
     "cap new work for that client, win two or three mid-size clients, and move them to retainers so income is smoother."),
    ("playbook:pricing", "Playbook for pricing: raise rates 5 to 15 percent for stable and growing clients, "
     "hold rates for declining clients until the relationship is repaired, and use retention discounts sparingly."),
    ("playbook:cashflow", "Playbook for a falling cash flow forecast: chase unpaid invoices, shorten payment terms, "
     "ask for deposits, and delay discretionary expenses until at-risk clients are resolved."),
    ("playbook:burnout", "Playbook for high burnout risk: too many shaky clients and irregular income. Pause low-value "
     "work, prioritise retainers, and stabilise the client base before taking on new projects."),
]


def build_docs(res):
    cl, act = res["clients"], res["active"]
    fc, mod = res["fc"], res["model"]
    watch = res["watch"].head(5)
    rank = {c: i + 1 for i, c in enumerate(watch["client_id"])}
    docs = []
    for _, r in cl.iterrows():
        band = ("High churn risk: likely to leave or go quiet, worth contacting soon." if r["RISK_%"] > 60
                else "Medium risk, keep an eye on it." if r["RISK_%"] > 30 else "Low risk: safe, reliable, healthy.")
        top = f" Ranked #{rank[r['client_id']]} on the watchlist by revenue at risk." if r["client_id"] in rank else ""
        docs.append((f"client:{r['client_id']}",
                     f"Client {r['client_id']} is {r['STAGE'].lower()}. Churn risk {r['RISK_%']:.0f}%. {band}{top} "
                     f"Last paid {r['recency']:.0f} days ago, usually pays every {r['avg_gap']:.0f} days "
                     f"(overdue x{r['overdue_ratio']:.1f}). Recent run-rate ${r['run_rate']:,.0f} per month, "
                     f"expected next 12 months ${r['PREDICTIVE_CLV']:,.0f}, revenue at risk ${r['AT_RISK']:,.0f}. "
                     f"Revenue trend {r['revenue_trend'] * 100:+.0f}%. Suggested action: {r['PRICE_STRATEGY']}."))
    docs.append(("business:watchlist", "Watchlist, who to contact first, priority clients to call, ordered by revenue at risk: " +
                 "; ".join(f"{w['client_id']} ({w['RISK_%']:.0f}% risk, ${w['AT_RISK']:,.0f} at stake)" for _, w in watch.iterrows()) + "."))
    dep, q = res["dependency"], res["quality"]
    docs.append(("business:overview",
                 f"Business overview as of {res['as_of']}: risk score {res['risk_score']} ({res['risk_status']}), "
                 f"burnout {res['burnout']}%. {len(act)} active clients, {len(cl) - len(act)} lost. "
                 f"Top client is {dep['top_client']}% of recent revenue, top five are {dep['top_5_clients']}%. "
                 f"Cash flow forecast next three months ${fc['net']['yhat'][0]:,.0f}, ${fc['net']['yhat'][1]:,.0f}, "
                 f"${fc['net']['yhat'][2]:,.0f}; revenue forecast ${fc['revenue']['yhat'][0]:,.0f} next month. "
                 f"Data quality: {q['duplicates_removed']} duplicate rows removed, {q['income_without_client']} income rows had no client."))
    if mod["mode"] == "ml":
        d = ", ".join(mod["drivers"])
        docs.append(("model:drivers", f"The churn model predicts whether a client pays nothing in the next {mod['horizon_days']} days. "
                     f"Strongest drivers: {d}. Backtest AUC {mod.get('auc', 'n/a')} versus {mod.get('baseline_auc', 'n/a')} for a simple overdue rule."))
    return docs + PLAYBOOK


class RagIndex:
    def __init__(self, res):
        self.docs = build_docs(res)
        self.vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english")
        self.X = self.vec.fit_transform([t for _, t in self.docs])

    def search(self, q, k=5):
        sims = (self.X @ self.vec.transform([q]).T).toarray().ravel()
        return [self.docs[i] for i in sims.argsort()[::-1][:k] if sims[i] > 0]

    def answer(self, q):
        hits = self.search(q)
        words = set(re.findall(r"[\w&-]+", q.lower()))
        named = [d for d in self.docs if d[0].startswith("client:") and d[0][7:].lower() in words]
        if named:  # a client was named: answer about that client, not look-alikes
            hits = named[:3] + [h for h in hits if not h[0].startswith("client:")]
        else:      # no client named: a couple of client examples at most
            cl = [h for h in hits if h[0].startswith("client:")][:2]
            hits = [h for h in hits if not h[0].startswith("client:")] + cl
        ctx = [d for d in self.docs if d[0] == "business:overview"] + [h for h in hits if h[0] != "business:overview"]
        prov = _provider()
        out = {"sources": [{"id": i, "text": t} for i, t in ctx], "mode": "retrieval"}
        if prov:
            try:
                out["answer"], out["mode"] = _ask_llm(prov, q, ctx), "llm"
                return out
            except Exception as e:
                out["note"] = f"Language model unavailable ({type(e).__name__}); showing the matching facts instead."
        out["answer"] = "\n".join(f"- {t}" for _, t in (hits or ctx)[:3])
        return out


PROVIDERS = [  # env var, OpenAI-compatible base URL, default model
    ("GROQ_API_KEY", "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    ("GEMINI_API_KEY", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.5-flash"),
    ("LLM_API_KEY", "", ""),
]


def _provider():
    for env, url, model in PROVIDERS:
        if os.getenv(env):
            base, name = os.getenv("LLM_BASE_URL", url), os.getenv("LLM_MODEL", model)
            if base and name:
                return os.environ[env], base.rstrip("/"), name


def _ask_llm(prov, question, ctx):
    key, base, model = prov
    system = ("You are the analyst inside AI Risk Manager. Answer using ONLY the context facts. Cite the fact ids "
              "in square brackets, like [client:C012]. If the context does not contain the answer, say so. "
              "Be concrete, under 120 words.")
    body = {"model": model, "max_tokens": 400, "temperature": 0.2, "messages": [
        {"role": "system", "content": system},
        {"role": "user", "content": "Context:\n" + "\n".join(f"[{i}] {t}" for i, t in ctx) + f"\n\nQuestion: {question}"}]}
    req = urllib.request.Request(base + "/chat/completions", json.dumps(body).encode(),
                                 {"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                  "User-Agent": "ai-risk-manager/1.0"})  # some gateways reject urllib's default UA
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["choices"][0]["message"]["content"].strip()
