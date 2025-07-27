import yfinance as yf
import pandas as pd
from scipy.stats import percentileofscore
import json
from datetime import datetime

def calculate_price_percentile(ticker_symbol, years=10):
    """
    计算一个ETF当前价格在过去指定年限历史数据中的分位点。
    """
    try:
        stock = yf.Ticker(ticker_symbol)
        hist_prices = stock.history(period=f"{years}y")['Close']
        if hist_prices.empty:
            print(f"警告 ({ticker_symbol}): 无法获取用于价格分位点计算的历史股价。")
            return None
        
        # 使用最新的价格信息来计算
        current_price = hist_prices.iloc[-1]
        
        price_percentile = percentileofscore(hist_prices, current_price)
        return price_percentile
    except Exception as e:
        print(f"错误 ({ticker_symbol}): 在计算价格分位点时发生错误: {e}")
        return None

def update_analysis_cache(configs):
    """
    为所有指定的ETF更新价格分位点分析缓存。
    """
    cache_file = '/app/analysis_cache.json'
    try:
        with open(cache_file, 'r') as f: cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        cache_file = 'analysis_cache.json'
        try:
            with open(cache_file, 'r') as f: cache = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError): cache = {}

    today_str = datetime.now().strftime('%Y-%m-%d')

    for config in configs:
        if not config.get("enabled", False): continue
        
        symbol = config['ticker_symbol']
        
        if cache.get(symbol, {}).get('date') == today_str:
            print(f"信息 ({symbol}): 使用今天的缓存数据。")
            continue

        print(f"信息 ({symbol}): 开始计算10年价格分位点...")
        price_p = calculate_price_percentile(symbol)
        
        cache[symbol] = {
            'date': today_str,
            'price_percentile': price_p
        }
        
        price_str = f"{price_p:.2f}%" if price_p is not None else "N/A"
        print(f"信息 ({symbol}): 分析完成。10年价格分位点: {price_str}")

    with open(cache_file, 'w') as f:
        json.dump(cache, f, indent=4)
        
    return cache