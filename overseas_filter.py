#!/usr/bin/env python3
"""
海外商业情报自动抓取与过滤
纯规则引擎版本 — 零 API Key、零注册、零费用
GitHub Actions 每天早 9 点自动运行
"""

import os
import re
import sys
import json
import hashlib
import datetime
from pathlib import Path
from urllib.parse import urlparse

# ========== 依赖自动安装 ==========
def ensure_dependencies():
    import subprocess
    needed = []
    for mod, pkg in [("feedparser","feedparser"), ("requests","requests"), ("html2text","html2text")]:
        try:
            __import__(mod)
        except ImportError:
            needed.append(pkg)
    if needed:
        subprocess.check_call([sys.executable, "-m", "pip", "install", *needed, "-q"])

ensure_dependencies()
import feedparser
import requests
import html2text

# ========== 配置 ==========
CONFIG = {
    "rss_sources": [
        {"name": "TLDR AI", "url": "https://tldr.tech/ai/rss", "max": 10},
        {"name": "Hacker News Best", "url": "https://hnrss.org/frontpage?points=30&count=15", "max": 8},
        {"name": "Product Hunt", "url": "https://hnrss.org/frontpage", "max": 5},
    ],
    "output_dir": os.environ.get("OUTPUT_DIR", "./output"),
    "output_file": "daily_business_briefing.md",
    "dedup_file": "processed_articles.json",
    "max_content_length": 6000,
}

# ========== 三道筛子：关键词 + 启发式规则 ==========

# 第一道筛：赛道信号词（权重 3）
SIGNAL_KEYWORDS = {
    "ai": ["llm", "gpt", "openai", "claude", "gemini", "copilot", "stable diffusion",
           "midjourney", "langchain", "vector database", "rag", "fine-tun", "agent",
           "multimodal", "transformer", "diffusion model", "embedding", "token"],
    "saas": ["mrr", "arr", "saas", "subscription", "plg", "product-led", "churn",
             "retention", "ltv", "cac", "onboarding", "self-serve", "freemium"],
    "devtools": ["api", "sdk", "open source", "github", "developer tool", "cli",
                 "ide", "vs code", "copilot", "platform", "infrastructure", "devops"],
    "automation": ["no-code", "low-code", "workflow", "zapier", "automation",
                   "make.com", "n8n", "browser automation", "playwright", "selenium"],
    "indie_hacker": ["indie hacker", "solo founder", "bootstrapped", "side project",
                     "maker", "build in public", "#buildinpublic", "one-person"],
    "growth": ["growth hack", "viral", "seo", "content market", "cold email",
               "outbound", "inbound", "conversion rate", "a/b test", "landing page"],
    "monetization": ["monetize", "pricing", "revenue", "profit", "affiliate",
                     "sponsorship", "ad revenue", "paywall", "micro-saas"],
    "china_出海": ["china", "chinese", "出海", "wechat", "alibaba", "bytedance",
                   "tencent", "xiaomi", "shein", "temu", "tiktok", "cross-border"],
}

# 第二道筛：可执行性信号词（权重 2）
ACTIONABLE_KEYWORDS = [
    "how to", "tutorial", "step by step", "guide", "blueprint", "template",
    "checklist", "framework", "strategy", "playbook", "case study", "example",
    "launch", "ship", "shipped", "revenue report", "income report",
    "monthly report", "grew from", "went from", "scaled to",
    "first 100", "first 1000", "customer acquisition", "cold outreach",
    "${number}k", "${number}m", "million", "thousand",
]

# 第三道筛：深度信号词（权重 1）
DEPTH_KEYWORDS = [
    "insight", "analysis", "breakdown", "deep dive", "retrospective",
    "lesson learned", "mistake", "failure", "pivot", "experiment",
    "benchmark", "comparison", "vs", "versus", "alternative to",
    "underrated", "overlooked", "hidden", "secret",
]

# 减分项（大公司 PR、纯技术细节、噪音）
NEGATIVE_KEYWORDS = [
    "press release", "funding round", "series a", "series b", "series c",
    "ipo", "acqui-hire", "quarterly earnings", "shareholder",
    "patch notes", "bug fix", "hotfix", "version bump",
    "crypto", "nft", "blockchain", "web3", "token", "metaverse",
    "deployed", "cia", "nsa", "regulation", "ban", "lawsuit",
    "podcast", "episode", "sponsor", "advertisement",
]

# 中文关键词翻译表（用于输出）
CN_TRANSLATIONS = {
    "ai": "AI/人工智能", "saas": "SaaS", "devtools": "开发者工具",
    "automation": "自动化", "indie_hacker": "独立开发者",
    "growth": "增长", "monetization": "变现", "china_出海": "中国出海",
}


def compute_score_and_tags(title, content):
    """计算文章的商业相关度评分和标签"""
    text = (title + " " + content).lower()
    score = 0
    matched_tags = []
    tag_scores = {}

    # 先检查减分项
    neg_hits = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text)
    if neg_hits >= 3:
        return 0, ["不相关"]

    # 第一道：赛道信号
    for tag, keywords in SIGNAL_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in text)
        if hits >= 2:
            matched_tags.append(tag)
            tag_scores[tag] = min(hits, 5)
            score += hits * 3

    # 如果没有任何赛道匹配，直接淘汰
    if score == 0:
        return 0, []

    # 第二道：可执行性
    actionable_hits = sum(1 for kw in ACTIONABLE_KEYWORDS if kw in text)
    score += actionable_hits * 2

    # 第三道：深度
    depth_hits = sum(1 for kw in DEPTH_KEYWORDS if kw in text)
    score += depth_hits * 1

    # 内容长度加分（有内容的文章更好）
    if len(text) > 1000:
        score += 2
    if len(text) > 3000:
        score += 3

    # 标题包含数字（数据驱动型文章）
    if re.search(r'\d', title):
        score += 2

    # 标题包含问号（通常是深度分析）
    if '?' in title or '？' in title:
        score += 1

    # 归一化到 1-10
    final_score = min(max(int(score / 5), 1), 10)

    return final_score, matched_tags


def extract_metrics(text):
    """提取关键数据指标"""
    metrics = []
    patterns = [
        r'(\$\d[\d,]*(?:\.\d+)?[KkMmBb]?)',  # 金额
        r'(\d[\d,]*\s*(?:users|customers|downloads|stars|revenue))',  # 用户数等
        r'(\d+\s*(?:%|percent|times|x)\s*(?:increase|growth|improve))',  # 增长率
        r'(\d+\s*(?:days?|weeks?|months?|hours?)\s+(?:to|of))',  # 时间框架
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        metrics.extend(matches[:3])
    return list(set(metrics))[:5]


def extract_action_item(title, content, tags):
    """为文章生成可执行行动建议模板"""
    text = title + " " + content[:1000]

    templates = {
        "ai": "评估该 AI 方案能否集成到现有产品中作为差异化功能",
        "saas": "分析该定价/增长策略是否适用于你的目标市场",
        "devtools": "检查该工具/框架能否降低你的开发成本或提升效率",
        "automation": "探索能否用类似自动化思路简化你的运营流程",
        "indie_hacker": "参考该作者的 MVP 思路和营销路径",
        "growth": "测试该增长策略在你自己项目中的可行性",
        "monetization": "评估该变现模式与你的用户画像是否匹配",
        "china_出海": "研究该市场机会是否适合中国团队切入",
    }

    if tags:
        return templates.get(tags[0], "对比该案例与你的业务，列出 3 个可借鉴点")
    return "通读原文，提炼 1 个可在一周内执行的点"


def build_markdown_section(article, score, tags, metrics):
    """构建单篇 Markdown 板块"""
    tags_cn = [CN_TRANSLATIONS.get(t, t) for t in tags]
    tags_md = " ".join(f"`{t}`" for t in tags_cn)
    stars = "⭐" * min(score, 10)
    action = extract_action_item(article["title"], article["content"], tags)

    metrics_str = "、".join(metrics) if metrics else "未提取到关键数据"

    # 生成摘要（取前 200 字）
    summary = article["content"][:200].replace("\n", " ").strip()
    if len(article["content"]) > 200:
        summary += "..."

    return f"""### {article['title']}

| 字段 | 内容 |
|------|------|
| **评分** | {stars} ({score}/10) |
| **标签** | {tags_md} |
| **原文** | [阅读原文]({article['link']}) |
| **来源** | {article['source']} |
| **关键数据** | {metrics_str} |

> **摘要**：{summary}

**可执行行动**：{action}

---
"""


def build_daily_header():
    today = datetime.date.today()
    return f"""# 海外商业情报每日看板

**日期**：{today.strftime('%Y年%m月%d日')}（{today.strftime('%A')}）
**生成时间**：{datetime.datetime.now().strftime('%H:%M:%S')}
**引擎**：规则引擎 v2 · Zero API Key

---

"""


# ========== RSS 抓取 ==========
def fetch_rss_articles(source_config):
    articles = []
    try:
        feed = feedparser.parse(source_config["url"])
        for entry in feed.entries[:source_config["max"]]:
            content = ""
            if hasattr(entry, "content") and entry.content:
                content = entry.content[0].get("value", "")
            elif hasattr(entry, "summary"):
                content = entry.summary
            elif hasattr(entry, "description"):
                content = entry.description

            if content:
                h2t = html2text.HTML2Text()
                h2t.ignore_links = False
                h2t.ignore_images = True
                content = h2t.handle(content)

            content = content[:CONFIG["max_content_length"]]

            articles.append({
                "title": entry.get("title", "无标题"),
                "link": entry.get("link", ""),
                "source": source_config["name"],
                "published": entry.get("published", ""),
                "content": content,
            })
    except Exception as e:
        print(f"[RSS错误] {source_config['name']}: {e}")
    return articles


def load_processed_hashes(output_dir):
    dedup_path = Path(output_dir) / CONFIG["dedup_file"]
    if dedup_path.exists():
        return set(json.loads(dedup_path.read_text(encoding="utf-8")))
    return set()


def save_processed_hashes(output_dir, hashes):
    dedup_path = Path(output_dir) / CONFIG["dedup_file"]
    dedup_path.write_text(json.dumps(list(hashes)), encoding="utf-8")


def compute_hash(article):
    return hashlib.md5(f"{article['title']}{article['link']}".encode()).hexdigest()


def main():
    output_dir = Path(CONFIG["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    processed_hashes = load_processed_hashes(output_dir)

    # 1. 抓取
    all_articles = []
    for source in CONFIG["rss_sources"]:
        print(f"[抓取] {source['name']} ...")
        articles = fetch_rss_articles(source)
        all_articles.extend(articles)

    # 去重
    new_articles = []
    for a in all_articles:
        h = compute_hash(a)
        if h not in processed_hashes:
            a["_hash"] = h
            new_articles.append(a)

    print(f"\n[汇总] {len(all_articles)} 篇，去重后 {len(new_articles)} 篇新文章")
    if not new_articles:
        print("[完成] 无新文章")
        return

    # 2. 过滤评分
    passed = []
    for a in new_articles:
        score, tags = compute_score_and_tags(a["title"], a["content"])
        if score >= 3 and tags:  # 阈值：3 分以上且有赛道标签
            metrics = extract_metrics(a["content"])
            passed.append({"article": a, "score": score, "tags": tags, "metrics": metrics})
            processed_hashes.add(a["_hash"])
            print(f"  ✅ [{score}/10] {a['title'][:50]}")

    save_processed_hashes(output_dir, processed_hashes)

    # 按评分排序
    passed.sort(key=lambda x: x["score"], reverse=True)
    print(f"\n[通过] {len(passed)} 篇")

    # 3. 生成 Markdown
    output_path = output_dir / CONFIG["output_file"]
    existing = output_path.read_text(encoding="utf-8") if output_path.exists() else ""

    md = build_daily_header()
    md += f"## 今日精选（共 {len(passed)} 条）\n\n"
    for p in passed:
        md += build_markdown_section(p["article"], p["score"], p["tags"], p["metrics"])

    output_path.write_text(existing + md, encoding="utf-8")
    print(f"[完成] 看板: {output_path.absolute()}  |  通过 {len(passed)} 篇")


if __name__ == "__main__":
    main()