import yfinance as yf
import time
import json
import csv
from datetime import datetime
from financial_analyzer import update_analysis_cache

# --- 文件路径常量 ---
CONFIG_FILE = 'app_config.json'
TRANSACTIONS_FILE = 'transactions.csv'

# --- 数据读写函数 ---
def read_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"错误: 无法读取或解析 {CONFIG_FILE}")
        return None

def write_config(data):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def append_to_csv(row):
    with open(TRANSACTIONS_FILE, 'a', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(row)

# --- 核心逻辑 ---
def get_stock_info(ticker_symbol):
    try:
        stock = yf.Ticker(ticker_symbol)
        info = stock.info
        price = info.get('regularMarketPrice') or info.get('currentPrice')
        if price is None:
            hist = stock.history(period="2d")
            if not hist.empty:
                price = hist['Close'].iloc[-1]
        
        pe_ratio = info.get('trailingPE')
        dividend_yield = info.get('dividendYield')
        
        return {"price": price, "pe": pe_ratio, "div_yield": dividend_yield}
    except Exception as e:
        print(f"[{datetime.now():%H:%M:%S}] 获取 {ticker_symbol} 价格时出错: {e}")
        return None

def format_value(value, unit="", default_val="N/A"):
    if value is None:
        return default_val
    return f"{value:.2f}{unit}"

def process_user_input(asset_state):
    symbol = asset_state['ticker_symbol']
    
    if asset_state.get('_just_marked_as_buy_done', False):
        print(f"\n--- 检测到 {asset_state['remark']}({symbol}) 买入操作已标记完成 ---")
        try:
            original_trigger_price = asset_state['buy_price_alert']
            actual_buy_price = float(input(f"请输入 {symbol} 的【实际买入价格】: "))
            new_cost_price = float(input(f"请输入 {symbol} 的【新的成本价】: "))
            
            buy_grid = asset_state.get('buy_grid', 0.04)
            asset_state['buy_price_alert'] = actual_buy_price * (1 - buy_grid)
            asset_state['cost_price'] = new_cost_price
            take_profit_line = asset_state.get('take_profit_line', 0.15)
            asset_state['sell_price_alert'] = new_cost_price * (1 + take_profit_line)
            
            append_to_csv([datetime.now().strftime('%Y-%m-%d %H:%M:%S'), symbol, asset_state['remark'], 'BUY', original_trigger_price, actual_buy_price, new_cost_price])
            print(f"信息({symbol}): 交易已记录。")
        except ValueError:
            print("错误: 输入无效。")
        asset_state['is_waiting_for_buy_input'] = False
        del asset_state['_just_marked_as_buy_done']

    elif asset_state.get('_just_marked_as_sell_done', False):
        print(f"\n--- 检测到 {asset_state['remark']}({symbol}) 卖出操作已标记完成 ---")
        try:
            original_trigger_price = asset_state['sell_price_alert']
            actual_sell_price = float(input(f"请输入 {symbol} 的【实际卖出价格】: "))
            new_cost_price = float(input(f"请输入 {symbol} 的【新的成本价】: "))

            sell_grid = asset_state.get('sell_grid', 0.04)
            asset_state['sell_price_alert'] = actual_sell_price * (1 + sell_grid)
            asset_state['cost_price'] = new_cost_price

            append_to_csv([datetime.now().strftime('%Y-%m-%d %H:%M:%S'), symbol, asset_state['remark'], 'SELL', original_trigger_price, actual_sell_price, new_cost_price])
            print(f"信息({symbol}): 交易已记录。")
        except ValueError:
            print("错误: 输入无效。")
        asset_state['is_waiting_for_sell_input'] = False
        del asset_state['_just_marked_as_sell_done']
        
    return asset_state

def monitor_asset(asset_state, analysis_data):
    symbol = asset_state['ticker_symbol']
    remark = asset_state.get('remark', symbol)
    
    stock_info = get_stock_info(symbol)
    if stock_info is None or stock_info.get('price') is None:
        print(f"[{datetime.now():%H:%M:%S}] {remark}({symbol}): 无法获取价格信息。")
        return asset_state

    current_price = stock_info['price']
    current_pe = stock_info.get('pe')
    current_yield = stock_info.get('div_yield')
    price_percentile = analysis_data.get('price_percentile')

    buy_alert = asset_state['buy_price_alert']
    sell_alert = asset_state['sell_price_alert']
    
    log_msg = (f"[{datetime.now():%H:%M:%S}] {remark}({symbol}): "
               f"当前价 {current_price:.2f} | "
               f"10年分位: {format_value(price_percentile, '%')} | "
               f"PE: {format_value(current_pe, '', 'N/A')} | "
               f"股息率: {format_value(current_yield * 100 if current_yield else None, '%', 'N/A')} | "
               f"买: {buy_alert:.2f} | "
               f"卖: {sell_alert:.2f}")
    print(log_msg)

    if current_price <= buy_alert:
        print(f"\n{'!'*15} [买入提醒] {'!'*15}\nETF {remark}({symbol}) 当前价 {current_price:.2f} <= 触发价 {buy_alert:.2f}\n")
        asset_state['is_waiting_for_buy_input'] = True
    elif current_price >= sell_alert:
        cost_price = asset_state['cost_price']
        profit = ((current_price / cost_price) - 1) * 100 if cost_price > 0 else float('inf')
        print(f"\n{'!'*15} [卖出提醒] {'!'*15}\nETF {remark}({symbol}) 当前价 {current_price:.2f} >= 触发价 {sell_alert:.2f} (盈利: {profit:.2f}%)\n")
        asset_state['is_waiting_for_sell_input'] = True
        
    return asset_state

def main():
    print("--- 状态化网格交易助手启动 ---")
    
    print("启动时分析历史数据...")
    initial_config = read_config()
    analysis_cache = {}
    if initial_config and initial_config.get("assets"):
        analysis_cache = update_analysis_cache(initial_config["assets"])
    print("历史数据分析完毕。")

    last_known_wait_states = {}

    while True:
        config = read_config()
        if config is None:
            time.sleep(10)
            continue

        assets = config.get("assets", [])
        config_has_changed = False

        for i, asset in enumerate(assets):
            symbol = asset['ticker_symbol']
            if not asset.get("enabled", False):
                continue

            is_currently_waiting_buy = asset.get('is_waiting_for_buy_input', False)
            is_currently_waiting_sell = asset.get('is_waiting_for_sell_input', False)
            was_previously_waiting_buy = last_known_wait_states.get(symbol, {}).get('buy', False)
            was_previously_waiting_sell = last_known_wait_states.get(symbol, {}).get('sell', False)

            if was_previously_waiting_buy and not is_currently_waiting_buy:
                asset['_just_marked_as_buy_done'] = True
                updated_asset = process_user_input(asset)
                config['assets'][i] = updated_asset
                config_has_changed = True
                last_known_wait_states[symbol] = {'buy': False, 'sell': False}
                continue

            if was_previously_waiting_sell and not is_currently_waiting_sell:
                asset['_just_marked_as_sell_done'] = True
                updated_asset = process_user_input(asset)
                config['assets'][i] = updated_asset
                config_has_changed = True
                last_known_wait_states[symbol] = {'buy': False, 'sell': False}
                continue

            # --- 修正：提供更详细的等待日志 ---
            if is_currently_waiting_buy or is_currently_waiting_sell:
                last_known_wait_states[symbol] = {'buy': is_currently_waiting_buy, 'sell': is_currently_waiting_sell}
                
                if is_currently_waiting_buy:
                    op_type = "买入"
                    trigger_price = asset['buy_price_alert']
                else: # is_currently_waiting_sell
                    op_type = "卖出"
                    trigger_price = asset['sell_price_alert']
                
                print(f"[{datetime.now():%H:%M:%S}] {asset['remark']}({symbol}): 等待【{op_type}】操作完成 (触发价: {trigger_price:.2f})...")
                continue

            asset_analysis_data = analysis_cache.get(symbol, {})
            original_asset_state = asset.copy()
            updated_asset = monitor_asset(asset, asset_analysis_data)
            
            if original_asset_state != updated_asset:
                config['assets'][i] = updated_asset
                config_has_changed = True
            
            last_known_wait_states[symbol] = {
                'buy': updated_asset.get('is_waiting_for_buy_input', False), 
                'sell': updated_asset.get('is_waiting_for_sell_input', False)
            }

        if config_has_changed:
            write_config(config)
            print("--- 状态已更新并保存到文件 ---")
        
        print("\n--- 所有资产检查完毕，等待60秒... ---\n")
        time.sleep(60)

if __name__ == "__main__":
    main()