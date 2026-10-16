"""Brief composition with LLM optionality and a deterministic verified fallback."""

import html
import json
import logging
from datetime import date
from decimal import Decimal
from pathlib import Path

from .config import settings
from .validate import ValidationError, validate_numeric_claims

LOGGER = logging.getLogger(__name__)


def _number(value: object) -> str:
    if value is None:
        return "n/a"
    decimal = Decimal(str(value))
    return f"{decimal:,.2f}"


def _first(results: dict[str, list[dict]], query: str, **match: object) -> dict | None:
    return next((row for row in results.get(query, []) if all(row.get(k) == v for k, v in match.items())), None)


def deterministic_brief(results: dict[str, list[dict]], as_of: date) -> str:
    gainers = [r for r in results.get("02_gainers_losers", []) if r["direction"] == "gainer"]
    losers = [r for r in results.get("02_gainers_losers", []) if r["direction"] == "loser"]
    volumes = results.get("03_volume_spikes", [])
    sectors = results.get("05_sector_performance", [])
    gaps = results.get("06_gaps", [])
    lines = [f"# US Equities Close — {as_of.isoformat()}", ""]
    if gainers and losers:
        up, down = gainers[0], losers[-1]
        lines.append(
            f"Leadership was led by {up['symbol']} at {_number(up['return_pct'])}%, while "
            f"{down['symbol']} was weakest at {_number(down['return_pct'])}%."
        )
    if volumes:
        row = volumes[0]
        lines.append(
            f"{row['symbol']} had the largest relative turnover at {_number(row['volume_multiple'])}x "
            f"its trailing average volume."
        )
    if sectors:
        best, worst = sectors[0], sectors[-1]
        lines.append(
            f"On an equal-weight basis, {best['sector']} led sectors at {_number(best['equal_weight_return_pct'])}%, "
            f"and {worst['sector']} trailed at {_number(worst['equal_weight_return_pct'])}%."
        )
    if gaps:
        row = gaps[0]
        lines.append(f"The largest opening gap was {row['symbol']} at {_number(row['gap_pct'])}% versus the prior close.")
    if len(lines) == 2:
        lines.append("No completed market data was available for this session.")
    return "\n\n".join(lines) + "\n"


def _brief_prompt(results: dict[str, list[dict]], as_of: date) -> str:
    return f"""Write a concise US equity desk recap for {as_of.isoformat()}, in at most 120 words.
Use only the numbers and tickers in FACTS. Do not introduce market causes or claims not supported
by FACTS. Do not use a numeric ordinal. Return Markdown prose with a single title.

FACTS:\n{json.dumps(results, default=str, indent=2)}"""


def _ollama_prompt(results: dict[str, list[dict]], as_of: date) -> str:
    approved = deterministic_brief(results, as_of).strip()
    return f"""Rewrite the APPROVED BRIEF below into a concise US equity desk note.
Return Markdown only: the title and one to four short paragraphs.

Hard rules:
- Preserve every ticker, number, sign, decimal place, percent sign, and x suffix exactly.
- Do not add any number, date, rank, market cause, or unsupported fact.
- Do not use words that express quantities (for example, "first", "two", or "half").
- If a rewrite could change a number or fact, return the APPROVED BRIEF verbatim.

APPROVED BRIEF:
{approved}
"""


def llm_is_configured() -> bool:
    cfg = settings()
    return (cfg.llm_provider == "openai" and bool(cfg.openai_api_key)) or (
        cfg.llm_provider == "anthropic" and bool(cfg.anthropic_api_key)
    ) or (cfg.llm_provider == "gemini" and bool(cfg.gemini_api_key)) or cfg.llm_provider == "ollama"


def llm_brief(results: dict[str, list[dict]], as_of: date) -> str:
    cfg = settings()
    prompt = _brief_prompt(results, as_of)
    if cfg.llm_provider == "deterministic":
        return deterministic_brief(results, as_of)
    if cfg.llm_provider == "openai":
        if not cfg.openai_api_key:
            return deterministic_brief(results, as_of)
        from openai import OpenAI

        response = OpenAI(api_key=cfg.openai_api_key).chat.completions.create(
            model=cfg.openai_model,
            temperature=0,
            messages=[
                {"role": "system", "content": "You are a precise sell-side market editor."},
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content or ""
    if cfg.llm_provider == "anthropic":
        if not cfg.anthropic_api_key:
            return deterministic_brief(results, as_of)
        from anthropic import Anthropic

        response = Anthropic(api_key=cfg.anthropic_api_key).messages.create(
            model=cfg.anthropic_model,
            max_tokens=300,
            system="You are a precise sell-side market editor.",
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in response.content if block.type == "text")
    if cfg.llm_provider == "gemini":
        if not cfg.gemini_api_key:
            return deterministic_brief(results, as_of)
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=cfg.gemini_api_key)
        response = client.models.generate_content(
            model=cfg.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction="You are a precise sell-side market editor.",
                temperature=0,
                max_output_tokens=300,
            ),
        )
        return response.text or ""
    if cfg.llm_provider == "ollama":
        import requests

        response = requests.post(
            f"{cfg.ollama_base_url.rstrip('/')}/api/generate",
            json={
                "model": cfg.ollama_model,
                "prompt": _ollama_prompt(results, as_of),
                "system": "You are a precise sell-side market editor.",
                "stream": False,
                "options": {"temperature": 0, "num_predict": 300},
            },
            timeout=120,
        )
        response.raise_for_status()
        return str(response.json().get("response", ""))
    raise ValueError(f"Unsupported LLM_PROVIDER: {cfg.llm_provider}")


def render_html(markdown: str) -> str:
    """Deliberately small renderer for the fixed brief format; avoids a Markdown dependency."""
    blocks = []
    for block in markdown.strip().split("\n\n"):
        safe = html.escape(block)
        blocks.append(f"<h1>{safe[2:]}</h1>" if safe.startswith("# ") else f"<p>{safe}</p>")
    return "<!doctype html><html><body>" + "\n".join(blocks) + "</body></html>\n"


def create_brief(results: dict[str, list[dict]], as_of: date, output_dir: str | Path = "briefs") -> tuple[Path, Path, bool]:
    try:
        draft = llm_brief(results, as_of)
        generated = llm_is_configured()
    except Exception:
        LOGGER.exception("LLM draft failed; using deterministic verified fallback")
        draft = deterministic_brief(results, as_of)
        generated = False
    try:
        validate_numeric_claims(draft, results, as_of)
    except ValidationError as exc:
        LOGGER.warning("LLM draft rejected by numeric validation: %s", exc)
        draft = deterministic_brief(results, as_of)
        generated = False
        validate_numeric_claims(draft, results, as_of)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    markdown_path = destination / f"brief_{as_of.isoformat()}.md"
    html_path = destination / f"brief_{as_of.isoformat()}.html"
    markdown_path.write_text(draft, encoding="utf-8")
    html_path.write_text(render_html(draft), encoding="utf-8")
    return markdown_path, html_path, generated
