import os
import akshare as ak
import requests
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime

# 环境变量配置
SEND_KEY = os.getenv("SEND_KEY")
STOCK_POOL = ["601868", "000001", "002594"]  # 你关注的股票池

# 微信推送
def push_wechat(title, content):
    if not SEND_KEY:
        print("未配置SEND_KEY，跳过推送")
        return
    url = f"https://sctapi.ftqq.com/{SEND_KEY}.send"
    data = {"title": title, "desp": content}
    try:
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        print(f"推送失败: {e}")

# 1. 盘口信号监控（对应你的主力攻略）
def monitor_stock(stock_code):
    try:
        # 获取分时+资金流数据
        df_min = ak.stock_zh_a_minute(symbol=stock_code, period="1")
        df_flow = ak.stock_individual_fund_flow(stock=stock_code, market="a")
        if df_min.empty or df_flow.empty:
            return []
        
        last = df_min.iloc[-1]
        price = last["close"]
        chg = (price - df_min.iloc[0]["open"]) / df_min.iloc[0]["open"] * 100
        main_flow = df_flow.iloc[0]["主力资金净流入"]
        inner = df_flow.iloc[0]["内盘"]
        outer = df_flow.iloc[0]["外盘"]
        vol_ratio = last["volume"] / df_min["volume"].tail(10).mean() if df_min["volume"].tail(10).mean() > 0 else 1

        signals = []
        # 诱多：涨+主力流出
        if chg > 1 and main_flow < -5000:
            signals.append(f"⚠️ 诱多：{stock_code} 涨{chg:.1f}%，主力流出{main_flow:.0f}万")
        # 洗盘：跌+主力流入
        if chg < -1 and main_flow > 5000:
            signals.append(f"💡 洗盘：{stock_code} 跌{chg:.1f}%，主力流入{main_flow:.0f}万")
        # 卖方强势：内盘>外盘
        if inner > outer * 1.2:
            signals.append(f"📉 卖方强势：{stock_code} 内盘({inner}) > 外盘({outer})")
        # 主力跑路：高位放量+长上影
        recent_rise = (df_min["close"].iloc[-1] / df_min["close"].iloc[0] - 1) * 100
        if recent_rise > 30 and vol_ratio > 2 and (last["high"] - price) > (price - last["low"]):
            signals.append(f"🚨 主力跑路：{stock_code} 高位放量长上影")
        return signals
    except Exception as e:
        print(f"监控{stock_code}失败: {e}")
        return []

# 2. 五维看股选股（对应你的攻略）
def five_dimension_select():
    selected = []
    for code in STOCK_POOL:
        try:
            # 维度1：热点（板块涨幅）
            df_board = ak.stock_board_cons(stock=code)
            board_rise = df_board.iloc[-1]["涨跌幅"] if not df_board.empty else 0
            # 维度2：要事（公告/新闻，简化为近30日是否有公告）
            df_ann = ak.stock_announcement(stock=code)
            has_event = not df_ann.empty and (datetime.now() - pd.to_datetime(df_ann.iloc[0]["公告日期"])).days <= 30
            # 维度3：资金（主力净流入）
            df_flow = ak.stock_individual_fund_flow(stock=code, market="a")
            main_flow = df_flow.iloc[0]["主力资金净流入"] if not df_flow.empty else 0
            # 维度4：深度（盘口稳定，波动小）
            df_min = ak.stock_zh_a_minute(symbol=code, period="1")
            volatility = df_min["close"].pct_change().std() if not df_min.empty else 1
            # 维度5：财务（PE<30，盈利）
            df_fin = ak.stock_financial_abstract(stock=code)
            pe = df_fin.iloc[-1]["市盈率"] if not df_fin.empty else 100
            net_profit = df_fin.iloc[-1]["净利润"] if not df_fin.empty else -1

            # 筛选条件
            if board_rise > 2 and has_event and main_flow > 0 and volatility < 0.02 and pe < 30 and net_profit > 0:
                selected.append(code)
        except Exception as e:
            print(f"选股{code}失败: {e}")
    return selected

# 3. 策略回测（简化版：诱多信号后次日卖出）
def backtest_strategy(stock_code):
    try:
        df = ak.stock_zh_a_daily(symbol=stock_code, adjust="hfq")
        df["chg"] = df["close"].pct_change()
        df["main_flow"] = ak.stock_individual_fund_flow(stock=stock_code, market="a")["主力资金净流入"]
        # 诱多信号：涨>2% + 主力流出>5000万
        df["signal"] = ((df["chg"] > 0.02) & (df["main_flow"] < -5000)).astype(int)
        # 回测：信号次日卖出
        df["return"] = df["close"].shift(-1) / df["close"] - 1
        strategy_return = df[df["signal"] == 1]["return"].mean()
        max_drawdown = (df["close"] / df["close"].cummax() - 1).min()
        return f"回测{stock_code}：平均收益{strategy_return:.2%}，最大回撤{max_drawdown:.2%}"
    except Exception as e:
        return f"回测{stock_code}失败: {e}"

# 4. 生成可视化报告
def generate_report(stock_code, signals):
    try:
        df_min = ak.stock_zh_a_minute(symbol=stock_code, period="1")
        plt.figure(figsize=(10, 5))
        plt.plot(df_min["time"], df_min["close"], label="价格")
        plt.title(f"{stock_code} 分时走势与信号")
        plt.xticks(rotation=45)
        plt.legend()
        plt.tight_layout()
        plt.savefig(f"{stock_code}_report.png")
        plt.close()
        return f"{stock_code}_report.png"
    except Exception as e:
        print(f"生成报告失败: {e}")
        return None

# 主函数
def main():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"=== 运行时间: {now} ===")

    # 1. 监控所有股票池
    all_signals = []
    for code in STOCK_POOL:
        signals = monitor_stock(code)
        all_signals.extend(signals)
        if signals:
            generate_report(code, signals)

    # 2. 每天18点执行选股+回测
    if now.endswith("18:00"):
        selected = five_dimension_select()
        backtest_results = [backtest_strategy(code) for code in STOCK_POOL]
        content = f"📊 每日选股报告（{now}）\n入选股票：{selected}\n\n回测结果：\n" + "\n".join(backtest_results)
        push_wechat("每日选股&回测报告", content)

    # 3. 有信号就推送微信
    if all_signals:
        content = "\n".join(all_signals)
        push_wechat("🚨 主力盘口预警", content)
        print(f"推送预警: {content}")
    else:
        print("暂无预警信号")

if __name__ == "__main__":
    main()
