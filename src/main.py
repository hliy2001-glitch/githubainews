import os
import json
import requests
from bs4 import BeautifulSoup
import anthropic
from datetime import datetime, timezone, timedelta

# ── 設定 ──────────────────────────────────────────────────────────────────────

GITHUB_TRENDING_URL = "https://github.com/trending"
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
TOP_N = 5

AI_KEYWORDS = [
    'ai', 'llm', 'gpt', 'claude', 'gemini', 'mistral', 'ollama',
    'langchain', 'rag', 'agent', 'chatbot', 'openai', 'anthropic',
    'transformer', 'neural', 'machine-learning', 'machine learning',
    'deep-learning', 'deep learning', 'nlp', 'language model',
    'diffusion', 'huggingface', 'hugging face', 'inference', 'fine-tun',
    'embedding', 'vector', 'multimodal', 'generative', 'foundation',
    'llama', 'qwen', 'deepseek', 'copilot', 'mcp', 'prompt',
    'text-to', 'speech', 'vision model', 'image generation',
]

CARD_COLORS = ['#1a1a2e', '#16213e', '#0f3460', '#533483', '#2b2d42']

# ── GitHub Trending 爬蟲 ──────────────────────────────────────────────────────

def scrape_github_trending():
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Safari/537.36'
        )
    }
    response = requests.get(GITHUB_TRENDING_URL, headers=headers, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, 'html.parser')
    repos = []

    for article in soup.find_all('article', class_='Box-row'):
        try:
            h2 = article.find('h2')
            if not h2:
                continue
            link = h2.find('a')
            if not link:
                continue

            repo_path = link.get('href', '').strip('/')
            parts = repo_path.split('/')
            if len(parts) < 2:
                continue
            owner, name = parts[0], parts[1]

            desc_tag = article.find('p')
            description = desc_tag.get_text(strip=True) if desc_tag else ''

            topics = [
                t.get_text(strip=True)
                for t in article.find_all('a', class_='topic-tag')
            ]

            stars_today_tag = article.find('span', class_='d-inline-block')
            stars_today = stars_today_tag.get_text(strip=True) if stars_today_tag else ''

            repos.append({
                'owner': owner,
                'name': name,
                'full_name': f"{owner}/{name}",
                'description': description,
                'topics': topics,
                'stars_today': stars_today,
                'url': f"https://github.com/{repo_path}",
            })
        except Exception:
            continue

    return repos

# ── AI 相關篩選 ───────────────────────────────────────────────────────────────

def is_ai_related(repo):
    haystack = ' '.join([
        repo['name'].lower().replace('-', ' ').replace('_', ' '),
        repo['description'].lower(),
        ' '.join(repo['topics']).lower(),
    ])
    return any(kw in haystack for kw in AI_KEYWORDS)

def get_top_ai_repos(repos):
    return [r for r in repos if is_ai_related(r)][:TOP_N]

# ── Claude 生成摘要（回傳結構化 JSON）────────────────────────────────────────

def generate_summary(repos):
    client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

    repo_lines = []
    for i, r in enumerate(repos, 1):
        topics_str = '、'.join(r['topics']) if r['topics'] else '無'
        repo_lines.append(
            f"{i}. 專案：{r['full_name']}\n"
            f"   說明：{r['description']}\n"
            f"   標籤：{topics_str}\n"
            f"   今日新增星星：{r['stars_today']}"
        )

    prompt = (
        "以下是今日 GitHub 上最熱門的 AI / LLM 相關開源專案資訊，"
        "請為每個專案用繁體中文撰寫大約 200 字的摘要。\n\n"
        + "\n\n".join(repo_lines)
        + "\n\n"
        "請以 JSON 陣列格式輸出，結構如下（只輸出純 JSON，不要加任何說明文字或 markdown）：\n"
        '[{"title": "專案名稱（只用斜線後的名稱，首字母大寫）", "summary": "摘要內文"}, ...]\n\n'
        "寫作要求：\n"
        "- 全程使用繁體中文\n"
        "- 語氣幽默專業，像一位懂技術又能說人話的科技編輯\n"
        "- 內文分成以下段落，段落之間空一行：\n"
        "  第一段：根據專案特性給 3～5 個 hashtag（例如 #AI工具 #開發者 #無需寫程式），放在同一行\n"
        "  第二段：破題句——目標客群是誰、所屬產業（若無則略過）、解決了什麼痛點\n"
        "  第三段：為何今天在 GitHub 上突然爆紅或備受關注\n"
        "  第四段：若有知名競品，簡短點出本專案的差異優勢；並說明使用門檻（需不需要會寫程式）\n"
        "  第五段：一個使用者未來可能的期待，以及一個值得觀察的潛在問題或風險\n"
        "- 用非技術語言，讓沒有程式背景的人也能理解\n"
        "- 每則摘要加入 1～2 個 emoji，自然融入而非硬加"
    )

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    # 移除可能的 markdown code block 包裝
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("```", 1)[0].strip()

    items = json.loads(raw)

    # 把 url 合併進去
    for i, item in enumerate(items):
        item['url'] = repos[i]['url'] if i < len(repos) else ''

    return items

# ── 組合 Flex Message 卡片 ────────────────────────────────────────────────────

def build_flex_bubble(index, title, summary, url, color):
    return {
        "type": "bubble",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": color,
            "paddingAll": "16px",
            "contents": [
                {
                    "type": "text",
                    "text": f"{index}.【{title}】",
                    "weight": "bold",
                    "color": "#ffffff",
                    "size": "md",
                    "wrap": True
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "14px",
            "contents": [
                {
                    "type": "text",
                    "text": summary,
                    "wrap": True,
                    "size": "sm",
                    "color": "#333333",
                    "lineSpacing": "6px"
                }
            ]
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "10px",
            "contents": [
                {
                    "type": "button",
                    "action": {
                        "type": "uri",
                        "label": "前往 GitHub →",
                        "uri": url
                    },
                    "style": "primary",
                    "color": color,
                    "height": "sm"
                }
            ]
        }
    }

# ── LINE 推播 ─────────────────────────────────────────────────────────────────

def send_line_flex(items):
    token = os.environ['LINE_CHANNEL_ACCESS_TOKEN']
    user_id = os.environ['LINE_USER_ID']

    tw_tz = timezone(timedelta(hours=8))
    today = datetime.now(tw_tz).strftime('%Y/%m/%d')
    header_text = f"👾{today} GitHub LLM應用相關今日熱門TOP5"

    bubbles = [
        build_flex_bubble(
            index=i + 1,
            title=item['title'],
            summary=item['summary'],
            url=item['url'],
            color=CARD_COLORS[i % len(CARD_COLORS)]
        )
        for i, item in enumerate(items)
    ]

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}',
    }
    payload = {
        "to": user_id,
        "messages": [
            {
                "type": "text",
                "text": header_text
            },
            {
                "type": "flex",
                "altText": header_text,
                "contents": {
                    "type": "carousel",
                    "contents": bubbles
                }
            }
        ]
    }
    resp = requests.post(LINE_PUSH_URL, headers=headers, json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()

# ── 主流程 ────────────────────────────────────────────────────────────────────

def main():
    print("== Step 1: 抓取 GitHub Trending ==")
    all_repos = scrape_github_trending()
    print(f"共抓到 {len(all_repos)} 個熱門 repo")

    print("== Step 2: 篩選 AI/LLM 相關 ==")
    ai_repos = get_top_ai_repos(all_repos)
    if not ai_repos:
        print("今日無 AI 相關熱門 repo，結束。")
        return
    for r in ai_repos:
        print(f"  [{r['stars_today']}] {r['full_name']} — {r['description'][:60]}")

    print("== Step 3: 呼叫 Claude 生成摘要 ==")
    items = generate_summary(ai_repos)
    for item in items:
        print(f"  [{item['title']}] {item['summary'][:50]}...")

    print("== Step 4: 發送 LINE Flex Message ==")
    result = send_line_flex(items)
    print("推播成功：", result)

if __name__ == "__main__":
    main()
