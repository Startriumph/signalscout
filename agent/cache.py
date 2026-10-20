import hashlib
import json
import os

CACHE_DIR = "cache"
os.makedirs(CACHE_DIR, exist_ok=True)

def _path(key: str) -> str:
    h = hashlib.sha256(key.encode()).hexdigest()[:32]
    return os.path.join(CACHE_DIR, f"{h}.json")

def cache_get(key: str):
    p = _path(key)
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def cache_set(key: str, value):
    with open(_path(key), "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)