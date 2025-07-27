import yfinance as yf
import time
import json
import threading
from datetime import datetime, timedelta
from financial_analyzer import update_analysis_cache

def get_stock_info(ticker_symbol):
    """
    获取ETF的最新价格和相关信息。
    """
    try:
        stock = yf.Ticker(ticker_symbol)
        info = stock.info
        
        price = info.get('regularMarketPrice')
        if price is None:
            price = info.get('currentPrice')
        if price is None:
            hist = stock.history(period="2d") 
            if not hist.empty:
                price = hist['Close'].iloc[-1]

        pe_ratio = info.get('trailingPE')

        dividend_yield = None
        if price and price > 0:
            one_year_ago = datetime.now() - timedelta(days=366)
            dividends_history = stock.dividends
            if not dividends_history.empty:
                dividends_history.index = dividends_history.index.tz_localize(None)
                dividends_last_year = dividends_history[dividends_history.index > one_year_ago]
                
                if not dividends_last_year.empty:
                    sum_dividends = dividends_last_year.sum()
                    dividend_yield = sum_dividends / price
                else:
                    dividend_yield = 0.0
            else:
                dividend_yield = 0.0

        return {
            "price": price,
            "pe": pe_ratio,
            "div_yield": dividend_yield
        }
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] 获取 {ticker_symbol} 实时信息时发生严重错误: {e}")
        return None

def format_value(value, unit="", default_val="N/A"):
    """格式化数值，如果是None则返回默认值"""
    if value is None:
        return default_val
    return f"{value:.2f}{unit}"

def monitor_stock(config, analysis_data):
    """单个ETF的监控线程函数"""
    ticker_symbol = config['ticker_symbol']
    remark = config.get('remark', ticker_symbol)
    
    try:
        next_buy_price = float(config['buy_price'])
        next_sell_price = float(config['sell_price'])
        grid_percent = float(config['grid_percent'])
    except (ValueError, TypeError) as e:
        print(f"错误 ({ticker_symbol}): config.json中的价格或比例格式不正确。错误: {e}")
        return

    price_percentile = analysis_data.get('price_percentile')
    
    header = (f"--- 线程启动: {remark}({ticker_symbol}) | "
              f"10年价格分位: {format_value(price_percentile, '%')} | "
              f"买入线: {next_buy_price:.2f} | "
              f"卖出线: {next_sell_price:.2f} ---")
    print(header)

    while True:
        stock_info = get_stock_info(ticker_symbol)
        if not stock_info or stock_info.get("price") is None:
            print(f"[{time.strftime('%H:%M:%S')}] {remark}({ticker_symbol}): 无法获取价格，1分钟后重试。")
            time.sleep(60)
            continue

        current_price = stock_info['price']
        current_pe = stock_info.get('pe')
        current_yield = stock_info.get('div_yield')
        
        yield_display_val = current_yield * 100 if current_yield is not None else None

        # --- 更新日志，加入10年价格分位点 ---
        log_msg = (f"[{time.strftime('%H:%M:%S')}] {remark}({ticker_symbol}): "
                   f"当前价 {current_price:.2f} | "
                   f"10年分位: {format_value(price_percentile, '%')} | "
                   f"PE: {format_value(current_pe, '', 'N/A')} | "
                   f"股息率: {format_value(yield_display_val, '%', 'N/A')} | "
                   f"买入线 {next_buy_price:.2f} | "
                   f"卖出线 {next_sell_price:.2f}")
        print(log_msg)

        if current_price <= next_buy_price:
            print(f"\n{'='*15} [买入提醒] {'='*15}")
            print(f"ETF {remark}({ticker_symbol}) 当前价 {current_price:.2f} 已触达或跌破买入线 {next_buy_price:.2f}")
            next_buy_price *= (1 - grid_percent)
            print(f"新的下一买入线: {next_buy_price:.2f}")
            print(f"{'='*42}\n")

        elif current_price >= next_sell_price:
            print(f"\n{'='*15} [卖出提醒] {'='*15}")
            print(f"ETF {remark}({ticker_symbol}) 当前价 {current_price:.2f} 已触达或突破卖出线 {next_sell_price:.2f}")
            next_sell_price *= (1 + grid_percent)
            print(f"新的下一卖出线: {next_sell_price:.2f}")
            print(f"{'='*42}\n")

        time.sleep(15)

def main():
    """主函数，初始化分析，然后启动监控线程"""
    config_path = '/app/config.json'
    try:
        with open(config_path, 'r') as f: configs = json.load(f)
    except FileNotFoundError:
        try:
            with open('config.json', 'r') as f: configs = json.load(f)
        except FileNotFoundError:
            print("错误: config.json 文件未找到。"); return
    except json.JSONDecodeError:
        print("错误: config.json 文件格式不正确。"); return

    print("--- 系统启动：正在为ETF更新10年价格分位点，请稍候... ---")
    enabled_configs = [c for c in configs if c.get("enabled", False)]
    if not enabled_configs:
        print("配置文件中没有启用 (enabled: true) 的监控任务。程序退出。"); return
        
    analysis_cache = update_analysis_cache(enabled_configs)
    print("--- 数据分析缓存更新完毕 ---")

    threads = []
    for config in enabled_configs:
        symbol = config['ticker_symbol']
        if symbol in analysis_cache:
            thread = threading.Thread(target=monitor_stock, args=(config, analysis_cache[symbol]))
            threads.append(thread)
            thread.start()

    print(f"--- ETF网格交易机器人已启动，共监控 {len(threads)} 个ETF ---")
    
    for thread in threads:
        thread.join()

if __name__ == "__main__":
    main()