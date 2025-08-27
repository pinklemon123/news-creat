# -*- coding: utf-8 -*-
"""
每日新闻生成器（OpenAI 版）
用法：
  1) python daily_news_generator.py --source code\result_with_links22.txt
  2) 直接 python daily_news_generator.py   # 未传 --source 时将自动选择 code/ 下最新的 result_with_links*.txt

需求：
  pip install requests beautifulsoup4

注意：
  请在系统环境变量中设置 OPENAI_API_KEY（不要把 key 写入代码）：
    PowerShell:  setx OPENAI_API_KEY "sk-xxxx"
"""

import os
import re
import sys
import json
import hashlib
from datetime import datetime
from urllib.parse import urljoin
import glob
import requests
from bs4 import BeautifulSoup

# ---------------- 配置 ----------------
OPENAI_CHAT_ENDPOINT = "https://api.openai.com/v1/chat/completions"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "你的秘钥")
REQUEST_TIMEOUT = 45
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/123.0 Safari/537.36")

# 输出目录（与你的项目结构一致）
PAGE_DIR = r"F:/creat/pa/page"
ASSET_DIR = os.path.join(PAGE_DIR, "assets")
os.makedirs(ASSET_DIR, exist_ok=True)


# ---------------- OpenAI 请求 ----------------
def make_chat_request(messages, model="gpt-4o-mini", temperature=0.2, max_tokens=1200):
    if not OPENAI_API_KEY:
        print("未检测到 OPENAI_API_KEY 环境变量。请先在系统里设置。")
        return None
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    try:
        resp = requests.post(
            OPENAI_CHAT_ENDPOINT,
            headers=headers,
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[OpenAI] 请求失败: {e}")
        return None


# ---------------- 通用工具 ----------------
def text_len(s: str) -> int:
    return len(re.sub(r"\s+", "", s or ""))


def fetch_html(url: str) -> str:
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        r.raise_for_status()
        r.encoding = r.apparent_encoding or "utf-8"
        return r.text
    except Exception as e:
        print(f"[抓取失败] {url}: {e}")
        return ""


def extract_title(soup: BeautifulSoup, fallback: str = "") -> str:
    meta = soup.select_one('meta[property="og:title"]') or soup.select_one('meta[name="og:title"]')
    if meta and meta.get("content"):
        return meta["content"].strip()
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    return (fallback or "未命名标题").strip()


CANDIDATE_SELECTORS = [
    "article",
    "article .content",
    ".article",
    ".article-content",
    ".post",
    ".post-content",
    ".entry-content",
    "#content",
    ".content",
    ".main",
    "#main",
    ".news",
]


def _clean_node(node):
    for bad in node.select("script,style,noscript,header,footer,nav,aside,form"):
        bad.decompose()
    return node


def extract_main_text_and_images(soup: BeautifulSoup, base_url: str):
    best_node, best_len = None, 0
    for sel in CANDIDATE_SELECTORS:
        for n in soup.select(sel):
            node = _clean_node(n)
            text = " ".join([p.get_text(" ", strip=True) for p in node.find_all("p")]) or node.get_text(" ", strip=True)
            L = text_len(text)
            if L > best_len:
                best_len, best_node = L, node

    if best_node is None:
        paragraphs = soup.find_all("p")
        text = " ".join([p.get_text(" ", strip=True) for p in paragraphs])
        main_text = re.sub(r"\s+", " ", text).strip()
        imgs = soup.find_all("img")
    else:
        text = " ".join([p.get_text(" ", strip=True) for p in best_node.find_all("p")]) or best_node.get_text(" ", strip=True)
        main_text = re.sub(r"\s+", " ", text).strip()
        imgs = best_node.find_all("img")

    cover = None
    og = soup.select_one('meta[property="og:image"]') or soup.select_one('meta[name="og:image"]')
    if og and og.get("content"):
        cover = og["content"].strip()

    if not cover:
        for im in imgs:
            src = im.get("src") or im.get("data-src") or im.get("data-original")
            if not src:
                continue
            full = urljoin(base_url, src)
            if any(ext in full.lower() for ext in [".svg", ".ico", ".gif"]):
                continue
            cover = full
            break

    return main_text, cover


def download_image(url: str, dest_dir: str):
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30, stream=True)
        r.raise_for_status()
        ct = (r.headers.get("Content-Type") or "").lower()
        ext = ".jpg"
        if "png" in ct:
            ext = ".png"
        elif "jpeg" in ct:
            ext = ".jpg"
        elif "webp" in ct:
            ext = ".webp"
        fn = hashlib.md5(url.encode("utf-8")).hexdigest() + ext
        fp = os.path.join(dest_dir, fn)
        with open(fp, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        return fn
    except Exception as e:
        print(f"[下载图片失败] {url}: {e}")
        return None


# ---------------- 读取爬虫结果 ----------------
def load_links_from_source(source_file: str):
    """
    解析 pa.py 产出的文本文件：
      文本: XXX
      URL: https://...
      ---
    返回 [(text, url), ...]，并按 URL 去重。
    """
    pairs, text, url = [], None, None
    with open(source_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("文本:"):
                text = line.replace("文本:", "", 1).strip()
            elif line.startswith("URL:"):
                url = line.replace("URL:", "", 1).strip()
            elif line == "---":
                if text and url:
                    pairs.append((text, url))
                text, url = None, None

    seen, uniq = set(), []
    for t, u in pairs:
        if u not in seen:
            uniq.append((t, u))
            seen.add(u)
    return uniq


def autodetect_latest_source():
    cand = sorted(glob.glob(os.path.join("code", "result_with_links*.txt")),
                  key=lambda p: os.path.getmtime(p),
                  reverse=True)
    return cand[0] if cand else None


# ---------------- AI：摘要、排序、导语 ----------------
def summarize_article(title: str, url: str, text: str, max_chars: int = 8000):
    """
    生成结构化中文摘要：高质量标题 + 3~5 要点 + 关键词
    仅基于正文，不得杜撰。
    """
    text = text[:max_chars]
    prompt = f"""
你是资深中文新闻编辑。仅基于我提供的【正文】，输出结构化摘要，禁止发挥与杜撰。
输出格式：
第一行：不超过28字的高质量中文标题（不要加引号）
接着：3~5条要点，每条以“• ”开头，覆盖：谁/做了什么/何时何地/为什么重要/影响
最后一行：关键词：A, B, C（2~4个中文关键词）

【页面标题】{title}
【来源链接】{url}
【正文】
{text}
""".strip()

    messages = [
        {"role": "system", "content": "你是严谨、客观的中文新闻编辑。"},
        {"role": "user", "content": prompt},
    ]
    return make_chat_request(messages, max_tokens=700)


def pick_top_articles(candidates, k=8):
    """
    candidates: [{'title':..., 'lead':...}, ...]
    让模型输出 JSON 数组的索引（如 [3,0,2]），按重要性降序。
    """
    items = "\n".join([f"[{i}] {c['title']} —— {c['lead']}" for i, c in enumerate(candidates)])
    prompt = f"""
以下是候选新闻（[]内为索引）。请选出最重要的 {k} 条，按重要性降序，仅输出一个 JSON 数组（例如：[3,0,2]），不要输出其它文字。
选择标准：影响范围、公共价值、时效性、信息密度。
{items}
""".strip()
    out = make_chat_request(
        [{"role": "system", "content": "你是新闻价值判断助手。"},
         {"role": "user", "content": prompt}],
        max_tokens=200,
    )
    if not out:
        # 兜底：按正文长度排序时会处理，这里先全部索引
        return list(range(min(k, len(candidates))))
    m = re.search(r"\[.*\]", out, re.S)
    if not m:
        return list(range(min(k, len(candidates))))
    try:
        arr = json.loads(m.group(0))
        arr = [i for i in arr if isinstance(i, int) and 0 <= i < len(candidates)]
        return arr[:k] if arr else list(range(min(k, len(candidates))))
    except Exception:
        return list(range(min(k, len(candidates))))


def generate_overall_intro(news_titles):
    titles_text = "\n".join(news_titles[:12])
    prompt = f"以下是今天筛选出的主要新闻标题：\n{titles_text}\n请写一段60~100字的总导语，客观、凝练、有概括力。不要使用提问句。语言为中文。"
    return make_chat_request(
        [{"role": "system", "content": "你是新闻导语撰写助手。"},
         {"role": "user", "content": prompt}],
        max_tokens=180,
    ) or ""


# ---------------- HTML 生成 ----------------
def generate_html(cards, overall_intro, output_file):
    """
    cards: [{title, summary_html, summary_text, link, cover_rel}]
    """
    today = datetime.now().strftime("%Y-%m-%d")
    css = """
:root{
  --bg:#0f172a; --panel:#111827; --fg:#e5e7eb;
  --muted:#9ca3af; --brand:#60a5fa; --card:#0b1220;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:linear-gradient(180deg,#0b1220,#0f172a);color:var(--fg);font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial}
header{padding:24px 16px;text-align:center;position:sticky;top:0;background:rgba(11,18,32,.7);backdrop-filter:blur(8px);border-bottom:1px solid rgba(255,255,255,.06)}
h1{margin:0;font-size:26px;letter-spacing:.5px}
.container{max-width:1200px;margin:0 auto;padding:18px}
.intro{background:rgba(96,165,250,.1);border:1px solid rgba(96,165,250,.25);padding:14px 16px;border-radius:12px;margin:16px 0;color:#dbeafe}
.toolbar{display:flex;gap:12px;align-items:center;margin:14px 0 6px}
input[type=search]{flex:1;padding:10px 12px;border-radius:10px;border:1px solid rgba(255,255,255,.12);background:#0b1324;color:var(--fg)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px;margin-top:12px}
.card{background:var(--card);border:1px solid rgba(255,255,255,.06);border-radius:16px;overflow:hidden;box-shadow:0 6px 20px rgba(0,0,0,.3);display:flex;flex-direction:column}
.cover{display:block;width:100%;aspect-ratio:16/9;object-fit:cover;background:#0a0f1c}
.card-body{padding:14px 14px 16px}
.card h2{font-size:18px;margin:0 0 8px;color:#e2e8f0;line-height:1.35}
.meta{font-size:12px;color:var(--muted);margin-bottom:8px}
.summary{font-size:14px;color:#d1d5db;line-height:1.6}
.summary ul{margin:8px 0 0 18px;padding:0}
a.button{display:inline-block;margin-top:10px;padding:8px 12px;background:var(--brand);color:#0b1220;text-decoration:none;border-radius:10px;font-weight:600}
footer{text-align:center;color:var(--muted);padding:22px 0;margin-top:26px;border-top:1px solid rgba(255,255,255,.06)}
"""
    js = """
function filterCards(ev){
  const q = (ev.value||'').trim().toLowerCase();
  document.querySelectorAll('.card').forEach(c=>{
    const text = c.getAttribute('data-key') || '';
    c.style.display = text.includes(q) ? '' : 'none';
  });
}
"""

    html_parts = [
        "<!DOCTYPE html>",
        '<html lang="zh"><head>',
        '<meta charset="utf-8" />',
        '<meta name="viewport" content="width=device-width, initial-scale=1" />',
        f"<title>每日新闻简报 - {today}</title>",
        "<style>" + css + "</style>",
        "<script>" + js + "</script>",
        "</head><body>",
        f"<header><h1>每日新闻简报 · {today}</h1></header>",
        '<div class="container">',
        '<div class="toolbar"><input type="search" placeholder="输入关键词筛选…" oninput="filterCards(this)" /></div>',
        f'<div class="intro">{overall_intro or ""}</div>',
        '<div class="grid">',
    ]

    def esc(s: str) -> str:
        return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    for c in cards:
        cover_tag = f'<img class="cover" src="assets/{esc(c.get("cover_rel",""))}" alt="cover" />' if c.get("cover_rel") else ""
        key = (c.get("title", "") + " " + (c.get("summary_text", "") or "")).lower().replace('"', "'")
        html_parts += [
            f'<article class="card" data-key="{esc(key)}">',
            cover_tag,
            '<div class="card-body">',
            f"<h2>{esc(c['title'])}</h2>",
            f'<div class="meta"><a href="{esc(c["link"])}" target="_blank" rel="noopener">来源链接</a></div>',
            f'<div class="summary">{c["summary_html"]}</div>',
            f'<a class="button" href="{esc(c["link"])}" target="_blank" rel="noopener">阅读全文</a>',
            "</div></article>",
        ]

    html_parts += [
        "</div></div>",
        "<footer>由 OpenAI 驱动 · 自动摘要与页面生成</footer>",
        "</body></html>",
    ]

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(html_parts))
    print(f"✅ 页面已生成: {output_file}")


# ---------------- 主流程 ----------------
def main():
    # 1) 定位来源文件
    source_file = None
    if len(sys.argv) >= 3 and sys.argv[1] == "--source":
        source_file = sys.argv[2]
    else:
        source_file = autodetect_latest_source()

    if not source_file or not os.path.exists(source_file):
        print("找不到爬虫输出文件。请传入 --source <path> 或确保 code/ 下存在 result_with_links*.txt")
        sys.exit(1)

    print(f"[读取] {source_file}")
    pairs = load_links_from_source(source_file)
    if not pairs:
        print("来源文件未解析到任何链接/文本。")
        sys.exit(1)

    # 2) 抓每篇文章正文 + 封面
    articles = []   # [{'url','title','text','cover'}]
    for (txt, url) in pairs:
        html = fetch_html(url)
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        title = extract_title(soup, fallback=txt)
        text, cover = extract_main_text_and_images(soup, url)
        if text_len(text) < 150:   # 太短的正文通常无价值
            continue
        articles.append({"url": url, "title": title, "text": text, "cover": cover})

    if not articles:
        print("没有可用的文章。")
        sys.exit(0)

    # 3) 初步摘要/lead 用于排序参考
    candidates = []
    for a in articles:
        lead = (a["text"][:240] + "…") if len(a["text"]) > 240 else a["text"]
        candidates.append({"title": a["title"], "lead": lead})

    order = pick_top_articles(candidates, k=min(10, len(candidates)))
    # 若模型输出不靠谱，可改为按正文长度排序：order = sorted(range(len(candidates)), key=lambda i: -text_len(articles[i]["text"]))[:min(10,len(candidates))]

    # 4) 逐篇高质量摘要 + 下载封面
    cards = []
    for idx in order:
        a = articles[idx]
        summary = summarize_article(a["title"], a["url"], a["text"]) or ""
        lines = [ln.strip() for ln in summary.splitlines() if ln.strip()]

        nice_title = a["title"]
        if lines and (len(lines[0]) <= 28) and ("•" not in lines[0]) and ("关键词" not in lines[0]):
            nice_title = lines[0]
            lines = lines[1:]

        bullets = [ln[1:].strip() if ln.startswith("•") else ln for ln in lines if ln.startswith("•")]
        other = [ln for ln in lines if (not ln.startswith("•")) and (not ln.startswith("关键词"))]
        kw = ""
        for ln in lines:
            if ln.startswith("关键词"):
                kw = ln

        if bullets:
            bullet_html = "<ul>" + "".join([f"<li>{b}</li>" for b in bullets]) + "</ul>"
        else:
            bullet_html = f"<p>{' '.join(other)}</p>" if other else ""

        summary_html = bullet_html + (f"<p style='color:#9ca3af;font-size:12px;margin-top:6px'>{kw}</p>" if kw else "")
        cover_rel = None
        if a.get("cover"):
            fn = download_image(a["cover"], ASSET_DIR)
            if fn:
                cover_rel = fn

        cards.append({
            "title": nice_title,
            "summary_html": summary_html or "<p>（暂无摘要）</p>",
            "summary_text": summary,
            "link": a["url"],
            "cover_rel": cover_rel,
        })

    # 5) 总导语 + 写 HTML
    overall_intro = generate_overall_intro([c["title"] for c in cards]) or ""
    out_file = os.path.join(PAGE_DIR, "daily_news.html")
    generate_html(cards, overall_intro, out_file)


if __name__ == "__main__":
    main()

# ----------------  END  ----------------