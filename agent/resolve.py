from pydantic import BaseModel
import yfinance as yf
from agent.llm import ask_json
from agent.config import MODEL_REASONING


class Peer(BaseModel):
    name: str
    nse_symbol: str


class Company(BaseModel):
    company_name: str
    nse_symbol: str
    sector: str
    sub_sector: str
    peers: list[Peer]


def verify_ticker(symbol):
    """Return a Yahoo Finance ticker (e.g. HINDUNILVR.NS) if it has price data, else None."""
    symbol = symbol.strip().upper().replace(".NS", "").replace(".BO", "")
    for suffix in (".NS", ".BO"):
        try:
            hist = yf.Ticker(symbol + suffix).history(period="5d")
            if not hist.empty:
                return symbol + suffix
        except Exception:
            pass
    return None


def resolve_company(name):
    prompt = f"""You are helping a financial research agent.
Company: {name}

Return:
- the company's official listed name
- its NSE trading symbol (no .NS suffix)
- its sector and sub-sector
- the 3 closest listed Indian peers (similar business mix, ideally similar scale), each with their NSE symbol

Use only companies listed on Indian exchanges. If you are unsure of a symbol, give your best guess."""

    data = ask_json(prompt, Company, MODEL_REASONING)

    ticker = verify_ticker(data["nse_symbol"])
    if ticker is None:
        raise ValueError(
            f"Could not verify ticker '{data['nse_symbol']}' for {name}. "
            "Check the company name or enter the ticker manually."
        )

    verified_peers = []
    for p in data["peers"]:
        pt = verify_ticker(p["nse_symbol"])
        if pt:
            verified_peers.append({"name": p["name"], "ticker": pt})
        else:
            print(f"Dropped unverified peer: {p['name']} ({p['nse_symbol']})")

    return {
        "company_name": data["company_name"],
        "ticker": ticker,
        "sector": data["sector"],
        "sub_sector": data["sub_sector"],
        "peers": verified_peers,
    }
