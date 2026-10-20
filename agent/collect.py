import io
import requests
import pdfplumber
from bs4 import BeautifulSoup
from tavily import TavilyClient
from agent.config import TAVILY_API_KEY
from agent.cache import cache_get, cache_set

tavily = TavilyClient(api_key=TAVILY_API_KEY)

HEADERS = {"User-Agent": "Mozilla/5.0 (research agent; hackathon project)"}
MAX_PDF_PAGES = 120
MAX_CHARS = 300_000
MIN_CHARS = 500
BLOCKED = ["youtube.com", "reddit.com", "facebook.com", "instagram.com",
           "quora.com", "twitter.com", "x.com", "linkedin.com", "pinterest.com"]

# (doc_type, query template)
QUERIES = {
    "results": "{name} quarterly results press release revenue volume growth",
    "presentation": "{name} investor presentation latest quarter",
    "transcript": "{name} earnings call transcript management commentary",
    "annual_report": "{name} annual report receivables inventory trade payables",
    "news": "{name} sales growth drivers demand channel mix",
}


def search(query, max_results=5):
    key = f"tavily|{query}|{max_results}"
    cached = cache_get(key)
    if cached is not None:
        return cached
    try:
        res = tavily.search(
            query,
            max_results=max_results,
            search_depth="basic",
            include_raw_content=True,
            exclude_domains=BLOCKED,
        )
        results = res.get("results", [])
    except Exception as e:
        print(f"  Search failed for '{query}': {e}")
        return []
    cache_set(key, results)
    return results


def fetch_pdf(url):
    key = f"pdf|{url}"
    cached = cache_get(key)
    if cached is not None:
        return cached["text"]
    try:
        r = requests.get(url, headers=HEADERS, timeout=40)
        r.raise_for_status()
        if len(r.content) > 25_000_000:
            print(f"  Skipped (PDF too large): {url}")
            return ""
        parts = []
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            for i, page in enumerate(pdf.pages[:MAX_PDF_PAGES]):
                text = page.extract_text() or ""
                if text.strip():
                    parts.append(f"[[page {i + 1}]]\n{text}")
        text = "\n\n".join(parts)
    except Exception as e:
        print(f"  PDF fetch failed ({e.__class__.__name__}): {url}")
        return ""
    cache_set(key, {"text": text})
    return text


def fetch_html(url):
    key = f"html|{url}"
    cached = cache_get(key)
    if cached is not None:
        return cached["text"]
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
        text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    except Exception as e:
        print(f"  HTML fetch failed ({e.__class__.__name__}): {url}")
        return ""
    cache_set(key, {"text": text})
    return text


def is_pdf(url):
    return url.lower().split("?")[0].endswith(".pdf")


def collect_company(name, ticker, kinds=None, max_docs=10, per_query=4):
    kinds = kinds or list(QUERIES.keys())
    cache_key = f"docs2|{ticker}|{','.join(kinds)}|{max_docs}|{per_query}"
    cached = cache_get(cache_key)
    if cached is not None:
        print(f"[{name}] loaded {len(cached)} documents from cache")
        return cached

    print(f"[{name}] collecting sources...")
    docs, seen = [], set()

    for kind in kinds:
        query = QUERIES[kind].format(name=name)
        for r in search(query, max_results=per_query):
            url = r.get("url", "")
            if not url or url in seen:
                continue
            seen.add(url)

            if is_pdf(url):
                text = fetch_pdf(url)
            else:
                text = r.get("raw_content") or r.get("content") or ""
                if len(text) < 1500:
                    text = fetch_html(url) or text

            if len(text) < MIN_CHARS:
                continue

            docs.append({
                "company": name,
                "ticker": ticker,
                "doc_type": kind,
                "title": r.get("title", ""),
                "url": url,
                "is_pdf": is_pdf(url),
                "text": text[:MAX_CHARS],
            })
            if len(docs) >= max_docs:
                break
        if len(docs) >= max_docs:
            break

    cache_set(cache_key, docs)
    return docs


def print_docs(docs):
    for d in docs:
        kind = "PDF " if d["is_pdf"] else "HTML"
        print(f"  [{d['doc_type']:<13}] {kind} {len(d['text']):>7} chars  {d['title'][:60]}")
        print(f"      {d['url']}")

