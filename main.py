
import sys
import os
import json
from agent.resolve import resolve_company
from agent.collect import collect_company
from agent.fin import get_financials
from agent.extract import extract_company, show_facts

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    with_peers = "--peers" in sys.argv
    name = " ".join(args) or "Hindustan Unilever"

    info = resolve_company(name)
    print(f"\nCompany: {info['company_name']} ({info['ticker']})")
    print("Peers:", ", ".join(p["name"] for p in info["peers"]))

    docs = collect_company(info["company_name"], info["ticker"])
    print(f"Company documents: {len(docs)}")

    fin = get_financials(info["ticker"])   # used from Step 5 onward

    os.makedirs("outputs", exist_ok=True)

    facts = extract_company(docs, max_calls=12)
    show_facts(info["company_name"], facts)
    with open(f"outputs/facts_{info['ticker']}.json", "w", encoding="utf-8") as f:
        json.dump(facts, f, indent=2, ensure_ascii=False)

    if with_peers:
        for p in info["peers"]:
            pdocs = collect_company(p["name"], p["ticker"],
                                    kinds=["results", "transcript"], max_docs=4)
            pf = extract_company(pdocs, max_calls=4)
            with open(f"outputs/facts_{p['ticker']}.json", "w", encoding="utf-8") as f:
                json.dump(pf, f, indent=2, ensure_ascii=False)

    