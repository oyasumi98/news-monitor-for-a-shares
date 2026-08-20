import json
import requests
from datetime import datetime, timezone
from .config import *
from .llm_prompt import SYSTEM_PROMPT, make_user_prompt

def call_deepseek(item):
    r = requests.post(
        f"{DEEPSEEK_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                 "Content-Type": "application/json"},
        json={"model": DEEPSEEK_MODEL,
              "messages":[{"role":"system","content":SYSTEM_PROMPT},
                          {"role":"user","content":make_user_prompt(item)}],
              "temperature":0.1,
              "response_format":{"type":"json_object"}},
        timeout=60)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

def call_gemini(item):
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        params={"key": GEMINI_API_KEY},
        json={"system_instruction":{"parts":[{"text":SYSTEM_PROMPT}]},
              "contents":[{"role":"user","parts":[{"text":make_user_prompt(item)}]}],
              "generationConfig":{"temperature":0.1,"responseMimeType":"application/json"}},
        timeout=60)
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]

def score_item(item):
    if DEEPSEEK_API_KEY:
        raw, model = call_deepseek(item), DEEPSEEK_MODEL
    elif GEMINI_API_KEY:
        raw, model = call_gemini(item), GEMINI_MODEL
    else:
        raise RuntimeError("请配置DEEPSEEK_API_KEY或GEMINI_API_KEY")
    raw = raw.strip().replace("```json","").replace("```","").strip()
    score = json.loads(raw)
    score["model"] = model
    score["scored_at"] = datetime.now(timezone.utc).isoformat()
    return score
