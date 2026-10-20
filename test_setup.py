

from google import genai
from agent.config import GEMINI_API_KEY

client = genai.Client(api_key=GEMINI_API_KEY)

skip = ("live", "tts", "audio", "image", "embedding", "translate",
        "lyria", "veo", "imagen", "robotics", "computer-use", "aqa")

for m in client.models.list():
    actions = m.supported_actions or []
    name = m.name.lower()
    if "generateContent" in actions and not any(s in name for s in skip):
        print(m.name)
        