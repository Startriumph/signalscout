
import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

# Set these after checking which models your key can use (see 0.9)
MODEL_REASONING = "gemini-3.8-flash"
MODEL_EXTRACTION = "gemini-3.8-flash"

if not GEMINI_API_KEY or not TAVILY_API_KEY:
    raise RuntimeError("Missing API keys. Check your .env file.")

