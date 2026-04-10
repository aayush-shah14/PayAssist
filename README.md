# PayAssist — Credit Card Reward Optimizer

## Aim

Help choose **which card to use for a purchase** by combining **deterministic reward math** with a small **policy layer** (preferences and overrides). Raw issuer marketing text can be turned into structured rules via an **optional LLM parser**; rewards are only computed by the engine, not by the LLM.

## Description

PayAssist is a **Python CLI** MVP. You describe a transaction (merchant, category, amount, plus optional channel / booking channel / ISO timestamp). The app loads card definitions from **`cards.json`**, scores cards with a **rule engine** (conditions, exclusions, date windows, priorities, caps), then applies **`policy`** (e.g. rent → Bilt, score overrides). Output is a recommended card name, short reason, and estimated points / dollar value.

## Overall workflow

1. **Data** — Cards live in `cards.json` (validated schema). You can edit JSON by hand or populate it from `.txt` snippets using `llm_parser.py`.
2. **Load** — `storage.load_cards()` reads and validates JSON into `CreditCard` objects.
3. **Score** — `engine.compute_reward` / `get_best_card` pick the best matching rule per card (priority, then multiplier), apply caps (optionally using `UserProfile.per_rule_spend` when `cap_period` is set), then convert points to dollars via `point_value`.
4. **Policy** — `policy.apply_policy` may change the final recommendation (rent preference, `SCORE_OVERRIDES`, future seasonal/relationship logic).
5. **CLI** — `main.py` prompts for a transaction and prints the final recommendation.

```text
cards.json ──► load_cards() ──► get_best_card() ──► apply_policy() ──► printed recommendation
                    ▲
     llm_parser.py (optional) upserts parsed cards
```

## Project layout

```text
PayAssist/
├── main.py           # Interactive CLI
├── llm_parser.py     # OpenAI: raw .txt → validated JSON → cards.json
├── engine.py         # Deterministic reward computation
├── policy.py         # Non-reward preferences and score overrides
├── storage.py        # Load/save cards.json, upsert by card name
├── validation.py     # Schema checks for cards and rules
├── models.py         # Transaction, UserProfile, rule TypedDicts, RewardComputation
├── cards.py          # CreditCard dataclass (runtime mirror of JSON)
├── cards.json        # Card catalog (name, point_value, base_rate, rules)
├── requirements.txt  # Python dependencies (OpenAI client for parser)
└── README.md
```

## Modules and scripts

| File | Role | How to use |
|------|------|------------|
| **`main.py`** | CLI entry: prompts for merchant, category, amount, optional channel / booking channel / timestamp; loads cards; runs engine + policy; prints recommendation. | `python3 main.py` |
| **`llm_parser.py`** | Calls OpenAI (`temperature=0`, JSON-only) for **ongoing earn rules only** (ignores credits/signup bonuses); validates; **normalizes** rules in-module (dedupe / priority hints); **upserts** into `cards.json`. | `pip install -r requirements.txt` then set `OPENAI_API_KEY`. `python3 llm_parser.py path/to/file.txt` or `python3 llm_parser.py benefits_raw`. Optional: `--cards`, `--model`. |
| **`engine.py`** | `compute_reward`, `get_best_card`: filter rules by category, `period` window, legacy dates, `conditions`, `exclusions`; resolve ties by `(priority, multiplier)`; caps + optional `UserProfile`. | Imported by `main.py` and `policy.py`. |
| **`policy.py`** | `apply_policy(..., user_profile=...)`: rent → Bilt; **`SCORE_OVERRIDES`**. | Edit `SCORE_OVERRIDES` as needed. |
| **`storage.py`** | `load_cards`, `save_cards`, `upsert_card`; default path `cards.json` next to this file. | Imported by `main.py` and `llm_parser.py`. |
| **`validation.py`** | `validate_card`, `validate_cards_file_payload`: required rule fields are `type`, `category`, `multiplier`; validates optional `conditions`, `exclusions`, `cap`, `cap_period`, `period` (string or `{start,end}` ISO), `priority`. | Used by `storage` and `llm_parser`. |
| **`models.py`** | `Transaction`, `UserProfile`, rule `TypedDict`s, `RewardComputation`. | Imported across the project. |
| **`cards.py`** | `CreditCard` dataclass built from validated JSON. | Imported by `engine`, `policy`, `storage`. |
| **`cards.json`** | Source of truth for cards at runtime. | Edit manually or update via `llm_parser.py`. |
| **`requirements.txt`** | Declares `openai` for the parser only; CLI + engine use the standard library otherwise. | `pip install -r requirements.txt` |

## Quick start (CLI only)

```bash
cd PayAssist
python3 main.py
```

Follow prompts. Ensure `cards.json` exists (sample cards are included).

## Quick start (LLM ingestion)

```bash
export OPENAI_API_KEY="sk-..."
# optional: export OPENAI_MODEL="gpt-4o-mini"
python3 llm_parser.py your_benefits.txt
# or batch:
mkdir -p benefits_raw && cp *.txt benefits_raw/
python3 llm_parser.py benefits_raw
```

Invalid model output is rejected by **`validation.py`** and will not be written until it passes checks.

## Design notes

- **LLM** is used **only for parsing** website text into JSON.
- **Reward value** is always computed in **`engine.py`** from structured rules.
- **`policy.py`** handles preferences and overrides that are not pure “max points” logic.
