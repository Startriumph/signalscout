import re
from pydantic import BaseModel
from agent.llm import ask_json
from agent.config import MODEL_EXTRACTION

ALLOWED = {
    "revenue_growth_pct", "volume_growth_pct", "same_store_growth_pct",
    "receivables", "inventory", "payables", "store_count",
    "guidance", "channel_comment",
}
TEXT_METRICS = {"guidance", "channel_comment"}  # facts with no number

KEYWORDS = [
    "volume", "growth", "same store", "same-store", "sssg", "like-for-like",
    "receivable", "inventor", "payable", "stores", "outlook", "expect",
    "guidance", "quick commerce", "e-commerce", "modern trade", "rural",
    "channel", "buyer",
]

PAGE_RE = re.compile(r"\[\[page (\d+)\]\]")
NUM_RE = re.compile(r"\d[\d,]*\.?\d*")


class Fact(BaseModel):
    metric: str
    period: str
    value_text: str
    unit: str
    is_decline: bool
    quote: str


class Facts(BaseModel):
    facts: list[Fact]


PROMPT = """You extract facts from a company document for a financial research agent.
Company: {company}
Document: {title} ({doc_type})

Return ONLY facts stated explicitly in the text below. Never calculate, infer or guess.
For every fact, copy `quote` exactly as written in the text (max 300 characters, same spelling,
numbers and punctuation, without any [[page N]] markers). `value_text` must be the number exactly
as it appears inside the quote ("" for text-only facts).

Metrics:
- revenue_growth_pct: year-on-year growth in revenue or sales
- volume_growth_pct: growth in volume or quantity sold (units, tonnes, grams, underlying volume growth), NOT revenue growth
- same_store_growth_pct: same-store or like-for-like sales growth
- receivables, inventory, payables: balance-sheet amounts (put the unit as stated, e.g. "INR crore", "INR million")
- store_count: number of stores at the end of a period
- guidance: forward-looking statement by management about future growth, margins or demand (value_text = "")
- channel_comment: statement about sales channels such as quick commerce, e-commerce, modern trade, general trade, rural or urban demand (value_text = "")

`period` = the period the fact refers to, as labelled in the document (e.g. "Q1 FY27", "FY26", "H1 FY26"), or "" if not stated.
Set is_decline = true only if the quote describes a decline, fall or negative growth.
If the text contains none of these, return an empty list.

TEXT:
{chunk}"""


def _norm(s):
    s = s.lower()
    for a, b in (("\u2019", "'"), ("\u2018", "'"), ("\u201c", '"'),
                 ("\u201d", '"'), ("\u2013", "-"), ("\u2014", "-")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


def _pages(text):
    """List of (page_number or None, normalized text)."""
    parts = PAGE_RE.split(text)
    if len(parts) == 1:
        return [(None, _norm(text))]
    out = []
    if parts[0].strip():
        out.append((None, _norm(parts[0])))
    for i in range(1, len(parts) - 1, 2):
        out.append((int(parts[i]), _norm(parts[i + 1])))
    return out


def _split(text, size=30000):
    chunks, cur = [], ""
    for line in text.split("\n"):
        if cur and len(cur) + len(line) + 1 > size:
            chunks.append(cur)
            cur = ""
        cur += line + "\n"
    if cur.strip():
        chunks.append(cur)
    return chunks


def best_chunks(text, n=3, size=30000, min_score=3):
    scored = []
    for c in _split(text, size):
        low = c.lower()
        score = sum(low.count(k) for k in KEYWORDS)
        if score >= min_score:
            scored.append((score, c))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:n]]


def _parse_number(s):
    m = NUM_RE.search(s)
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def _check(f, pages, whole):
    """Return {'page', 'value'} if the fact is verified in the source, else None."""
    if f["metric"] not in ALLOWED:
        return None
    q = _norm(f["quote"])
    if len(q) < 15:
        return None

    vt = f["value_text"].strip()
    value = None
    if vt:
        if _norm(vt) not in q:          # the number must appear inside the quote
            return None
        num = _parse_number(vt)
        if num is None:
            return None
        neg = f["is_decline"] or bool(re.match(r"^[\s(]*[-\u2212(]", vt))
        value = -abs(num) if neg else num
    elif f["metric"] not in TEXT_METRICS:
        return None

    for page, t in pages:               # the quote must appear in the document
        if q in t:
            return {"page": page, "value": value}
    if q in whole:
        return {"page": None, "value": value}
    return None


def extract_company(docs, max_calls=12):
    if not docs:
        return []
    name = docs[0]["company"]
    order = {"primary": 0, "secondary": 1, "aggregator": 2}
    facts, seen = [], set()
    calls = proposed = 0

    for d in sorted(docs, key=lambda x: order.get(x.get("tier", "secondary"), 1)):
        if calls >= max_calls:
            break
        pages = _pages(d["text"])
        whole = _norm(PAGE_RE.sub(" ", d["text"]))

        for chunk in best_chunks(d["text"]):
            if calls >= max_calls:
                break
            calls += 1
            prompt = PROMPT.format(
                company=d["company"], title=d["title"][:100],
                doc_type=d["doc_type"], chunk=chunk,
            )
            try:
                data = ask_json(prompt, Facts, MODEL_EXTRACTION)
            except Exception as e:
                print(f"  Skipped a chunk of '{d['title'][:40]}': {e}")
                continue

            for f in data.get("facts", []):
                proposed += 1
                ok = _check(f, pages, whole)
                if ok is None:
                    continue
                key = (f["metric"], f["period"], f["value_text"], f["quote"][:60])
                if key in seen:
                    continue
                seen.add(key)
                facts.append({
                    "company": d["company"], "ticker": d["ticker"],
                    "metric": f["metric"], "period": f["period"],
                    "value": ok["value"], "unit": f["unit"],
                    "quote": f["quote"], "page": ok["page"],
                    "url": d["url"], "title": d["title"],
                    "tier": d.get("tier", "secondary"), "doc_type": d["doc_type"],
                })

    print(f"  [{name}] {len(facts)} verified of {proposed} proposed ({calls} LLM calls)")
    return facts


def show_facts(name, facts, per_metric=5):
    print(f"\n=== Verified facts: {name} ({len(facts)}) ===")
    by = {}
    for f in facts:
        by.setdefault(f["metric"], []).append(f)
    for metric, items in by.items():
        print(f"\n{metric} ({len(items)})")
        for f in items[:per_metric]:
            val = "" if f["value"] is None else f"{f['value']:g} {f['unit']}"
            pg = f" p.{f['page']}" if f["page"] else ""
            print(f"  [{f['period'] or '-'}] {val} ({f['tier']}){pg}")
            print(f"     \"{f['quote'][:140]}\"")
            print(f"     {f['url']}")

            