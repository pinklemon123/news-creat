import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.common.exceptions import WebDriverException
import os
from urllib.parse import urlparse, urljoin

# --- 配置部分 ---
options = EdgeOptions()
options.add_argument('--headless')
options.add_argument('--disable-gpu')
options.add_argument('log-level=3') # 禁用不必要的日志输出

# 请确保这里的路径是正确的
driver_path = r"C:\Users\pinkl\Desktop\新建文件夹\edgedriver_win64\msedgedriver.exe"
service = EdgeService(executable_path=driver_path)

# --- 文件路径配置 ---
output_dir = r"F:\creat\pa\code"
output_file = os.path.join(output_dir, "result_with_links22.txt")
os.makedirs(output_dir, exist_ok=True)

# --- 目标网站设置 ---
# 您可以在这里更改您想要爬取的网站，例如 "https://www.stnn.cc/ent" 或 "https://www.gov.cn/","https://www.chinawriter.com.cn/403990/index.html","https://www.chinawriter.com.cn/404057/index.html"
url_to_crawl = "https://www.bbc.com/zhongwen/simp"

try:
    print("正在启动虚拟浏览器...")
    driver = webdriver.Edge(service=service, options=options)
    print("浏览器启动成功。")

    # --- 爬取部分 ---
    print(f"正在访问：{url_to_crawl}")
    driver.get(url_to_crawl)

    print("等待10秒钟以确保页面内容加载...")
    time.sleep(10)

    # --- 提取并写入文件 ---
    with open(output_file, 'w', encoding='utf-8') as f:
        print(f"准备将网页所有链接信息写入文件: {output_file}")
        title = driver.title
        f.write(f"网页标题：{title}\n\n")
        f.write("--- 网页中所有可见链接信息 ---\n")

        # 抓取页面上所有可见的链接
        link_elements = driver.find_elements(By.TAG_NAME, 'a')
        
        unique_links = {}
        base_domain = urlparse(url_to_crawl).netloc
        
        # 定义通用的链接过滤规则
        common_exclude_keywords = ['登录', '注册', '版权', '隐私', 'English', '留言', '投稿', '更多']
        
        for link_element in link_elements:
            try:
                link_text = link_element.text.strip()
                link_href = link_element.get_attribute('href')
                
                if not link_href:
                    continue

                full_url = urljoin(url_to_crawl, link_href)
                parsed_url = urlparse(full_url)
                
                # 通用过滤条件
                is_valid_news_link = (
                    # 链接文本长度适中，避免抓取短的导航链接
                    len(link_text) > 15 and
                    # 链接在当前域名下
                    parsed_url.netloc == base_domain and
                    # 排除包含常见非新闻关键词的链接
                    not any(keyword in link_text for keyword in common_exclude_keywords) and
                    # URL 中通常包含多级目录，并且不以域名或栏目名称结尾
                    parsed_url.path.count('/') > 2 and
                    # 排除图片、视频等文件链接
                    not any(full_url.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.mp4', '.avi', '.mov']) and
                    # 排除以 # 或 ? 开头的内部锚点或参数链接
                    '#' not in full_url and '?' not in full_url and
                    # 排除重复链接
                    full_url not in unique_links
                )

                if is_valid_news_link:
                    unique_links[full_url] = link_text
                    print(f"找到潜在的新闻链接: {link_text} -> {full_url}")

            except Exception as e:
                # 发生错误时继续处理下一个链接
                continue
        
        if not unique_links:
            print("未能找到任何有效的新闻链接。请检查网址或放宽筛选条件。")

        for url, text in unique_links.items():
            f.write(f"文本: {text}\nURL: {url}\n---\n")

    print(f"所有链接信息已成功写入文件：{output_file}")

except WebDriverException as e:
    print("发生错误，请检查驱动程序路径是否正确或URL是否有效。")
    print(f"错误信息: {e}")

finally:
    # 关闭浏览器，释放资源
    if 'driver' in locals():
        print("关闭浏览器...")
        driver.quit()
        print("爬虫任务完成。")
 #source venv/Scripts/activate