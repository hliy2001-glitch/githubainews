import os
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
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

# ── Claude 生成摘要 ───────────────────────────────────────────────────────────

def generate_summary(repos):
    genai.configure(api_key=os.environ['GEMINI_API_KEY'])
    model = genai.GenerativeModel('gemini-2.0-flash')

    repo_lines = []
    for i, r in enumerate(repos, 1):
        topics_str = '、'.join(r['topics']) if r['topics'] else '無'
        repo_lines.append(
            f"{i}. 專案：{r['full_name']}\n"
            f"   說明：{r['description']}\n"
            f"   標籤：{topics_str}\n"
            f"   今日新增星星：{r['stars_today']}\n"
            f"   連結：{r['url']}"
        )

    prompt = (
        "以下是今日 GitHub 上最熱門的 AI / LLM 相關開源專案資訊，"
        "請為每個專案用繁體中文撰寫大約 300 字的摘要。\n\n"
        + "\n\n".join(repo_lines)
        + "\n\n"
        "輸出格式規定（嚴格遵守）：\n"
        "1.【專案名稱】摘要內文約300字；\n"
        "2.【專案名稱】摘要內文約300字；\n"
        "以此類推...\n\n"
        "寫作要求：\n"
        "- 全程使用繁體中文\n"
        "- 解釋這個專案能解決什麼問題、帶來什麼價值\n"
        "- 說明為何今天在 GitHub 上突然爆紅或備受關注\n"
        "- 用非技術語言，讓沒有程式背景的人也能理解\n"
        "- 每條摘要結尾加上「；」\n"
        "- 不要加任何額外標題或說明文字，直接從 1. 開始輸出"
    )

    response = model.generate_content(prompt)
    return response.text.strip()

# ── LINE 推播 ─────────────────────────────────────────────────────────────────

def send_line_message(body_text):
    token = os.environ['LINE_CHANNEL_ACCESS_TOKEN']
    user_id = os.environ['LINE_USER_ID']

    tw_tz = timezone(timedelta(hours=8))
    today = datetime.now(tw_tz).strftime('%Y/%m/%d')
    full_text = f"GitHub AI 熱門專案日報\n{today}\n\n{body_text}"

    # LINE 單則文字訊息上限 5000 字，視情況截斷
    if len(full_text) > 4900:
        full_text = full_text[:4900] + "\n\n（內容過長，已自動截斷）"

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}',
    }
    payload = {
        "to": user_id,
        "messages": [{"type": "text", "text": full_text}],
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
    summary = generate_summary(ai_repos)
    print(summary[:300], "...")

    print("== Step 4: 發送 LINE 推播 ==")
    result = send_line_message(summary)
    print("推播成功：", result)

if __name__ == "__main__":
    main()
