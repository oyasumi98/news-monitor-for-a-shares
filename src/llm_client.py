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

    # ---- 为所有可能缺失的字段提供默认值 ----
    defaults = {
        # 核心字段（与数据库表 event_scores 保持一致）
        'category': 'other',
        'event_type': 'unknown',
        'novelty': 0,
        'economic_impact': 0,
        'transmission': 0,
        'expectation_gap': 50,        # 默认给中性值
        'market_sensitivity': 0,
        'event_score': 0,
        'direction': 'unknown',
        'affected_assets': '',
        'affected_industries': '',
        'rationale': '',
        'second_order_effects': '',
        'risks': '',

        # 新增扩展字段（用于后续分析，即使数据库不存也不影响）
        'event_cluster': None,
        'is_repeat': False,
        'has_new_marginal_change': False,
        'marginal_change_detail': None,
        'industry_chain_layer_1': '',
        'industry_chain_layer_2': '',
        'industry_chain_layer_3': '',
        'us_stocks_direct': [],
        'us_stocks_indirect': [],
        'us_stocks_second_order': [],
        'us_stocks_conceptual': [],
        'a_stocks_direct': [],
        'a_stocks_indirect': [],
        'a_stocks_second_order': [],
        'a_stocks_conceptual': [],
        'market_crowdedness': 'unknown',
        'expectation_gap_detail': '',
        'speaker_name': None,
        'speaker_role': None,
        'speaker_statement_type': None,
        'speaker_core_view': None,
        'validation_catalyst': None,
        'market_context_note': '',
        'speaker_or_source_credibility': None,
    }

    # 用默认值补全缺失字段，已有的保留
    for key, default in defaults.items():
        if key not in score:
            score[key] = default

    # 确保列表字段是列表类型
    list_fields = ['us_stocks_direct', 'us_stocks_indirect', 'us_stocks_second_order',
                   'us_stocks_conceptual', 'a_stocks_direct', 'a_stocks_indirect',
                   'a_stocks_second_order', 'a_stocks_conceptual']
    for f in list_fields:
        if f in score and not isinstance(score[f], list):
            score[f] = []   # 如果不是列表，置空

    score["model"] = model
    score["scored_at"] = datetime.now(timezone.utc).isoformat()
    return score
