"""
market_data.py - 自动抓取美股/A股市场数据的工具模块

数据源：
- 美股：yfinance (Yahoo Finance，免费，无需API Key)
- A股：akshare (东方财富/新浪财经，免费，无需API Key)

输出：
- 美股涨跌幅TOP20
- 美股成交额TOP20
- A股涨跌幅TOP20
- A股成交额TOP20
- 行业涨跌幅（A股）
- 市场情绪指标（涨跌比、涨停跌停、北向资金）
- 技术面指标（MA、RSI、成交量变化）
- 时间戳

使用方法：
    from market_data import fetch_all_market_data, get_market_sentiment, get_technical_indicators
    data = fetch_all_market_data()
    sentiment = get_market_sentiment()
    tech = get_technical_indicators("000001")
"""

import pandas as pd
import yfinance as yf
import akshare as ak
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union
import time


# ============================================================
# 美股数据（使用 yfinance）
# ============================================================

# 美股主流股票池（可扩展）
US_STOCK_POOL = [
    # 科技巨头
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "NFLX",
    # 芯片
    "AMD", "INTC", "TSM", "AVGO", "QCOM", "TXN", "MU", "ARM",
    # 金融
    "JPM", "BAC", "GS", "V", "MA", "WFC", "C",
    # 消费
    "WMT", "PG", "KO", "PEP", "MCD", "COST", "HD", "NKE",
    # 医药
    "JNJ", "PFE", "MRK", "ABBV", "UNH", "LLY",
    # 工业/能源
    "XOM", "CVX", "GE", "CAT", "BA", "HON", "UPS",
    # 通信/媒体
    "DIS", "CMCSA", "VZ", "T",
    # 中概股
    "BABA", "JD", "PDD", "BIDU", "NIO", "LI", "XPEV", "TCOM",
    # 其他重要
    "SPY", "QQQ", "DIA",
]

# 美股行业ETF映射
US_SECTOR_ETFS = {
    "科技": "XLK",
    "金融": "XLF",
    "医疗": "XLV",
    "消费": "XLY",
    "能源": "XLE",
    "工业": "XLI",
    "材料": "XLB",
    "公用事业": "XLU",
    "房地产": "XLRE",
    "通信": "XLC",
}


def fetch_us_market_data() -> Dict:
    """获取美股市场数据：涨跌幅TOP20 + 成交额TOP20 + 行业涨跌幅"""
    try:
        quotes = []
        for symbol in US_STOCK_POOL:
            try:
                t = yf.Ticker(symbol)
                info = t.info
                if info:
                    price = info.get("regularMarketPrice") or info.get("currentPrice") or 0
                    prev_close = info.get("regularMarketPreviousClose") or info.get("previousClose") or price
                    change = price - prev_close if prev_close else 0
                    change_pct = (change / prev_close * 100) if prev_close and prev_close != 0 else 0
                    volume = info.get("regularMarketVolume") or info.get("volume") or 0

                    quotes.append({
                        "symbol": symbol,
                        "name": info.get("longName", info.get("shortName", symbol)),
                        "price": price,
                        "change": change,
                        "change_pct": change_pct,
                        "volume": volume,
                        "sector": info.get("sector", info.get("industry", "未知")),
                    })
            except Exception:
                continue

        df = pd.DataFrame(quotes)

        if df.empty:
            return {"us_gainers": [], "us_losers": [], "us_volume": [], "us_sectors": [], "timestamp": datetime.now().isoformat()}

        gainers = df.nlargest(20, "change_pct")[
            ["symbol", "name", "price", "change_pct", "change", "volume"]
        ].to_dict(orient="records")

        losers = df.nsmallest(20, "change_pct")[
            ["symbol", "name", "price", "change_pct", "change", "volume"]
        ].to_dict(orient="records")

        volume_top = df.nlargest(20, "volume")[
            ["symbol", "name", "price", "change_pct", "volume"]
        ].to_dict(orient="records")

        sector_data = []
        for sector_name, etf_symbol in US_SECTOR_ETFS.items():
            try:
                etf = yf.Ticker(etf_symbol)
                info = etf.info
                price = info.get("regularMarketPrice") or info.get("currentPrice") or 0
                prev_close = info.get("regularMarketPreviousClose") or info.get("previousClose") or price
                change_pct = ((price - prev_close) / prev_close * 100) if prev_close and prev_close != 0 else 0
                sector_data.append({
                    "sector": sector_name,
                    "etf": etf_symbol,
                    "change_pct": change_pct,
                })
            except Exception:
                continue

        return {
            "us_gainers": gainers,
            "us_losers": losers,
            "us_volume": volume_top,
            "us_sectors": sector_data,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        return {
            "us_gainers": [],
            "us_losers": [],
            "us_volume": [],
            "us_sectors": [],
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
        }


# ============================================================
# A股数据（使用 akshare）
# ============================================================

def fetch_a_share_market_data() -> Dict:
    """获取A股市场数据：涨跌幅TOP20 + 成交额TOP20 + 行业涨跌幅"""
    try:
        df = ak.stock_zh_a_spot_em()

        if df.empty:
            return {"a_gainers": [], "a_losers": [], "a_volume": [], "a_sectors": [], "timestamp": datetime.now().isoformat()}

        df.columns = ["code", "name", "price", "change_pct", "change", "volume", "amount", "open", "high", "low", "prev_close", "turnover", "pe", "pb", "market_cap", "circ_mv"]

        for col in ["price", "change_pct", "change", "volume", "amount"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df[df["price"] > 0]

        if df.empty:
            return {"a_gainers": [], "a_losers": [], "a_volume": [], "a_sectors": [], "timestamp": datetime.now().isoformat()}

        gainers = df.nlargest(20, "change_pct")[
            ["code", "name", "price", "change_pct", "change", "amount"]
        ].to_dict(orient="records")

        losers = df.nsmallest(20, "change_pct")[
            ["code", "name", "price", "change_pct", "change", "amount"]
        ].to_dict(orient="records")

        volume_top = df.nlargest(20, "amount")[
            ["code", "name", "price", "change_pct", "amount"]
        ].to_dict(orient="records")

        sectors = _fetch_a_share_sectors()

        return {
            "a_gainers": gainers,
            "a_losers": losers,
            "a_volume": volume_top,
            "a_sectors": sectors,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        return {
            "a_gainers": [],
            "a_losers": [],
            "a_volume": [],
            "a_sectors": [],
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
        }


def _fetch_a_share_sectors() -> List[Dict]:
    """获取A股行业涨跌幅（申万一级行业）"""
    try:
        sector_codes = {
            "食品饮料": "801120",
            "医药生物": "801150",
            "电子": "801080",
            "计算机": "801750",
            "通信": "801770",
            "传媒": "801760",
            "电力设备": "801730",
            "机械设备": "801890",
            "汽车": "801880",
            "有色金属": "801050",
            "钢铁": "801040",
            "煤炭": "801950",
            "石油石化": "801960",
            "基础化工": "801030",
            "建筑材料": "801710",
            "建筑装饰": "801720",
            "房地产": "801180",
            "银行": "801780",
            "非银金融": "801790",
            "国防军工": "801740",
            "家用电器": "801110",
            "纺织服饰": "801130",
            "轻工制造": "801140",
            "商贸零售": "801200",
            "社会服务": "801210",
            "美容护理": "801980",
            "交通运输": "801170",
            "公用事业": "801160",
            "环保": "801970",
            "农林牧渔": "801010",
        }

        sector_data = []
        for name, code in sector_codes.items():
            try:
                df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date="20200101", end_date=datetime.now().strftime("%Y%m%d"), adjust="")
                if not df.empty:
                    latest = df.iloc[-1]
                    prev = df.iloc[-2] if len(df) > 1 else latest
                    change_pct = ((latest["收盘"] - prev["收盘"]) / prev["收盘"] * 100) if prev["收盘"] != 0 else 0
                    sector_data.append({
                        "sector": name,
                        "code": code,
                        "change_pct": change_pct,
                    })
            except Exception:
                continue

        return sector_data

    except Exception:
        return []


# ============================================================
# 市场情绪指标（新增）
# ============================================================

def get_market_sentiment() -> Dict:
    """
    获取A股市场情绪指标
    包括：涨跌比、涨停跌停家数、北向资金流向、强势/弱势板块
    """
    sentiment = {
        "timestamp": datetime.now().isoformat(),
        "advance_decline_ratio": 0,
        "up_count": 0,
        "down_count": 0,
        "limit_up": 0,
        "limit_down": 0,
        "north_flow": {},
        "top_sectors": [],
        "bottom_sectors": [],
        "market_status": "中性"
    }

    try:
        # 1. 获取A股实时行情
        df = ak.stock_zh_a_spot_em()
        if df is not None and not df.empty:
            # 处理列名
            df.columns = ["code", "name", "price", "change_pct", "change", "volume", "amount", "open", "high", "low", "prev_close", "turnover", "pe", "pb", "market_cap", "circ_mv"]
            df["change_pct"] = pd.to_numeric(df["change_pct"], errors="coerce")

            up = len(df[df["change_pct"] > 0])
            down = len(df[df["change_pct"] < 0])
            flat = len(df[df["change_pct"] == 0])

            sentiment["up_count"] = up
            sentiment["down_count"] = down
            sentiment["advance_decline_ratio"] = round(up / (up + down), 3) if (up + down) > 0 else 0

            # 涨停跌停（按A股标准：±9.8%以上视为涨停/跌停）
            sentiment["limit_up"] = len(df[df["change_pct"] >= 9.8])
            sentiment["limit_down"] = len(df[df["change_pct"] <= -9.8])

            # 市场状态判断
            ratio = sentiment["advance_decline_ratio"]
            if ratio > 0.6:
                sentiment["market_status"] = "偏乐观（涨多跌少）"
            elif ratio < 0.4:
                sentiment["market_status"] = "偏悲观（跌多涨少）"
            else:
                sentiment["market_status"] = "中性"

        # 2. 北向资金（沪深股通）
        try:
            north_flow = ak.stock_hsgt_north_net_flow_in_em()
            if north_flow is not None and not north_flow.empty:
                latest = north_flow.iloc[-1]
                sentiment["north_flow"] = {
                    "date": str(latest.get("日期", "")),
                    "net_in": float(latest.get("净买入", 0)),
                    "cumulative": float(latest.get("累计净买入", 0))
                }
        except Exception as e:
            print(f"[SENTIMENT] 北向资金数据获取失败: {e}")

        # 3. 强势/弱势板块
        try:
            sector_df = ak.stock_sector_spot_em()
            if sector_df is not None and not sector_df.empty:
                sector_df.columns = ["板块", "最新价", "涨跌幅", "涨跌额", "成交量", "成交额"]
                sector_df["涨跌幅"] = pd.to_numeric(sector_df["涨跌幅"], errors="coerce")
                sector_df = sector_df.dropna(subset=["涨跌幅"])

                top = sector_df.nlargest(5, "涨跌幅")
                bottom = sector_df.nsmallest(5, "涨跌幅")

                sentiment["top_sectors"] = [
                    {"name": row["板块"], "change_pct": float(row["涨跌幅"])}
                    for _, row in top.iterrows()
                ]
                sentiment["bottom_sectors"] = [
                    {"name": row["板块"], "change_pct": float(row["涨跌幅"])}
                    for _, row in bottom.iterrows()
                ]
        except Exception as e:
            print(f"[SENTIMENT] 板块数据获取失败: {e}")

    except Exception as e:
        print(f"[SENTIMENT] 情绪指标获取失败: {e}")
        sentiment["error"] = str(e)

    return sentiment


# ============================================================
# 技术面指标（新增）
# ============================================================

def get_technical_indicators(symbol: str, period: str = "daily", days: int = 60) -> Dict:
    """
    获取个股技术面指标

    参数：
        symbol: 股票代码（A股如 '000001'，美股如 'AAPL'）
        period: 周期 'daily' 或 'weekly'
        days: 历史数据天数

    返回：
        {
            "symbol": 代码,
            "ma5": 5日均线,
            "ma10": 10日均线,
            "ma20": 20日均线,
            "rsi": RSI指标,
            "volume_change": 成交量变化率,
            "price_position": 价格在均线中的位置
        }
    """
    result = {
        "symbol": symbol,
        "ma5": None,
        "ma10": None,
        "ma20": None,
        "rsi": None,
        "volume_change": None,
        "price_position": "unknown",
        "error": None
    }

    try:
        # 判断是A股还是美股
        if symbol.isdigit() or (len(symbol) == 6 and symbol[:1].isdigit()):
            # A股
            df = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date=(datetime.now() - timedelta(days=days)).strftime("%Y%m%d"), end_date=datetime.now().strftime("%Y%m%d"), adjust="qfq")
        else:
            # 美股
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=f"{days}d")

        if df is None or df.empty:
            result["error"] = "无数据"
            return result

        # 标准化列名
        if "收盘" in df.columns:
            close_col = "收盘"
            volume_col = "成交量"
        elif "Close" in df.columns:
            close_col = "Close"
            volume_col = "Volume"
        else:
            result["error"] = "无法识别列名"
            return result

        # 计算均线
        prices = df[close_col].values
        if len(prices) >= 5:
            result["ma5"] = round(float(prices[-5:].mean()), 2)
        if len(prices) >= 10:
            result["ma10"] = round(float(prices[-10:].mean()), 2)
        if len(prices) >= 20:
            result["ma20"] = round(float(prices[-20:].mean()), 2)

        # 计算RSI（14日）
        if len(prices) >= 15:
            gains = []
            losses = []
            for i in range(1, len(prices)):
                diff = prices[i] - prices[i-1]
                if diff > 0:
                    gains.append(diff)
                    losses.append(0)
                else:
                    gains.append(0)
                    losses.append(abs(diff))

            avg_gain = sum(gains[-14:]) / 14
            avg_loss = sum(losses[-14:]) / 14

            if avg_loss == 0:
                result["rsi"] = 100
            else:
                rs = avg_gain / avg_loss
                result["rsi"] = round(100 - (100 / (1 + rs)), 2)

        # 成交量变化（对比5日均量）
        if volume_col in df.columns and len(df) >= 5:
            volumes = df[volume_col].values[-5:]
            avg_volume = volumes.mean()
            current_volume = volumes[-1]
            if avg_volume > 0:
                result["volume_change"] = round((current_volume / avg_volume - 1) * 100, 2)

        # 价格位置判断
        current_price = prices[-1]
        if result["ma20"] and result["ma5"]:
            if current_price > result["ma20"] and current_price > result["ma5"]:
                result["price_position"] = "多头排列（强势）"
            elif current_price > result["ma20"] and current_price < result["ma5"]:
                result["price_position"] = "短期回调（中性偏多）"
            elif current_price < result["ma20"] and current_price < result["ma5"]:
                result["price_position"] = "空头排列（弱势）"
            elif current_price < result["ma20"] and current_price > result["ma5"]:
                result["price_position"] = "短期反弹（中性偏弱）"
            else:
                result["price_position"] = "震荡整理"

    except Exception as e:
        result["error"] = str(e)

    return result


# ============================================================
# 统一入口
# ============================================================

def fetch_all_market_data() -> Dict:
    """统一入口：获取美股和A股基础市场数据"""
    us_data = fetch_us_market_data()
    a_data = fetch_a_share_market_data()
    sentiment = get_market_sentiment()

    return {
        **us_data,
        **a_data,
        "sentiment": sentiment,
        "fetched_at": datetime.now().isoformat(),
    }


# ============================================================
# 格式化函数（供LLM提示词使用）
# ============================================================

def format_market_data_for_prompt(data: Dict) -> str:
    """将市场数据格式化为文本，嵌入LLM提示词"""
    lines = []
    lines.append(f"## 📊 市场行情快照（{data.get('fetched_at', 'N/A')}）")
    lines.append("")

    # 情绪指标
    sentiment = data.get("sentiment", {})
    if sentiment:
        lines.append("### 市场情绪")
        lines.append(f"- 涨跌比：{sentiment.get('up_count', 0)}涨 / {sentiment.get('down_count', 0)}跌 → {sentiment.get('market_status', '未知')}")
        lines.append(f"- 涨停：{sentiment.get('limit_up', 0)}家 | 跌停：{sentiment.get('limit_down', 0)}家")

        north = sentiment.get("north_flow", {})
        if north and north.get("net_in") is not None:
            net_in = north.get("net_in", 0)
            direction = "净流入" if net_in > 0 else "净流出"
            lines.append(f"- 北向资金：{direction} {abs(net_in):.2f}亿元")

        top_sectors = sentiment.get("top_sectors", [])
        if top_sectors:
            lines.append(f"- 强势板块：{', '.join([s['name'] for s in top_sectors[:3]])}")

        bottom_sectors = sentiment.get("bottom_sectors", [])
        if bottom_sectors:
            lines.append(f"- 弱势板块：{', '.join([s['name'] for s in bottom_sectors[:3]])}")
        lines.append("")

    # A股涨幅TOP10
    a_gainers = data.get("a_gainers", [])[:10]
    if a_gainers:
        lines.append("### A股涨幅TOP10")
        for i, s in enumerate(a_gainers, 1):
            lines.append(f"{i}. {s['code']} {s['name']} +{s['change_pct']:.2f}% (¥{s['price']:.2f})")
        lines.append("")

    # A股跌幅TOP10
    a_losers = data.get("a_losers", [])[:10]
    if a_losers:
        lines.append("### A股跌幅TOP10")
        for i, s in enumerate(a_losers, 1):
            lines.append(f"{i}. {s['code']} {s['name']} {s['change_pct']:.2f}% (¥{s['price']:.2f})")
        lines.append("")

    # A股成交额TOP10
    a_volume = data.get("a_volume", [])[:10]
    if a_volume:
        lines.append("### A股成交额TOP10")
        for i, s in enumerate(a_volume, 1):
            amount_str = f"{s['amount']:.2f}亿" if s['amount'] > 10000 else f"{s['amount']:.0f}万"
            lines.append(f"{i}. {s['code']} {s['name']} {amount_str} (涨跌幅 {s['change_pct']:.2f}%)")
        lines.append("")

    # 行业涨跌幅
    sectors = data.get("a_sectors", []) or data.get("us_sectors", [])
    if sectors:
        lines.append("### 行业涨跌幅")
        sorted_sectors = sorted(sectors, key=lambda x: x.get("change_pct", 0), reverse=True)
        for s in sorted_sectors[:10]:
            sign = "+" if s["change_pct"] > 0 else ""
            lines.append(f"- {s['sector']}: {sign}{s['change_pct']:.2f}%")
        lines.append("")

    return "\n".join(lines)


def format_sentiment_for_prompt(sentiment: Dict) -> str:
    """单独格式化情绪指标"""
    if not sentiment or sentiment.get("error"):
        return "市场情绪数据暂时不可用"

    lines = ["## 📈 市场情绪快照"]
    lines.append(f"- 涨跌比：{sentiment.get('up_count', 0)}涨 / {sentiment.get('down_count', 0)}跌 → {sentiment.get('market_status', '未知')}")
    lines.append(f"- 涨停：{sentiment.get('limit_up', 0)}家 | 跌停：{sentiment.get('limit_down', 0)}家")

    north = sentiment.get("north_flow", {})
    if north and north.get("net_in") is not None:
        net_in = north.get("net_in", 0)
        direction = "净流入" if net_in > 0 else "净流出"
        lines.append(f"- 北向资金：{direction} {abs(net_in):.2f}亿元")

    top = sentiment.get("top_sectors", [])
    if top:
        lines.append(f"- 强势板块：{', '.join([s['name'] for s in top[:3]])}")

    bottom = sentiment.get("bottom_sectors", [])
    if bottom:
        lines.append(f"- 弱势板块：{', '.join([s['name'] for s in bottom[:3]])}")

    return "\n".join(lines)


def format_technical_for_prompt(tech_data: Dict) -> str:
    """格式化技术面指标"""
    if not tech_data or tech_data.get("error"):
        return f"技术指标获取失败: {tech_data.get('error', '未知错误')}"

    lines = [f"## 📉 技术面指标 - {tech_data.get('symbol', '')}"]
    lines.append(f"- MA5：{tech_data.get('ma5', 'N/A')}")
    lines.append(f"- MA10：{tech_data.get('ma10', 'N/A')}")
    lines.append(f"- MA20：{tech_data.get('ma20', 'N/A')}")
    lines.append(f"- RSI(14)：{tech_data.get('rsi', 'N/A')}")
    lines.append(f"- 成交量变化：{tech_data.get('volume_change', 'N/A')}%")
    lines.append(f"- 价格位置：{tech_data.get('price_position', '未知')}")

    return "\n".join(lines)


# ============================================================
# 命令行入口
# ============================================================

if __name__ == "__main__":
    print("正在获取市场数据...")
    data = fetch_all_market_data()

    print(f"\n抓取时间: {data.get('fetched_at')}")
    print(f"A股涨幅TOP20: {len(data.get('a_gainers', []))} 条")
    print(f"A股跌幅TOP20: {len(data.get('a_losers', []))} 条")
    print(f"A股成交额TOP20: {len(data.get('a_volume', []))} 条")

    sentiment = data.get("sentiment", {})
    print(f"\n市场情绪: {sentiment.get('market_status', '未知')}")
    print(f"涨跌比: {sentiment.get('up_count', 0)}/{sentiment.get('down_count', 0)}")
    print(f"涨停: {sentiment.get('limit_up', 0)}家, 跌停: {sentiment.get('limit_down', 0)}家")

    print("\n" + "=" * 60)
    print(format_market_data_for_prompt(data))
