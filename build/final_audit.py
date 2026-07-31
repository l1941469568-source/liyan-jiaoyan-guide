# -*- coding: utf-8 -*-
"""终审独立验证脚本：不复用 Codex/Claude 的任何检查代码"""
import re, os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

SITE = r"C:\Users\admin\jiaoyan-guide\site"
issues = []

# 1) 图片引用完整性（自己解析 HTML）
img_refs = set()
html_files = [os.path.join(SITE, "index.html")] + \
    [os.path.join(SITE, "chapters", f) for f in os.listdir(os.path.join(SITE, "chapters")) if f.endswith(".html")]
for hf in html_files:
    base = os.path.dirname(hf)
    for m in re.finditer(r'<img[^>]+src="([^"]+)"', open(hf, encoding="utf-8").read()):
        p = os.path.normpath(os.path.join(base, m.group(1)))
        img_refs.add(p)
        if not os.path.exists(p):
            issues.append(f"缺失图片: {m.group(1)} in {os.path.basename(hf)}")
print(f"[1] HTML 页面数={len(html_files)}, 唯一图片引用={len(img_refs)}, 缺失=0" if not issues else f"[1] 问题: {issues[:5]}")

# 2) 站内链接完整性 + 上一节/下一节链
links = []
for hf in html_files:
    base = os.path.dirname(hf)
    for m in re.finditer(r'<a[^>]+href="([^"#]+)[^"]*"', open(hf, encoding="utf-8").read()):
        url = m.group(1)
        if url.startswith(("http://", "https://", "mailto:", "javascript:")):
            issues.append(f"外部链接: {url} in {os.path.basename(hf)}")
            continue
        if not os.path.exists(os.path.normpath(os.path.join(base, url))):
            issues.append(f"死链: {url} in {os.path.basename(hf)}")
        links.append(url)
print(f"[2] 站内链接检查完毕, 问题数={len([i for i in issues if '死链' in i or '外部链接' in i])}")

# 3) prev/next 链完整性：按文件名排序验证相邻页互链
chaps = sorted(f for f in os.listdir(os.path.join(SITE, "chapters")) if f.endswith(".html"))
chain_errors = []
for i, f in enumerate(chaps):
    html = open(os.path.join(SITE, "chapters", f), encoding="utf-8").read()
    prev_m = re.search(r'class="[^"]*prev[^"]*"[^>]*href="([^"]+)"|href="([^"]+)"[^>]*class="[^"]*prev', html)
    nxt_m  = re.search(r'class="[^"]*next[^"]*"[^>]*href="([^"]+)"|href="([^"]+)"[^>]*class="[^"]*next', html)
    # 宽松提取：找 rel/prev 文本附近的 href
    if i > 0 and chaps[i-1] not in html:
        chain_errors.append(f"{f} 缺少到 {chaps[i-1]} 的上一节链接")
    if i < len(chaps)-1 and chaps[i+1] not in html:
        chain_errors.append(f"{f} 缺少到 {chaps[i+1]} 的下一节链接")
print(f"[3] prev/next 链: {len(chaps)} 页, 链断裂数={len(chain_errors)}")
for e in chain_errors[:5]: print("   ", e)

# 4) file:// 兼容：无外部资源、无 fetch
ext = []
for root, _, files in os.walk(SITE):
    for fn in files:
        if fn.endswith((".html", ".css", ".js")):
            t = open(os.path.join(root, fn), encoding="utf-8").read()
            for m in re.finditer(r'(?:src|href)="(https?://[^"]+)"', t):
                ext.append(f"{fn}: {m.group(1)}")
            if "fetch(" in t:
                ext.append(f"{fn}: 含 fetch(")
print(f"[4] 外部资源/fetch 违规数={len(ext)}")
for e in ext[:5]: print("   ", e)

# 5) 内容保真度：抽查与 Claude 不同的节 —— 九、（五）发布研修日志 (PDF p185-187)
import pymupdf
doc = pymupdf.open(r"C:\Users\admin\jiaoyan-guide\build\manual.pdf")
pdf_text = "".join(doc[p].get_text() for p in (184, 185, 186))
pdf_chars = set(re.sub(r"\s", "", pdf_text))
target = os.path.join(SITE, "chapters", "09-05.html")
if os.path.exists(target):
    web = open(target, encoding="utf-8").read()
    web_text = re.sub(r"<[^>]+>|\s", "", web)
    hit = sum(1 for c in pdf_chars if c in web_text)
    print(f"[5] 09-05.html 存在, PDF p185-187 字符覆盖率={hit/len(pdf_chars)*100:.1f}%")
else:
    cand = [f for f in chaps if f.startswith("09")]
    print(f"[5] 09-05.html 不存在! 第九章页面: {cand}")

# 6) 每页都有导航树和灯箱结构
struct_err = []
for f in chaps[:5] + chaps[-3:]:
    html = open(os.path.join(SITE, "chapters", f), encoding="utf-8").read()
    for needle in ('aria-current="page"', 'lightbox', 'search-index.js'):
        if needle not in html:
            struct_err.append(f"{f} 缺少 {needle}")
print(f"[6] 结构抽查(8页): 问题数={len(struct_err)}")
for e in struct_err: print("   ", e)

print("\n=== 终审结论:", "通过" if not issues and not chain_errors and not ext and not struct_err else "存在问题", "===")
