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
- 时间戳

使用方法：
    from market_data import fetch_all_market_data
    data = fetch_all_market_data()
    print(data["us_gainers"])  # 美股涨幅TOP20
"""

import pandas as pd
import yfinance as yf
import akshare as ak
from datetime import datetime
from typing import Dict, List, Optional


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
    "SPY", "QQQ", "DIA",  # ETF作为基准参考
]

# 美股行业ETF映射（用于行业涨跌幅）
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
    """
    获取美股市场数据：涨跌幅TOP20 + 成交额TOP20 + 行业涨跌幅
    """
    try:
        # 获取股票池的实时行情
        tickers = yf.Tickers(" ".join(US_STOCK_POOL))
        # 用 info 获取最新数据（比 download 更实时）
        quotes = []
        for symbol in US_STOCK_POOL:
            try:
                t = yf.Ticker(symbol)
                info = t.info
                if info:
                    # 提取关键字段
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

        # 涨跌幅TOP20（涨幅）
        gainers = df.nlargest(20, "change_pct")[
            ["symbol", "name", "price", "change_pct", "change", "volume"]
        ].to_dict(orient="records")

        # 跌幅TOP20（跌幅最大的）
        losers = df.nsmallest(20, "change_pct")[
            ["symbol", "name", "price", "change_pct", "change", "volume"]
        ].to_dict(orient="records")

        # 成交额TOP20（按成交量排序）
        volume_top = df.nlargest(20, "volume")[
            ["symbol", "name", "price", "change_pct", "volume"]
        ].to_dict(orient="records")

        # 行业涨跌幅（使用行业ETF）
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
    """
    获取A股市场数据：涨跌幅TOP20 + 成交额TOP20 + 行业涨跌幅
    """
    try:
        # 获取A股实时行情（东方财富源）
        df = ak.stock_zh_a_spot_em()

        if df.empty:
            return {"a_gainers": [], "a_losers": [], "a_volume": [], "a_sectors": [], "timestamp": datetime.now().isoformat()}

        # 重命名列以便处理
        df.columns = ["code", "name", "price", "change_pct", "change", "volume", "amount", "open", "high", "low", "prev_close", "turnover", "pe", "pb", "market_cap", "circ_mv"]

        # 转换数值类型
        for col in ["price", "change_pct", "change", "volume", "amount"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        # 过滤掉无效数据
        df = df[df["price"] > 0]

        if df.empty:
            return {"a_gainers": [], "a_losers": [], "a_volume": [], "a_sectors": [], "timestamp": datetime.now().isoformat()}

        # 涨跌幅TOP20
        gainers = df.nlargest(20, "change_pct")[
            ["code", "name", "price", "change_pct", "change", "amount"]
        ].to_dict(orient="records")

        # 跌幅TOP20
        losers = df.nsmallest(20, "change_pct")[
            ["code", "name", "price", "change_pct", "change", "amount"]
        ].to_dict(orient="records")

        # 成交额TOP20
        volume_top = df.nlargest(20, "amount")[
            ["code", "name", "price", "change_pct", "amount"]
        ].to_dict(orient="records")

        # 行业涨跌幅（使用申万一级行业指数）
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
        # 申万一级行业指数
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
                # 获取行业指数实时行情
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
# 统一入口
# ============================================================

def fetch_all_market_data() -> Dict:
    """
    统一入口：同时获取美股和A股数据
    """
    us_data = fetch_us_market_data()
    a_data = fetch_a_share_market_data()

    return {
        **us_data,
        **a_data,
        "fetched_at": datetime.now().isoformat(),
    }


def format_market_data_for_prompt(data: Dict) -> str:
    """
    将市场数据格式化为文本，方便嵌入到LLM提示词中
    """
    lines = []
    lines.append(f"## 市场行情快照（{data.get('fetched_at', 'N/A')}）")
    lines.append("")

    # 美股涨幅TOP10（精简版）
    gainers = data.get("us_gainers", [])[:10]
    if gainers:
        lines.append("### 美股涨幅TOP10")
        for i, s in enumerate(gainers, 1):
            lines.append(f"{i}. {s['symbol']} {s['name']} +{s['change_pct']:.2f}% (${s['price']:.2f})")
        lines.append("")

    # 美股跌幅TOP10
    losers = data.get("us_losers", [])[:10]
    if losers:
        lines.append("### 美股跌幅TOP10")
        for i, s in enumerate(losers, 1):
            lines.append(f"{i}. {s['symbol']} {s['name']} {s['change_pct']:.2f}% (${s['price']:.2f})")
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

    # 行业涨跌幅
    sectors = data.get("us_sectors", []) or data.get("a_sectors", [])
    if sectors:
        lines.append("### 行业涨跌幅")
        sorted_sectors = sorted(sectors, key=lambda x: x.get("change_pct", 0), reverse=True)
        for s in sorted_sectors[:10]:
            lines.append(f"- {s['sector']}: {s['change_pct']:.2f}%")
        lines.append("")

    return "\n".join(lines)


# ============================================================
# 命令行入口（便于测试）
# ============================================================

if __name__ == "__main__":
    print("正在获取市场数据...")
    data = fetch_all_market_data()

    # 打印摘要
    print(f"\n抓取时间: {data.get('fetched_at')}")
    print(f"美股涨幅TOP20: {len(data.get('us_gainers', []))} 条")
    print(f"美股跌幅TOP20: {len(data.get('us_losers', []))} 条")
    print(f"A股涨幅TOP20: {len(data.get('a_gainers', []))} 条")
    print(f"A股跌幅TOP20: {len(data.get('a_losers', []))} 条")

    # 打印格式化文本（适合嵌入提示词）
    print("\n" + "=" * 60)
    print(format_market_data_for_prompt(data))
