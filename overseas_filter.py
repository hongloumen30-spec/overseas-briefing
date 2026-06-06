#!/usr/bin/env python3
"""
海外邮件自动抓取与商业过滤
每天自动抓取 RSS 源 → 三道筛子深度过滤 → 结构化中文看板追加写入 Markdown
"""

import os
import sys
import json
import hashlib
import datetime
import time
from pathlib import Path
from urllib.parse import urlparse

# ========== 依赖检测与自动安装 ==========
REQUIRED_PACKAGES = {
    "feedparser": "feedparser",
    "requests": "requests",
    "html2text": "html2text",
}

def ensure_dependencies():
    import subprocess
    missing = []
    for mod, pkg in REQUIRED_PACKAGES.items():
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        subprocess.check_call([sys.executable, "-m", "pip", "install", *missing, "-q"])
        print(f"[依赖] 已安装: {', '.join(missing)}")

ensure_dependencies()

import feedparser
import requests
import html2text

# ========== 配置区（可按需修改） ==========
CONFIG = {
    # RSS 源列表：TLDR AI + Hacker News + Indie Hackers
    "rss_sources": [
        {
            "name": "TLDR AI",
            "url": "https://tldr.tech/ai/rss",
            "max_articles": 10,
        },
        {
            "name": "Hacker News (Best)",
            "url": "https://hnrss.org/frontpage?points=30&count=15",
            "max_articles": 8,
        },
        {
            "name": "Product Hunt Today",
            "url": "https://hnrss.org/frontpage",
            "max_articles": 5,
        },
    ],

    # LLM API 配置（Groq 免费方案，注册即用无需绑卡）
    "llm_api_url": os.environ.get("LLM_API_URL", "https://api.groq.com/openai/v1/chat/completions"),
    "llm_api_key": os.environ.get("LLM_API_KEY", ""),
    "llm_model": os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile"),

    # 输出文件路径
    "output_dir": os.environ.get("OUTPUT_DIR", "./output"),
    "output_file": "daily_business_briefing.md",

    # 已处理文章的哈希去重文件
    "dedup_file": "processed_articles.json",

    # 每篇文章请求间隔（秒），避免 API 限流
    "request_interval": 2,

    # 单篇文章最大字符数（超出截断）
    "max_content_length": 8000,
}

# ========== 三道筛子过滤提示词 ==========
FILTER_PROMPT = """你是顶级商业分析师。请用「三道筛子」严格过滤以下海外科技文章，输出结构化结果。

## 输入文章
标题：{title}
来源：{source}
原文：
{content}

## 三道筛子标准

### 第一道：赛道信号筛
- 是否涉及 AI/ML、SaaS、开发者工具、自动化、出海、Creator Economy 赛道？
- 是否涉及新型商业模式、定价策略、增长黑客、用户获取新范式？
- 是否属于「有用的信号」而非纯技术实现细节或大公司 PR 通稿？
→ 不通过则直接返回 {"pass": false}

### 第二道：可执行性筛
- 该信息能否在 1-3 个月内转化为可落地的商业行动？
- 是否存在「先发优势窗口」或「信息不对称红利」？
- 核心逻辑是否能被独立开发者或小团队复用？
→ 不通过则直接返回 {"pass": false}

### 第三道：深加工筛
对通过的文章进行以下提炼：
- 一句话核心洞察（中文，40字以内）
- 商业模式拆解（如何赚钱）
- 关键数据/指标（如有）
- 对中国出海创业者的启示（2-3条）
- 可立即执行的行动建议（1条）

## 输出格式（严格 JSON）
{{
  "pass": true/false,
  "score": 1-10,
  "title_cn": "中文标题",
  "insight": "一句话核心洞察",
  "business_model": "商业模式拆解",
  "key_data": "关键数据或留空",
  "china_insights": ["启示1", "启示2"],
  "action_item": "可立即执行的行动建议",
  "tags": ["标签1", "标签2"]
}}
只输出 JSON，不要任何多余文字。"""


# ========== 核心函数 ==========

def fetch_rss_articles(source_config):
    """抓取单个 RSS 源的文章列表"""
    articles = []
    try:
        feed = feedparser.parse(source_config["url"])
        entries = feed.entries[: source_config["max_articles"]]
        for entry in entries:
            # 提取正文
            content = ""
            if hasattr(entry, "content") and entry.content:
                content = entry.content[0].get("value", "")
            elif hasattr(entry, "summary"):
                content = entry.summary
            elif hasattr(entry, "description"):
                content = entry.description

            # HTML → 纯文本
            if content:
                h2t = html2text.HTML2Text()
                h2t.ignore_links = False
                h2t.ignore_images = True
                content = h2t.handle(content)

            content = content[: CONFIG["max_content_length"]]

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
    """加载已处理文章的去重哈希"""
    dedup_path = Path(output_dir) / CONFIG["dedup_file"]
    if dedup_path.exists():
        return set(json.loads(dedup_path.read_text(encoding="utf-8")))
    return set()


def save_processed_hashes(output_dir, hashes):
    """保存已处理哈希"""
    dedup_path = Path(output_dir) / CONFIG["dedup_file"]
    dedup_path.write_text(json.dumps(list(hashes)), encoding="utf-8")


def compute_article_hash(article):
    """计算文章去重哈希"""
    raw = f"{article['title']}{article['link']}"
    return hashlib.md5(raw.encode()).hexdigest()


def filter_article(article):
    """调用 LLM API 进行三道筛子过滤"""
    prompt = FILTER_PROMPT.format(
        title=article["title"],
        source=article["source"],
        content=article["content"],
    )

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CONFIG['llm_api_key']}",
    }

    payload = {
        "model": CONFIG["llm_model"],
        "messages": [
            {"role": "system", "content": "你是严格的商业分析师，只输出 JSON。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 800,
    }

    try:
        resp = requests.post(
            CONFIG["llm_api_url"], headers=headers, json=payload, timeout=60
        )
        resp.raise_for_status()
        result = resp.json()
        content = result["choices"][0]["message"]["content"].strip()

        # 清理可能的 ```json 包裹
        if content.startswith("```"):
            content = content.split("\n", 1)[1]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

        return json.loads(content)
    except json.JSONDecodeError:
        print(f"[LLM解析失败] {article['title'][:40]} → 返回非JSON")
        return {"pass": False}
    except requests.exceptions.RequestException as e:
        print(f"[LLM请求失败] {article['title'][:40]}: {e}")
        return {"pass": False}
    except Exception as e:
        print(f"[LLM未知错误] {article['title'][:40]}: {e}")
        return {"pass": False}


def build_markdown_section(result, article):
    """将过滤结果构建为 Markdown 板块"""
    if not result.get("pass"):
        return ""

    tags_md = " ".join(f"`{t}`" for t in result.get("tags", []))
    insights_md = "\n".join(f"- {s}" for s in result.get("china_insights", []))

    return f"""### {result.get('title_cn', article['title'])}

| 字段 | 内容 |
|------|------|
| **评分** | {'⭐' * min(result.get('score', 5), 10)} ({result.get('score', 'N/A')}/10) |
| **标签** | {tags_md} |
| **原文** | [{article['title']}]({article['link']}) |
| **来源** | {article['source']} |

> **核心洞察**：{result.get('insight', '无')}

**商业模式拆解**：{result.get('business_model', '无')}

**关键数据**：{result.get('key_data', '无') if result.get('key_data') else '未提及'}

**对中国出海创业者的启示**：
{insights_md}

**可执行行动**：{result.get('action_item', '无')}

---
"""


def build_daily_header():
    """构建每日报告的头部"""
    today = datetime.date.today()
    return f"""# 海外商业情报每日看板

**日期**：{today.strftime('%Y年%m月%d日')}（{today.strftime('%A')}）
**生成时间**：{datetime.datetime.now().strftime('%H:%M:%S')}

---

"""


def main():
    output_dir = Path(CONFIG["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    # 加载去重哈希
    processed_hashes = load_processed_hashes(output_dir)

    # 1. 抓取所有 RSS 源
    all_articles = []
    for source in CONFIG["rss_sources"]:
        print(f"[抓取] {source['name']} ...")
        articles = fetch_rss_articles(source)
        print(f"  → 获取 {len(articles)} 篇")
        all_articles.extend(articles)

    # 去重
    new_articles = []
    for a in all_articles:
        h = compute_article_hash(a)
        if h not in processed_hashes:
            a["_hash"] = h
            new_articles.append(a)

    print(f"\n[汇总] 共 {len(all_articles)} 篇，去重后 {len(new_articles)} 篇新文章")

    if not new_articles:
        print("[完成] 无新文章，跳过过滤")
        return

    # 2. 过滤 + 翻译
    passed_results = []
    new_hashes = set()

    for i, article in enumerate(new_articles):
        print(f"[过滤 {i+1}/{len(new_articles)}] {article['title'][:50]}...")
        result = filter_article(article)

        new_hashes.add(article["_hash"])

        if result.get("pass"):
            result["_article"] = article
            passed_results.append(result)
            print(f"  ✅ 通过 (评分 {result.get('score', '?')}/10)")
        else:
            print(f"  ❌ 未通过")

        # 速率限制
        if i < len(new_articles) - 1:
            time.sleep(CONFIG["request_interval"])

    # 更新去重哈希
    processed_hashes.update(new_hashes)
    save_processed_hashes(output_dir, processed_hashes)

    # 3. 按评分排序
    passed_results.sort(key=lambda x: x.get("score", 0), reverse=True)

    print(f"\n[结果] 通过过滤: {len(passed_results)} 篇")

    # 4. 构建 Markdown 输出
    output_path = output_dir / CONFIG["output_file"]

    # 如果已有文件，追加模式
    if output_path.exists():
        existing = output_path.read_text(encoding="utf-8")
        # 在现有内容末尾追加，不覆盖历史
    else:
        existing = ""

    md = build_daily_header()
    md += f"## 今日精选（共 {len(passed_results)} 条）\n\n"

    for r in passed_results:
        md += build_markdown_section(r, r["_article"])

    # 追加到文件
    full_content = existing + md
    output_path.write_text(full_content, encoding="utf-8")

    print(f"[完成] 看板已写入: {output_path.absolute()}")
    print(f"        通过文章数: {len(passed_results)}")

    # 输出简短摘要
    if passed_results:
        print("\n📋 今日精选摘要：")
        for r in passed_results[:5]:
            print(f"  [{r.get('score', '?')}/10] {r.get('title_cn', '?')} — {r.get('insight', '')[:60]}...")


if __name__ == "__main__":
    main()