"""
check_groq.py - confirms your Groq key and model work BEFORE you rely on them.
Run from the backend folder (venv active):   python check_groq.py
It never prints your key.
"""
import os
import sys

from dotenv import load_dotenv

load_dotenv()
key = os.getenv("GROQ_API_KEY")
model = os.getenv("GROQ_MODEL") or "openai/gpt-oss-120b"
if not key:
    sys.exit("FAIL: GROQ_API_KEY is not set in backend/.env")
print(f"Key found in .env (length {len(key)}). Configured model: {model}")

from groq import Groq
from llm import GroqLLM, LLMError

try:
    ids = sorted(m.id for m in Groq(api_key=key, timeout=30).models.list().data)
except Exception as e:
    from llm import map_error
    sys.exit("FAIL listing models: " + map_error(e).message)

print(f"\n{len(ids)} models available to your account:")
for i in ids:
    print("  ", i, "   <-- configured" if i == model else "")
if model not in ids:
    sys.exit(f"\nFAIL: '{model}' is not in your list. Set GROQ_MODEL in backend/.env to one of the ids above "
             "(openai/gpt-oss-120b is the usual choice).")

try:
    out = GroqLLM().complete_json("ping", "Reply with one JSON object only.", 'Reply exactly: {"ok": true}')
    print("\nTest call result:", out)
    print("PASS: Groq key and model work.")
except LLMError as e:
    sys.exit(f"\nFAIL test call [{e.code}]: {e.message}")
