# -*- coding: utf-8 -*-
"""
news_analyzer.py
读取爬虫输出(result_with_links*.txt)，抓正文/首图，AI 生成：
- 每篇结构化摘要（标题 + 3~5 要点 + 关键词）
- 当日总导语
- 当日主题（配色/形状/装饰）
输出：code/news_data.json
用法：
  python news_analyzer.py --source code\result_with_linksXX.txt --out code\news_data.json --provider openai
  # provider: openai | deepseek（默认 openai）
依赖：requests beautifulsoup4
"""
import os, re, json, glob, argparse, hashlib
from datetime import datetime
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/123.0 Safari/537.36")
REQUEST_TIMEOUT = 45

def autodetect_latest_source():
    cand = sorted(glob.glob(os.path.join("code","result_with_links*.txt")),
                  key=lambda p: os.path.getmtime(p), reverse=True)
    return cand[0] if cand else None

def load_pairs(path):
    pairs, text, url = [], None, None
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s.startswith("文本:"):
                text = s.replace("文本:", "", 1).strip()
            elif s.startswith("URL:"):
                url = s.replace("URL:", "", 1).strip()
            elif s == "---":
                if text and url:
                    pairs.append((text, url))
                text, url = None, None
    # 去重
    seen, uniq = set(), []
    for t,u in pairs:
        if u not in seen:
            uniq.append((t,u)); seen.add(u)
    return uniq

def fetch_html(url):
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        r.raise_for_status()
        r.encoding = r.apparent_encoding or "utf-8"
        return r.text
    except Exception as e:
        print(f"[抓取失败] {url}: {e}")
        return ""

def extract_title(soup, fallback=""):
    og = soup.select_one('meta[property="og:title"]') or soup.select_one('meta[name="og:title"]')
    if og and og.get("content"):
        return og["content"].strip()
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    return fallback or "未命名标题"

CANDIDATE = [
    "article",".article",".post",".entry-content",".article-content",
    "#content",".content","#main",".main",".news"
]

def _clean(node):
    for bad in node.select("script,style,noscript,header,footer,nav,aside,form"):
        bad.decompose()
    return node

def text_len(s): 
    import re
    return len(re.sub(r"\s+","", s or ""))

def extract_main_and_cover(soup, base_url):
    best, best_len = None, 0
    for sel in CANDIDATE:
        for n in soup.select(sel):
            node = _clean(n)
            text = " ".join([p.get_text(" ", strip=True) for p in node.find_all("p")]) or node.get_text(" ", strip=True)
            L = text_len(text)
            if L > best_len:
                best, best_len = node, L
    if best is None:
        text = " ".join([p.get_text(" ", strip=True) for p in soup.find_all("p")])
        imgs = soup.find_all("img")
    else:
        text = " ".join([p.get_text(" ", strip=True) for p in best.find_all("p")]) or best.get_text(" ", strip=True)
        imgs = best.find_all("img")
    main = re.sub(r"\s+"," ", text).strip()

    cover = None
    og = soup.select_one('meta[property="og:image"]') or soup.select_one('meta[name="og:image"]')
    if og and og.get("content"):
        cover = urljoin(base_url, og["content"].strip())
    if not cover:
        for im in imgs:
            src = im.get("src") or im.get("data-src") or im.get("data-original")
            if not src: 
                continue
            full = urljoin(base_url, src)
            if any(ext in full.lower() for ext in [".svg",".ico",".gif"]):
                continue
            cover = full; break
    return main, cover

# ---------------- AI 接口（OpenAI 或 DeepSeek，采用 Chat Completions 兼容格式） ----------------
def chat_complete(messages, provider="openai", model=None, temperature=0.5, max_tokens=800):
    if provider == "deepseek":
        endpoint = "https://api.deepseek.com/v1/chat/completions"
        api_key = os.getenv("DEEPSEEK_API_KEY")
        default_model = "deepseek-chat"
    else:
        endpoint = "https://api.openai.com/v1/chat/completions"
        api_key = os.getenv("OPENAI_API_KEY")
        default_model = "gpt-4o-mini"
    if not api_key:
        raise RuntimeError(f"未检测到 {'DEEPSEEK_API_KEY' if provider=='deepseek' else 'OPENAI_API_KEY'}")
    headers = {"Content-Type":"application/json","Authorization":f"Bearer {api_key}"}
    payload = {"model": model or default_model, "messages": messages,
               "temperature": temperature, "max_tokens": max_tokens}
    r = requests.post(endpoint, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

def summarize_article(title, url, text, provider):
    text = text[:8000]
    prompt = f"""
你是资深中文新闻编辑。仅基于我提供的【正文】，输出结构化摘要，禁止杜撰。
输出格式：
第一行：不超过28字的高质量中文标题（不要引号）
随后：3~5条要点，每条以“• ”开头，覆盖：谁/做了什么/何时何地/为何重要/影响
最后一行：关键词：A, B, C（2~4 个）
【页面标题】{title}
【来源链接】{url}
【正文】{text}
""".strip()
    return chat_complete(
        [{"role":"system","content":"你是严谨、客观的中文新闻编辑。"},
         {"role":"user","content":prompt}],
        provider=provider, max_tokens=700)

def pick_top(candidates, k, provider):
    listing = "\n".join([f"[{i}] {c['title']} —— {c['lead']}" for i,c in enumerate(candidates)])
    prompt = f"""以下是候选新闻（[]内为索引）。请选出最重要的 {k} 条，按重要性降序，仅输出 JSON 数组（例：[3,0,2]），不要其它文字。
选择标准：影响范围、公共价值、时效性、信息密度。
{listing}"""
    out = chat_complete(
        [{"role":"system","content":"你是新闻价值判断助手。"},
         {"role":"user","content":prompt}],
        provider=provider, max_tokens=200, temperature=0.2)
    import json, re
    m = re.search(r"\[.*\]", out, re.S)
    if not m: 
        return list(range(min(k,len(candidates))))
    try:
        arr = json.loads(m.group(0))
        arr = [i for i in arr if isinstance(i,int) and 0<=i<len(candidates)]
        return arr[:k] if arr else list(range(min(k,len(candidates))))
    except:
        return list(range(min(k,len(candidates))))

def overall_intro(titles, provider):
    prompt = "以下是今天筛选出的主要新闻标题：\n" + "\n".join(titles[:12]) + "\n请写一段60~100字总导语，客观凝练。"
    return chat_complete(
        [{"role":"system","content":"你是新闻导语撰写助手。"},
         {"role":"user","content":prompt}],
        provider=provider, max_tokens=160, temperature=0.5)

def _extract_json_block(s):
    if not s: return None
    stack,start=0,-1
    for i,ch in enumerate(s):
        if ch=='{':
            if stack==0: start=i
            stack+=1
        elif ch=='}':
            stack-=1
            if stack==0 and start>=0:
                import json
                try: return json.loads(s[start:i+1])
                except: return None
    import re, json
    m = re.search(r"\{[\s\S]*\}", s)
    if m:
        try: return json.loads(m.group(0))
        except: return None
    return None

def design_theme(titles, provider):
    sample = "\n".join(f"- {t}" for t in titles[:12])
    prompt = f"""
请基于这些新闻标题，输出一个紧凑 JSON 的网页主题（配色、圆角、阴影、背景渐变、布局密度、是否使用封面图、装饰图形数组），
字段尽量参考：
{{
  "name":"示例",
  "palette":{{"bg":"#0f172a","surface":"#111827","text":"#e5e7eb","muted":"#94a3b8","brand":"#60a5fa","accent1":"#a78bfa","accent2":"#34d399"}},
  "radius":{{"card":16,"button":12,"chip":10}},
  "layout":{{"grid_min":280,"density":"comfortable"}},
  "style":"glass",
  "background":"linear-gradient(180deg,#0b1220,#0f172a)",
  "use_covers":true,
  "shadows":{{"card":"0 6px 20px rgba(0,0,0,.28)","button":"0 4px 14px rgba(0,0,0,.22)"}},
  "shapes":[{{"type":"blob","color":"#60a5fa","opacity":0.18,"size":"680px","blur":"30px","position":{{"top":"-120px","right":"-120px"}}}}]
}}
只输出 JSON，不要解释。
标题：
{sample}
"""
    out = chat_complete(
        [{"role":"system","content":"你是优秀的 UI/UX 设计师，强调对比度与可读性。"},
         {"role":"user","content":prompt}],
        provider=provider, max_tokens=500, temperature=0.9)
    return _extract_json_block(out)

def main():
    ap = argparse.ArgumentParser()
    # ap.add_argument("--source", type=str, default=None)
    ap.add_argument("--source", type=str, default=r"F:\creat\pa\code\result_with_links22.txt")
    ap.add_argument("--out", type=str, default=os.path.join("code","news_data.json"))
    ap.add_argument("--provider", type=str, default="openai", choices=["openai","deepseek"])
    ap.add_argument("--limit", type=int, default=18)
    args = ap.parse_args()

    source = args.source or autodetect_latest_source()
    if not source or not os.path.exists(source):
        raise FileNotFoundError("未找到爬虫结果（code/result_with_links*.txt）")

    pairs = load_pairs(source)[:args.limit]
    articles_raw = []
    for anchor_text, url in pairs:
        html = fetch_html(url)
        if not html: 
            continue
        soup = BeautifulSoup(html, "html.parser")
        title = extract_title(soup, fallback=anchor_text)
        body, cover = extract_main_and_cover(soup, url)
        if len(body) < 120:   # 过短的正文跳过
            continue
        try:
            summ = summarize_article(title, url, body, provider=args.provider)
        except Exception as e:
            print("[摘要失败]", e); 
            summ = None
        lead = (summ or "").splitlines()[0].strip() if summ else title
        site = urlparse(url).netloc
        articles_raw.append({
            "title": title, "link": url, "site": site,
            "cover_url": cover, "raw_summary": summ or "",
            "lead": lead
        })

    if not articles_raw:
        raise RuntimeError("抓不到有效正文，或全部摘要失败。")

    # 选题 Top K
    k = min(10, len(articles_raw))
    idxs = pick_top(articles_raw, k, provider=args.provider)
    selected = [articles_raw[i] for i in idxs]
    titles = [a["title"] for a in selected]

    # 总导语 + 主题
    try:
        intro = overall_intro(titles, provider=args.provider)
    except Exception as e:
        print("[导语失败]", e); intro = ""
    try:
        theme = design_theme(titles, provider=args.provider) or {}
    except Exception as e:
        print("[主题失败]", e); theme = {}

    out = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "overall_intro": intro or "",
        "theme": theme or {},
        "articles": selected
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[OK] 写出：{args.out}")

if __name__ == "__main__":
    main()


    # ap.add_argument("--source", type=str, default=None)
