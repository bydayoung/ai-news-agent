import calendar
import html
import json
import os
import re
import time
from urllib.parse import quote_plus

import feedparser
import requests
import trafilatura
from dotenv import load_dotenv


# =========================================================
# 환경 변수
# =========================================================

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

MODEL = "gemma3:4b"

OLLAMA_URL = "http://localhost:11434/api/chat"

NEWS_PER_KEYWORD = 5

MAX_SELECTED_NEWS = 5

# 기사 하나당 Ollama에 전달할 최대 본문 길이
MAX_ARTICLE_LENGTH = 6000


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
    """
    Google News 제목 뒤에 붙는
    ' - 연합뉴스' 같은 출처명을 제거
    """

    title = title.strip()

    if source:
        suffix = f" - {source}"

        if title.endswith(suffix):
            title = title[:-len(suffix)]

    return title.strip()


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
    one_day_ago = current_time - (24 * 60 * 60)

    for entry in feed.entries:

        # 최근 24시간 기사만
        if entry.get("published_parsed"):

            published_timestamp = calendar.timegm(
                entry.published_parsed
            )

            if published_timestamp < one_day_ago:
                continue

        source = ""

        if entry.get("source"):
            source = entry.source.get("title", "")

        rss_summary = clean_html_text(
            entry.get("summary", "")
        )

        title = clean_title(
            entry.title,
            source
        )

        articles.append({
            "title": title,
            "link": entry.link,
            "published": entry.get("published", ""),
            "source": source,
            "keyword": keyword,
            "rss_summary": rss_summary,
        })

        if len(articles) >= NEWS_PER_KEYWORD:
            break

    return articles


# =========================================================
# 2. 중복 제거
# =========================================================

def normalize_title(title):
    title = title.lower()

    title = re.sub(
        r"[^가-힣a-z0-9\s]",
        "",
        title
    )

    title = re.sub(
        r"\s+",
        " ",
        title
    )

    return title.strip()


def remove_duplicates(articles):
    seen = set()
    result = []

    for article in articles:

        normalized = normalize_title(
            article["title"]
        )

        if normalized in seen:
            continue

        seen.add(normalized)
        result.append(article)

    return result


# =========================================================
# 3. Ollama JSON 호출
# =========================================================

def call_ollama_json(prompt):
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "format": "json",
        "stream": False,
        "options": {
            "temperature": 0.1,
        },
    }

    response = requests.post(
        OLLAMA_URL,
        json=payload,
        timeout=300,
    )

    response.raise_for_status()

    content = response.json()[
        "message"
    ]["content"]

    return json.loads(content)


# =========================================================
# 4. 구름에 유용한 뉴스 선정
# =========================================================

def select_news(articles):
    news_text = ""

    for index, article in enumerate(articles):

        news_text += f"""
INDEX: {index}
제목: {article["title"]}
출처: {article["source"]}
키워드: {article["keyword"]}
발행일: {article["published"]}

----------------------------------------
"""

    prompt = f"""
너는 AI 교육 플랫폼 회사 '구름'의 직원들에게
매일 제공할 뉴스 큐레이션 Agent다.

아래 뉴스 중 구름 구성원이 업무상 알아두면
유용한 뉴스만 최대 {MAX_SELECTED_NEWS}개 선정한다.


[구름이 관심 있는 분야]

- AI / LLM
- AI Agent
- Coding Agent
- Computer Use Agent
- AI Developer Tool
- AI 기반 교육
- AI Tutor
- Personalized Learning
- AI 기반 시험 및 평가
- 개발자 교육
- 기업 대상 AI 교육
- 개발자 역량 평가
- 개발자 채용 시장 변화


[우선적으로 선택]

- 새로운 AI 모델 및 주요 기능 발표
- AI Agent 기술 변화
- Coding Agent / Developer Tool 변화
- AI를 교육에 적용한 사례
- AI Tutor 및 개인화 학습
- AI 기반 시험 / 평가 기술
- 개발자 교육 시장 변화
- 기업 AI 교육 관련 변화
- 교육 플랫폼이 참고할 만한 기술이나 서비스


[제외]

- 단순 주가 뉴스
- 단순 투자 뉴스
- 광고성 기사
- AI와 직접 관계없는 뉴스
- 거의 동일한 사건을 다루는 중복 뉴스


반드시 기사 INDEX만 선택한다.

최대 {MAX_SELECTED_NEWS}개까지만 선택한다.

JSON만 출력한다.

형식:

{{
    "selected_indices": [0, 2, 5]
}}


뉴스 목록:

{news_text}
"""

    try:
        result = call_ollama_json(prompt)

    except Exception as e:
        print(
            f"뉴스 선정 오류: {e}"
        )
        return []

    indices = result.get(
        "selected_indices",
        []
    )

    validated = []

    for index in indices:

        if not isinstance(index, int):
            continue

        if index < 0:
            continue

        if index >= len(articles):
            continue

        if index in validated:
            continue

        validated.append(index)

        if len(validated) >= MAX_SELECTED_NEWS:
            break

    return validated


# =========================================================
# 5. 기사 본문 가져오기
# =========================================================

def get_article_content(article):
    """
    Google News 링크를 통해 기사 내용을 가져온다.

    본문 수집 실패 시 RSS summary를 사용한다.
    """

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "Chrome/120.0 Safari/537.36"
        )
    }

    try:
        response = requests.get(
            article["link"],
            headers=headers,
            timeout=15,
            allow_redirects=True,
        )

        response.raise_for_status()

        extracted = trafilatura.extract(
            response.text,
            include_comments=False,
            include_tables=False,
            include_links=False,
        )

        if extracted:

            extracted = extracted.strip()

            # 충분한 본문이 있다면 사용
            if len(extracted) >= 200:

                return (
                    extracted[:MAX_ARTICLE_LENGTH],
                    response.url
                )

    except Exception:
        pass

    # 본문 수집 실패 → RSS 설명 사용
    fallback = article.get(
        "rss_summary",
        ""
    )

    if not fallback:
        fallback = article["title"]

    return (
        fallback[:MAX_ARTICLE_LENGTH],
        article["link"]
    )


# =========================================================
# 6. 기사 하나씩 개별 요약
# =========================================================

def summarize_article(article, content):
    prompt = f"""
다음 뉴스 기사를 한국어로 요약한다.

[제목]
{article["title"]}

[출처]
{article["source"]}

[기사 내용]
{content}


규칙:

- 핵심 내용을 2~3문장으로 요약한다.
- 기사 제목을 그대로 반복하지 않는다.
- 구체적으로 무엇이 발표되었거나 변화했는지 설명한다.
- 기사에 없는 내용을 추측하지 않는다.
- 회사 관점이나 의견은 작성하지 않는다.
- 선정 이유도 작성하지 않는다.
- 뉴스 내용 자체만 요약한다.
- 지나치게 길게 작성하지 않는다.

반드시 JSON만 출력한다.

형식:

{{
    "summary": "기사 핵심 요약"
}}
"""

    try:
        result = call_ollama_json(
            prompt
        )

        summary = result.get(
            "summary",
            ""
        ).strip()

        if summary:
            return summary

    except Exception as e:

        print(
            f"요약 오류: {e}"
        )

    # 요약 실패 시 fallback
    fallback = article.get(
        "rss_summary",
        ""
    )

    if fallback:
        return fallback

    return "기사 요약을 생성하지 못했습니다."


# =========================================================
# 7. 최종 뉴스 데이터 생성
# =========================================================

def analyze_news(articles):
    print(
        "\n구름 맞춤 뉴스 선정 중..."
    )

    selected_indices = select_news(
        articles
    )

    if not selected_indices:
        return []

    print(
        f"선정된 뉴스: "
        f"{len(selected_indices)}개"
    )

    results = []

    for order, index in enumerate(
        selected_indices,
        1
    ):

        article = articles[index]

        print()
        print(
            f"[{order}/{len(selected_indices)}] "
            f"본문 수집"
        )

        print(
            f"  {article['title']}"
        )

        content, resolved_url = (
            get_article_content(
                article
            )
        )

        print(
            "  → 요약 생성 중..."
        )

        summary = summarize_article(
            article,
            content
        )

        results.append({
            "title": article["title"],
            "summary": summary,
            "source": (
                article["source"]
                or "출처 정보 없음"
            ),
            "url": resolved_url,
        })

    return results


# =========================================================
# 8. Slack Block Kit
# =========================================================

def build_slack_blocks(articles):
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": (
                    "☁️ AI & Education "
                    "Daily Briefing"
                ),
                "emoji": True,
            },
        },

        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "🔥 *오늘의 핵심 뉴스*\n"
                    f"구름 구성원에게 유용한 "
                    f"뉴스 {len(articles)}개를 "
                    f"선정했습니다."
                ),
            },
        },

        {
            "type": "divider",
        },
    ]

    for index, article in enumerate(
        articles,
        1
    ):

        # Slack mrkdwn에서 클릭 가능한 링크
        article_link = (
            f"<{article['url']}|"
            f"🔗 기사 읽기>"
        )

        text = (
            f"*{index}. {article['title']}*\n\n"
            f"{article['summary']}\n\n"
            f"_출처: {article['source']}_\n"
            f"{article_link}"
        )

        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": text,
            },
        })

        blocks.append({
            "type": "divider",
        })

    return blocks


# =========================================================
# 9. Slack 전송
# =========================================================

def send_slack(articles):
    if not SLACK_WEBHOOK_URL:

        print(
            "SLACK_WEBHOOK_URL이 "
            "설정되지 않았습니다."
        )

        return

    if not articles:

        print(
            "Slack으로 보낼 뉴스가 없습니다."
        )

        return

    blocks = build_slack_blocks(
        articles
    )

    payload = {
        "text": (
            "☁️ AI & Education "
            "Daily Briefing"
        ),
        "blocks": blocks,
    }

    try:
        response = requests.post(
            SLACK_WEBHOOK_URL,
            json=payload,
            timeout=10,
        )

        response.raise_for_status()

        print()
        print("✅ Slack 전송 완료")

    except requests.exceptions.RequestException as e:

        print(
            f"Slack 전송 오류: {e}"
        )


# =========================================================
# Main
# =========================================================

def main():
    print("=" * 60)
    print(
        "AI & Education News Agent"
    )
    print("=" * 60)

    print(
        "\n뉴스 수집 시작\n"
    )

    all_articles = []

    # -----------------------------------------------------
    # 뉴스 수집
    # -----------------------------------------------------

    for keyword in KEYWORDS:

        print(
            f"[검색] {keyword}"
        )

        try:
            articles = get_google_news(
                keyword
            )

            print(
                f"      → "
                f"{len(articles)}개"
            )

            all_articles.extend(
                articles
            )

        except Exception as e:

            print(
                f"      → 오류: {e}"
            )

    # -----------------------------------------------------
    # 중복 제거
    # -----------------------------------------------------

    all_articles = remove_duplicates(
        all_articles
    )

    print()
    print(
        f"중복 제거 후 뉴스: "
        f"{len(all_articles)}개"
    )

    if not all_articles:

        print(
            "최근 뉴스가 없습니다."
        )

        return

    # -----------------------------------------------------
    # Agent
    # -----------------------------------------------------

    print(
        "\nAgent 분석 시작..."
    )

    try:
        selected_articles = (
            analyze_news(
                all_articles
            )
        )

    except requests.exceptions.ConnectionError:

        print(
            "Ollama에 연결할 수 없습니다."
        )

        print(
            "Ollama가 실행 중인지 "
            "확인해주세요."
        )

        print()
        print(
            f"ollama run {MODEL}"
        )

        return

    except Exception as e:

        print(
            f"Agent 실행 오류: {e}"
        )

        return

    # -----------------------------------------------------
    # 결과
    # -----------------------------------------------------

    if not selected_articles:

        print(
            "오늘 공유할 중요한 "
            "뉴스가 없습니다."
        )

        return

    print()
    print("=" * 60)
    print(
        f"최종 선정: "
        f"{len(selected_articles)}개"
    )
    print("=" * 60)

    for index, article in enumerate(
        selected_articles,
        1
    ):

        print()
        print(
            f"{index}. "
            f"{article['title']}"
        )

        print(
            article["summary"]
        )

        print(
            f"출처: "
            f"{article['source']}"
        )

    # -----------------------------------------------------
    # Slack
    # -----------------------------------------------------

    send_slack(
        selected_articles
    )

    print("=" * 60)


if __name__ == "__main__":
    main()