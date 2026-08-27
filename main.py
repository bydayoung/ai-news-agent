import calendar
import html
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote_plus

import feedparser
import requests
from dotenv import load_dotenv


# =========================================================
# 환경 변수
# =========================================================

# 로컬 테스트에서는 .env 사용
# GitHub Actions에서는 Repository Secret을 환경 변수로 전달
load_dotenv()

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")


# =========================================================
# 설정
# =========================================================

KEYWORDS = [
    # AI / Agent
    "AI Agent",
    "LLM Agent",
    "AI coding agent",
    "Computer Use AI",

    # AI Education
    "AI education",
    "AI tutor",
    "personalized learning AI",
    "AI assessment education",

    # Developer Education
    "developer education",
    "coding education",
    "developer training",
    "AI developer training",
]

NEWS_PER_KEYWORD = 8
MAX_SELECTED_NEWS = 5
LOOKBACK_DAYS = 7


# =========================================================
# 공통
# =========================================================

def clean_html_text(text):
    if not text:
        return ""

    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def clean_title(title, source):
    """Google News 제목 뒤의 ' - 출처명' 제거"""

    title = title.strip()

    if source:
        suffix = f" - {source}"

        if title.endswith(suffix):
            title = title[:-len(suffix)]

    return title.strip()


def normalize_title(title):
    title = title.lower()
    title = re.sub(r"[^가-힣a-z0-9\s]", "", title)
    title = re.sub(r"\s+", " ", title)

    return title.strip()


def format_published_date(article):
    timestamp = article.get("published_timestamp")

    if not timestamp:
        return "발행일 정보 없음"

    return datetime.fromtimestamp(
        timestamp,
        tz=timezone.utc,
    ).strftime("%Y-%m-%d")


# =========================================================
# 1. Google News RSS 수집
# =========================================================

def get_google_news(keyword):
    encoded_keyword = quote_plus(keyword)

    url = (
        "https://news.google.com/rss/search"
        f"?q={encoded_keyword}"
        "&hl=ko"
        "&gl=KR"
        "&ceid=KR:ko"
    )

    feed = feedparser.parse(url)

    articles = []
    current_time = time.time()
    cutoff = current_time - (LOOKBACK_DAYS * 24 * 60 * 60)

    for entry in feed.entries:
        published_timestamp = None

        if entry.get("published_parsed"):
            published_timestamp = calendar.timegm(
                entry.published_parsed
            )

            if published_timestamp < cutoff:
                continue

        source = ""

        if entry.get("source"):
            source = entry.source.get("title", "")

        title = clean_title(
            entry.get("title", ""),
            source,
        )

        if not title:
            continue

        articles.append(
            {
                "title": title,
                "link": entry.get("link", ""),
                "published": entry.get("published", ""),
                "published_timestamp": published_timestamp,
                "source": source or "출처 정보 없음",
                "keyword": keyword,
            }
        )

        if len(articles) >= NEWS_PER_KEYWORD:
            break

    return articles


# =========================================================
# 2. 중복 제거
# =========================================================

def remove_duplicates(articles):
    seen = set()
    result = []

    for article in articles:
        normalized = normalize_title(article["title"])

        if not normalized or normalized in seen:
            continue

        seen.add(normalized)
        result.append(article)

    return result


# =========================================================
# 3. LLM 없는 규칙 기반 뉴스 선정
# =========================================================

IMPORTANT_TERMS = {
    "agent": 4,
    "coding agent": 5,
    "computer use": 5,
    "developer tool": 4,
    "ai tutor": 5,
    "personalized learning": 4,
    "assessment": 4,
    "평가": 4,
    "교육": 3,
    "developer education": 4,
    "개발자 교육": 4,
    "llm": 3,
    "생성형 ai": 3,
    "artificial intelligence": 2,
    "ai": 1,
}

EXCLUDE_TERMS = [
    "주가",
    "급등",
    "급락",
    "목표주가",
    "투자의견",
    "증권",
]


def relevance_score(article):
    """제목 + 검색 키워드를 기준으로 단순 관련도 점수 계산"""

    text = (
        f"{article['title']} "
        f"{article.get('keyword', '')}"
    ).lower()

    score = 0

    for term, weight in IMPORTANT_TERMS.items():
        if term.lower() in text:
            score += weight

    for term in EXCLUDE_TERMS:
        if term.lower() in text:
            score -= 10

    timestamp = article.get("published_timestamp") or 0

    return score, timestamp


def select_news(articles):
    """LLM 대신 규칙 기반으로 관련도 높은 뉴스 선정"""

    ranked = sorted(
        articles,
        key=relevance_score,
        reverse=True,
    )

    ranked = [
        article
        for article in ranked
        if relevance_score(article)[0] >= 0
    ]

    return ranked[:MAX_SELECTED_NEWS]


# =========================================================
# 4. Slack Block Kit
# =========================================================

def build_slack_blocks(articles):
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "☁️ AI & Education Weekly Briefing",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "🔥 *이번 주 주요 뉴스*\n"
                    f"AI · Agent · 교육 · 개발자 교육 관련 "
                    f"뉴스 {len(articles)}개를 모았습니다."
                ),
            },
        },
        {"type": "divider"},
    ]

    for index, article in enumerate(articles, 1):
        article_link = (
            f"<{article['link']}|🔗 기사 읽기>"
            if article.get("link")
            else "기사 링크 없음"
        )

        published_date = format_published_date(article)

        text = (
            f"*{index}. {article['title']}*\n"
            f"_출처: {article['source']} · {published_date}_\n"
            f"{article_link}"
        )

        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": text,
                },
            }
        )

        blocks.append({"type": "divider"})

    return blocks


# =========================================================
# 5. Slack 전송
# =========================================================

def send_slack(articles):
    if not SLACK_WEBHOOK_URL:
        raise RuntimeError(
            "SLACK_WEBHOOK_URL이 없습니다. "
            "GitHub Repository Secret 또는 .env를 확인하세요."
        )

    if not articles:
        print("Slack으로 보낼 뉴스가 없습니다.")
        return

    payload = {
        "text": "☁️ AI & Education Weekly Briefing",
        "blocks": build_slack_blocks(articles),
    }

    response = requests.post(
        SLACK_WEBHOOK_URL,
        json=payload,
        timeout=15,
    )

    response.raise_for_status()

    print("✅ Slack 전송 완료")


# =========================================================
# Main
# =========================================================

def main():
    print("=" * 60)
    print("AI & Education Weekly News")
    print("=" * 60)

    all_articles = []

    print(f"\n최근 {LOOKBACK_DAYS}일 뉴스 수집 시작\n")

    for keyword in KEYWORDS:
        print(f"[검색] {keyword}")

        try:
            articles = get_google_news(keyword)
            print(f"      → {len(articles)}개")
            all_articles.extend(articles)

        except Exception as e:
            print(f"      → 오류: {e}")

    all_articles = remove_duplicates(all_articles)

    print(f"\n중복 제거 후 뉴스: {len(all_articles)}개")

    if not all_articles:
        print("최근 뉴스가 없습니다.")
        return

    selected_articles = select_news(all_articles)

    print(f"최종 선정: {len(selected_articles)}개")

    for index, article in enumerate(selected_articles, 1):
        print(f"{index}. {article['title']}")
        print(f"   {article['source']}")
        print(f"   {article['link']}")

    send_slack(selected_articles)


if __name__ == "__main__":
    main()
