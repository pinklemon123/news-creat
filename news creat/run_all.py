# -*- coding: utf-8 -*-
"""
run_all.py
一键流水线：
  [1/3] 运行爬虫 pa.py
  [2/3] AI 分析 news_analyzer.py  ->  code/news_data.json
  [3/3] 网页生成 news_webgen.py   ->  F:/creat/pa/page/daily_news.html

你可以在这里直接声明 API Key（如不想在系统环境里设）：
  os.environ["OPENAI_API_KEY"] = "YOUR_OPENAI_KEY"
  os.environ["DEEPSEEK_API_KEY"] = "YOUR_DEEPSEEK_KEY"
优先级：环境变量 > 此处硬编码。
"""
import subprocess, os, sys

# ====== 可选：在此放你的 Key（占位符，建议改成环境变量）======
os.environ["OPENAI_API_KEY"] = "………………………………"
# os.environ["DEEPSEEK_API_KEY"] = "YOUR_DEEPSEEK_KEY"
# ======================================================

base_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(base_dir)

# 固定读取的爬虫结果文件（不要改）
FIXED_SOURCE = r"F:\creat\pa\code\result_with_links22.txt"

print("[1/3] 正在运行爬虫程序...")
subprocess.run([sys.executable, "pa.py"], check=True)

if not os.path.exists(FIXED_SOURCE):
    raise FileNotFoundError(f"未找到固定爬虫输出：{FIXED_SOURCE}。请确认 pa.py 写出的文件路径一致。")

print(f"使用固定文件：{FIXED_SOURCE}")

# 你可以在这里切换 provider: openai | deepseek
PROVIDER = os.environ.get("NEWS_PROVIDER", "openai").lower()

print("[2/3] 正在分析与生成数据 JSON...")
subprocess.run([
    sys.executable, "news_analyzer.py",
    "--source", FIXED_SOURCE,
    "--out", os.path.join("code","news_data.json"),
    "--provider", PROVIDER
], check=True)

print("[3/3] 正在生成每日新闻 HTML...")
subprocess.run([sys.executable, "news_webgen.py", "--data", os.path.join("code","news_data.json")], check=True)

print("全部完成！请到 F:/creat/pa/page 查看 daily_news.html 与 assets/ 封面图。")




