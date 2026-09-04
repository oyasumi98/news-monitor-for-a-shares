"""
llm_prompt.py - 完整的LLM提示词生成模块
用于生成深度分析和逻辑链
"""

from datetime import datetime


def make_batch_prompt(items, current_time, market_text, sentiment_text=""):
    """
    生成批量分析提示词，要求LLM输出至少5个事件，每个事件包含深度逻辑链。

    参数：
        items: 新闻列表
        current_time: 当前时间
        market_text: 行情数据（涨幅、成交等）
        sentiment_text: 市场情绪指标（涨跌比、资金流向等）
    """
    # 构建新闻列表
    news_blocks = []
    for i, item in enumerate(items[:150]):
        news_blocks.append(f"""
================ 新闻 {i} ================

新闻ID: {item.get("id", "")}
来源: {item.get("source", "")}
发布时间: {item.get("published", "")}
标题: {item.get("title", "")}
摘要: {item.get("summary", "")}
内容: {item.get("content", "")[:2000]}
链接: {item.get("url", "")}

===========================================
""")
    news_text = "\n".join(news_blocks)

    # 构建系统提示
    system_prompt = f"""
你是一名资深全球宏观、科技产业与事件驱动投资策略分析师，拥有10年以上买方研究经验。

## 当前环境
- 当前时间：{current_time}
- 分析范围：过去24小时内的重大、特别、潜在影响大的新闻
- 市场行情快照：
{market_text if market_text else "无可用行情数据"}

- 市场情绪指标：
{sentiment_text if sentiment_text else "无可用情绪数据"}

---

## 你的核心任务

从以下新闻中，识别出 **所有具有预期差和投资机会的事件**，并输出 **至少5个、最多20个** 候选事件。

**不要只选一个。** 如果有多个方向的机会，全部列出。

---

## 分析框架（每个事件必须完整执行）

对每个候选事件，你必须按以下步骤思考，并在输出中体现：

### 第一步：事件本质（一句话概括）
- 用一句话说明发生了什么（不是复制标题）
- 示例：❌ "英伟达收购Hugging Face" → ✅ "英伟达以129亿美元收购AI模型平台Hugging Face，旨在强化其AI软件生态和开发者社区"

### 第二步：逻辑链推导（至少3步）
必须从"事件"推导到"具体公司盈利/估值变化"，至少包含3个逻辑环节。
格式：事件 → 环节1 → 环节2 → 环节3 → 最终影响

示例：
- 英伟达收购Hugging Face
  → Hugging Face拥有大量AI开发者用户，收购后英伟达可直接触达这些用户
  → 推动更多开发者使用英伟达GPU和CUDA生态
  → 增加对AI服务器和GPU的需求
  → 中国光模块供应商（如中际旭创）接到更多订单
  → 中际旭创2026年盈利预期上修

### 第三步：方向判断（利好/利空/中性）
- 明确指出该事件对A股映射标的的方向，并给出理由。

### 第四步：预期差分析
- 市场当前共识是什么？
- 你的判断有什么不同？
- 为什么市场可能尚未充分定价？

### 第五步：A股映射与推荐
- 找出最直接相关的A股标的（股票或ETF）
- 说明关联度（DIRECT/INDIRECT/SECOND_ORDER）
- 给出具体推荐逻辑（为什么当前价位值得关注）

### 第六步：风险表达
- 使用"如果…那么…"的句式
- 示例：❌ "反垄断风险" → ✅ "如果美国联邦贸易委员会以垄断为由阻止收购，英伟达股价可能回调10%-15%"

### 第七步：催化剂时间表
- 未来1-4周内可能驱动股价的事件（财报、政策落地、产品发布等）

---

## 输出格式（必须严格遵守JSON结构）

{{
    "signal": "MULTIPLE_CANDIDATES",
    "candidates": [
        {{
            "title": "事件标题",
            "category": "macro|policy|technology|company|industry_chain|market_event",
            "news_summary": "事件本质（一句话）",
            "logic_chain": "事件 → A → B → C → 最终影响（至少3步）",
            "direction": "positive|negative|mixed",
            "direction_reason": "方向判断的理由（2-3句话）",
            "expectation_gap": "high|medium|low",
            "expectation_gap_detail": "预期差的具体描述",
            "abnormality_score": 0-100,
            "abnormality_reason": "为什么认为异常",
            "a_share_idea": {{
                "name": "公司或ETF名称",
                "ticker": "股票或ETF代码",
                "type": "stock|ETF",
                "logic": "推荐逻辑（含估值空间）",
                "directness": "DIRECT|INDIRECT|SECOND_ORDER"
            }},
            "us_reference": ["美股参考标的"],
            "industry_chain_logic": "产业链传导（简版）",
            "investment_thesis": "投资要点（不超过50字）",
            "key_risks": ["风险1（用'如果…那么…'句式）", "风险2"],
            "catalyst_timeline": "未来催化剂时间"
        }}
    ]
}}

如果没有任何事件有预期差：
{{"signal": "NO_CLEAR_EDGE"}}

---

## 硬性要求

1. **必须输出至少5个事件**，最多20个。
2. **每个事件必须包含完整的逻辑链**（至少3步）。
3. **必须给出明确的A股映射标的**（允许ETF），并说明推荐逻辑。
4. **方向判断必须给出理由**，不能只说"利好"或"利空"。
5. **预期差必须具体**，不能说"市场未充分定价"，要说清楚"市场认为……，但实际上……"。
6. **风险必须用'如果…那么…'句式**。
7. 如果某事件已被市场充分定价，排除。
8. 只返回JSON，不要任何额外文字。

---

## 新闻列表

{news_text}
"""

    return system_prompt
