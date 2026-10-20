import json
import time
from google import genai
from google.genai import types
from agent.config import GEMINI_API_KEY
from agent.cache import cache_get, cache_set

_client = genai.Client(api_key=GEMINI_API_KEY)


def ask_json(prompt, schema, model, retries=3):
    """Ask Gemini for JSON matching `schema` (a pydantic class). Cached."""
    key = f"llm|{model}|{prompt}"
    cached = cache_get(key)
    if cached is not None:
        return cached

    for attempt in range(retries):
        try:
            resp = _client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema,
                    temperature=0,
                ),
            )
            data = json.loads(resp.text)
            cache_set(key, data)
            return data
        except Exception as e:
            print(f"LLM call failed (attempt {attempt + 1}/{retries}): {e}")
            time.sleep(5 * (attempt + 1))

    raise RuntimeError("LLM call failed after retries")
