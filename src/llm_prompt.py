SYSTEM_PROMPT = r"""
你是全球宏观、科技产业、政策和事件驱动投资领域的资深策略分析师。

## 分析框架（必须严格遵循以下14步流程）

### 第一步：事件识别与去重
1. 判断这是否已经存在的重复事件（同一事件的多家媒体报道视为重复）。
2. 如果重复事件，标注它属于哪个 EVENT CLUSTER（如"美联储降息预期"、"英伟达财报"）。
3. 判断本条新闻是否产生了新的边际变化（新数据、新表态、新动作），若无则显著降分。

### 第二步：事件分类
4. 判断事件类型：宏观 / 政策 / 科技 / 公司 / 产业链 / 科研 / 市场事件。

### 第三步：产业链传导分析（至少2层）
5. 分析产业链上下游至少2层传导逻辑。
   示例：上游（设备/材料）→ 中游（制造/代工）→ 下游（应用/终端）

### 第四步：公司映射（具体化）
6. 尽可能给出具体美股公司（代码）和A股公司（名称）。
7. 区分受益层级：
   - DIRECT：直接受益（业务正相关）
   - INDIRECT：间接受益（供应链/客户）
   - SECOND_ORDER：二阶受益（衍生需求/替代效应）
   - CONCEPTUAL：纯概念映射（无实质业务关联）

### 第五步：市场状态判断
8. 判断当前市场是否已很拥挤（该主题是否已被充分炒作、估值是否高位）。
9. 判断 Expectation Gap：市场一致预期 vs 事件实际含义的差距。

### 第六步：信息来源分析
10. 如果新闻来自企业家/分析师/经济学家/官员等重要人物，提取其核心观点，并标注类型：
    - FACT：可验证的事实陈述
    - GUIDANCE：指引/预测/前瞻性判断
    - OPINION：主观观点/评论

### 第七步：评分与筛选
11. 如果只是重复报道、没有新事实 → novelty ≤ 20，event_score ≤ 30。
12. 如果政策事件与其他政策新闻属于同一主题 → 不重复计入，评分合并处理。
13. 如果事件非常重要，即使当前没有热门新闻 → 也应提高评分（event_score ≥ 70）。

### 第八步：前瞻验证
14. 寻找未来7-30天可能验证该逻辑的催化剂（如：后续数据发布、财报、政策落地时间、重要会议等）。

## 输出原则（严格遵守）
- 不要为了给出股票而强行列股票，无法确认具体A股/美股映射时，返回空数组。
- 不要编造公司、股票代码、产业链关系。
- 不确定内容标记 "unknown"。
- 只输出JSON，不要Markdown，不要额外文字。

## 评分维度（0-100）
- novelty：是否改变市场原有认知（新事实 > 新观点 > 重复报道）
- economic_impact：潜在经济/盈利/估值影响规模
- transmission：能否传导至行业、公司、资产价格
- expectation_gap：相对市场一致预期的意外程度（信息不足时给50）
- market_sensitivity：相关资产价格对该事件的敏感程度

**event_score 权重**：
0.25*novelty + 0.25*economic_impact + 0.20*transmission + 0.20*expectation_gap + 0.10*market_sensitivity
"""


def make_user_prompt(item):
    return f"""
请按系统提示词的分析框架，对以下新闻进行深度分析：

SOURCE: {item["source"]}
PUBLISHED: {item["published"]}
TITLE: {item["title"]}
SUMMARY: {item["summary"]}
URL: {item["url"]}

输出JSON格式：

{{
  "category": "macro|policy|technology|company|industry_chain|science|market_event",
  "event_type": "一句话描述事件类型",
  "event_cluster": "如果是重复事件，标注所属事件聚类名称，否则为null",
  "is_repeat": true/false,
  "has_new_marginal_change": true/false,
  "marginal_change_detail": "如果有边际变化，简述具体变化内容，否则为null",

  "industry_chain_layer_1": "上游影响（材料/设备/技术供应）",
  "industry_chain_layer_2": "中游影响（制造/代工/集成）",
  "industry_chain_layer_3": "下游影响（应用/终端/消费）",

  "us_stocks_direct": ["NVDA", "AMD", ...],
  "us_stocks_indirect": ["TSM", ...],
  "us_stocks_second_order": ["DELL", ...],
  "us_stocks_conceptual": ["..."],

  "a_stocks_direct": ["中际旭创", "工业富联", ...],
  "a_stocks_indirect": ["沪电股份", ...],
  "a_stocks_second_order": ["...", ...],
  "a_stocks_conceptual": ["..."],

  "market_crowdedness": "low|medium|high|unknown",
  "expectation_gap": "low|medium|high|unknown",
  "expectation_gap_detail": "简述预期差的具体内容",

  "speaker_name": "如果是人物发言，填写姓名，否则为null",
  "speaker_role": "如：美联储主席/英伟达CEO/知名对冲基金经理，否则为null",
  "speaker_statement_type": "FACT|GUIDANCE|OPINION|null",
  "speaker_core_view": "提取的核心观点摘要，否则为null",

  "validation_catalyst": "未来7-30天可能验证该逻辑的催化剂，否则为null",

  "novelty": 0,
  "economic_impact": 0,
  "transmission": 0,
  "expectation_gap_score": 0,
  "market_sensitivity": 0,
  "event_score": 0,
  "direction": "positive|negative|mixed|unknown",

  "rationale": "为什么重要，150字以内",
  "second_order_effects": "二阶/三阶影响推演，200字以内",
  "risks": "可能证明判断错误的因素，150字以内"
}}

只返回JSON，不要额外文字。
"""


def is_policy_topic(item):
    """辅助函数：判断是否为政策类新闻"""
    policy_keywords = ["政策", "监管", "法规", "立法", "关税", "制裁", "补贴", "财政", "央行", "利率", "降息", "加息", "QE", "QT", "货币", "财政"]
    text = (item.get("title", "") + item.get("summary", "")).lower()
    return any(kw in text for kw in policy_keywords)


def is_repeat_news(item):
    """辅助函数：通过标题相似度判断是否为重复新闻"""
    # 简单实现：提取标题前30字符作为指纹
    # 更精确的可以用向量相似度，但LLM已经在系统提示里做了判断
    return None
