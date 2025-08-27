# -*- coding: utf-8 -*-
"""
news_webgen.py
读取 code/news_data.json，渲染到 F:/creat/pa/page/daily_news.html
并把封面图下载到 F:/creat/pa/page/assets/
用法：
  python news_webgen.py --data code\news_data.json
依赖：requests
"""
import os, re, json, argparse, hashlib
import requests

PAGE_DIR = r"F:/creat/pa/page"
ASSET_DIR = os.path.join(PAGE_DIR, "assets")
os.makedirs(ASSET_DIR, exist_ok=True)

def download_image(url, dest_dir):
    try:
        r = requests.get(url, timeout=30, stream=True)
        r.raise_for_status()
        ct = (r.headers.get("Content-Type") or "").lower()
        ext = ".jpg"
        if "png" in ct: ext = ".png"
        elif "jpeg" in ct: ext = ".jpg"
        elif "webp" in ct: ext = ".webp"
        fn = hashlib.md5(url.encode("utf-8")).hexdigest() + ext
        fp = os.path.join(dest_dir, fn)
        with open(fp, "wb") as f:
            for chunk in r.iter_content(8192): f.write(chunk)
        return "assets/" + fn
    except Exception:
        return None

def _get(d,*path, default=None):
    cur=d or {}
    for k in path:
        if not isinstance(cur, dict) or k not in cur: return default
        cur = cur[k]
    return cur

def build_css(theme):
    pal = _get(theme,"palette", default={}) or {}
    defval = {
        "bg":"#0f172a","surface":"#111827","text":"#e5e7eb",
        "muted":"#9ca3af","brand":"#60a5fa","accent1":"#a78bfa","accent2":"#34d399"
    }
    for k,v in defval.items(): pal[k]=pal.get(k) or v
    radius = _get(theme,"radius", default={}) or {}
    r_card = int(radius.get("card") or 16)
    r_btn = int(radius.get("button") or 12)
    r_chip = int(radius.get("chip") or 10)
    layout = _get(theme,"layout", default={}) or {}
    grid_min = int(layout.get("grid_min") or 280)
    density = (layout.get("density") or "comfortable").lower()
    style = (theme or {}).get("style","glass").lower()
    background = (theme or {}).get("background") or f"linear-gradient(180deg,{pal['bg']},#0b1324)"
    use_covers = bool((theme or {}).get("use_covers", True))
    shadows = _get(theme,"shadows", default={}) or {}
    sh_card = shadows.get("card") or "0 6px 20px rgba(0,0,0,.28)"
    sh_btn  = shadows.get("button") or "0 4px 14px rgba(0,0,0,.22)"
    pad_y = 14 if density=="compact" else 16
    pad_x = 14 if density=="compact" else 16
    if style=="glass":
        card_bg="rgba(255,255,255,.06)"; card_border="1px solid rgba(255,255,255,.10)"; backdrop="backdrop-filter:blur(10px);"
    elif style=="soft":
        card_bg=pal["surface"]; card_border="1px solid rgba(255,255,255,.06)"; backdrop=""
    else:
        card_bg=pal["surface"]; card_border="1px solid rgba(255,255,255,.08)"; backdrop=""
    css = f"""
:root{{--bg:{pal['bg']};--surface:{pal['surface']};--text:{pal['text']};--muted:{pal['muted']};
--brand:{pal['brand']};--accent1:{pal['accent1']};--accent2:{pal['accent2']};
--r-card:{r_card}px;--r-btn:{r_btn}px;--r-chip:{r_chip}px;--sh-card:{sh_card};--sh-btn:{sh_btn};}}
*{{box-sizing:border-box}} html,body{{margin:0;padding:0;background:{background};color:var(--text);
font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial}}
header{{padding:24px 16px;text-align:center;position:sticky;top:0;background:color-mix(in oklab, var(--surface) 70%, transparent);
backdrop-filter:blur(8px);border-bottom:1px solid rgba(255,255,255,.06);z-index:10}}
h1{{margin:0;font-size:26px;letter-spacing:.5px}}
.container{{max-width:1200px;margin:0 auto;padding:18px}}
.intro{{background:color-mix(in oklab, var(--brand) 14%, transparent);border:1px solid color-mix(in oklab, var(--brand) 28%, transparent);
padding:14px 16px;border-radius:12px;margin:16px 0;color:#dbeafe}}
.toolbar{{display:flex;gap:12px;align-items:center;margin:14px 0 6px}}
input[type=search]{{flex:1;padding:10px 12px;border-radius:10px;border:1px solid rgba(255,255,255,.12);
background:color-mix(in oklab, var(--surface) 85%, #000 15%);color:var(--text)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax({grid_min}px,1fr));gap:16px;margin-top:12px}}
.card{{background:{card_bg};{backdrop}border:{card_border};border-radius:var(--r-card);overflow:hidden;box-shadow:var(--sh-card);display:flex;flex-direction:column}}
.cover{{display:block;width:100%;aspect-ratio:16/9;object-fit:cover;background:#0a0f1c}}
.card-body{{padding:{pad_y}px {pad_x}px {pad_y+2}px}}
.card h2{{font-size:18px;margin:0 0 8px;color:#e2e8f0;line-height:1.35}}
.meta{{font-size:12px;color:var(--muted);margin-bottom:8px}}
.summary{{font-size:14px;color:#d1d5db;line-height:1.6}}
.summary ul{{margin:8px 0 0 18px;padding:0}}
a.button{{display:inline-block;margin-top:10px;padding:8px 12px;background:var(--brand);color:#0b1220;text-decoration:none;border-radius:var(--r-btn);font-weight:700;box-shadow:var(--sh-btn)}}
a.button:hover{{transform:translateY(-1px);transition:transform .2s ease}}
footer{{text-align:center;color:var(--muted);padding:22px 0;margin-top:26px;border-top:1px solid rgba(255,255,255,.06)}}
.decor{{position:fixed;inset:auto;pointer-events:none;z-index:0;filter:blur(0)}}
.blob{{border-radius:50%;}}
.ring{{border:2px solid currentColor;border-radius:50%;background:transparent}}
.stripe{{height:2px;width:60vw;max-width:800px}}
"""
    return css, use_covers

def shapes_html(theme):
    def _style(pos):
        if not isinstance(pos, dict): return ""
        return ";".join([f"{k}:{v}" for k,v in pos.items() if v])
    html=[]
    for shp in (theme.get("shapes") or []):
        typ = (shp.get("type") or "blob").lower()
        color = shp.get("color") or "var(--accent1)"
        opacity = shp.get("opacity") or 0.18
        size = shp.get("size") or "600px"
        blur = shp.get("blur")
        pos = _style(shp.get("position") or {})
        extra = f"filter:blur({blur});" if blur else ""
        common = f"style='color:{color};background:{color};opacity:{opacity};width:{size};height:{size};{pos};{extra}'"
        cls = "blob" if typ=="blob" else ("ring" if typ=="ring" else "stripe")
        html.append(f"<div class='decor {cls}' {common}></div>")
    return "\n".join(html)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=str, default=os.path.join("code","news_data.json"))
    args = ap.parse_args()

    with open(args.data, "r", encoding="utf-8") as f:
        data = json.load(f)

    css, use_covers = build_css(data.get("theme") or {})
    deco = shapes_html(data.get("theme") or {})
    today = data.get("date","")
    intro = (data.get("overall_intro") or "").replace("<","&lt;").replace(">","&gt;")

    cards_html=[]
    for a in data.get("articles") or []:
        cover_rel = None
        if use_covers and a.get("cover_url"):
            cover_rel = download_image(a["cover_url"], ASSET_DIR)
        meta = a.get("site","")
        safe_title = (a.get("title") or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
        # 把要点列表从 raw_summary 提取一下
        bullets = []
        for line in (a.get("raw_summary") or "").splitlines():
            line=line.strip()
            if line.startswith("•"):
                bullets.append(line)
        ul = "".join([f"<li>{b[1:].strip()}</li>" for b in bullets]) if bullets else ""
        key = (safe_title + " " + meta).lower()
        cover_tag = f"<img class='cover' src='{cover_rel}' alt='{safe_title}' />" if cover_rel else ""
        card = f"""
<article class="card" data-key="{key}">
  {cover_tag}
  <div class="card-body">
    <h2>{safe_title}</h2>
    <div class="meta">{meta}</div>
    <div class="summary"><ul>{ul}</ul></div>
    <a class="button" href="{a.get('link')}" target="_blank" rel="noopener">阅读原文</a>
  </div>
</article>"""
        cards_html.append(card)

    js = """
function filterCards(ev){
  const q = (ev.value||'').trim().toLowerCase();
  document.querySelectorAll('.card').forEach(c=>{
    const text = c.getAttribute('data-key') || '';
    c.style.display = text.includes(q) ? '' : 'none';
  });
}
"""

    html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>每日新闻简报 - {today}</title>
<style>{css}</style>
<script>{js}</script>
</head>
<body>
{deco}
<header><h1>每日新闻简报 · {today}</h1></header>
<div class="container">
  <div class="toolbar">
    <input type="search" placeholder="输入关键词筛选…" oninput="filterCards(this)" />
  </div>
  <div class="intro">{intro}</div>
  <div class="grid">
    {"".join(cards_html)}
  </div>
  <footer>由 AI 自动生成 · 数据来源网络</footer>
</div>
</body></html>"""

    os.makedirs(PAGE_DIR, exist_ok=True)
    out_html = os.path.join(PAGE_DIR, "daily_news.html")
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[OK] 生成：{out_html}")

if __name__ == "__main__":
    main()
