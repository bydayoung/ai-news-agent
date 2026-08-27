import calendar
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
# GitHub Actions에서는 Repository Secret 사용
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

# 검색어별 최대 수집 개수
NEWS_PER_KEYWORD = 8

# Slack에 보낼 최대 뉴스 개수
MAX_SELECTED_NEWS = 5

# 동일 카테고리 최대 개수
MAX_NEWS_PER_CATEGORY = 3

# 최근 며칠 기사까지 볼지
LOOKBACK_DAYS = 7

# Slack에 표시할 기사 제목 최대 길이
MAX_TITLE_LENGTH = 80


# =========================================================
# 공통
# =========================================================

def clean_title(title, source):
    """Google News 제목 뒤의 ' - 출처명' 제거"""

    title = title.strip()

    if source:
        suffix = f" - {source}"

        if title.endswith(suffix):
            title = title[:-len(suffix)]

    return title.strip()


def normalize_title(title):
    """중복 비교를 위한 제목 정규화"""

    title = title.lower()
    title = re.sub(
        r"[^가-힣a-z0-9\s]",
        "",
        title,
    )
    title = re.sub(
        r"\s+",
        " ",
        title,
    )

    return title.strip()


def shorten_title(
    title,
    max_length=MAX_TITLE_LENGTH,
):
    """Slack에서 너무 긴 제목 축약"""

    if len(title) <= max_length:
        return title

    return (
        title[:max_length].rstrip()
        + "..."
    )


def format_published_date(article):
    """timestamp를 YYYY-MM-DD 형식으로 변환"""

    timestamp = article.get(
        "published_timestamp"
    )

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
    encoded_keyword = quote_plus(
        keyword
    )

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

    cutoff = (
        current_time
        - (
            LOOKBACK_DAYS
            * 24
            * 60
            * 60
        )
    )

    for entry in feed.entries:
        published_timestamp = None

        # 최근 LOOKBACK_DAYS 이내 기사만 사용
        if entry.get(
            "published_parsed"
        ):
            published_timestamp = (
                calendar.timegm(
                    entry.published_parsed
                )
            )

            if (
                published_timestamp
                < cutoff
            ):
                continue

        source = ""

        if entry.get("source"):
            source = entry.source.get(
                "title",
                "",
            )

        title = clean_title(
            entry.get(
                "title",
                "",
            ),
            source,
        )

        if not title:
            continue

        articles.append(
            {
                "title": title,
                "link": entry.get(
                    "link",
                    "",
                ),
                "published": entry.get(
                    "published",
                    "",
                ),
                "published_timestamp":
                    published_timestamp,
                "source":
                    source
                    or "출처 정보 없음",

                # 검색에 사용된 키워드는
                # 기록만 하고 점수에는 사용하지 않음
                "keyword": keyword,
            }
        )

        if (
            len(articles)
            >= NEWS_PER_KEYWORD
        ):
            break

    return articles


# =========================================================
# 2. 중복 제거
# =========================================================

def remove_duplicates(articles):
    seen = set()
    result = []

    for article in articles:
        normalized = normalize_title(
            article["title"]
        )

        if not normalized:
            continue

        if normalized in seen:
            continue

        seen.add(normalized)
        result.append(article)

    return result


# =========================================================
# 3. 규칙 기반 관련도 점수
# =========================================================

IMPORTANT_TERMS = {
    # Agent
    "coding agent": 5,
    "코딩 에이전트": 5,

    "computer use": 5,
    "computer use agent": 5,
    "컴퓨터 유즈": 5,

    "ai agent": 4,
    "ai 에이전트": 4,

    "agent": 3,
    "에이전트": 3,

    # Developer Tool
    "developer tool": 4,
    "개발자 도구": 4,

    # AI Education
    "ai tutor": 5,
    "ai 튜터": 5,

    "personalized learning": 4,
    "개인화 학습": 4,

    "assessment": 4,
    "평가": 4,

    # Developer Education
    "developer education": 4,
    "개발자 교육": 4,

    "coding education": 4,
    "코딩 교육": 4,

    # LLM / GenAI
    "llm": 3,
    "대규모 언어 모델": 3,

    "생성형 ai": 3,
    "generative ai": 3,

    "artificial intelligence": 2,

    # 일반적인 AI 언급은 낮은 점수
    "ai": 1,
}


# 주가·증권 중심 기사 감점
EXCLUDE_TERMS = [
    "주가",
    "급등",
    "급락",
    "목표주가",
    "투자의견",
    "증권",
]


def relevance_score(article):
    """
    기사 제목을 이용해 관련도를 계산하고
    최신 기사에는 추가 점수를 준다.
    """

    # 검색 키워드는 점수 계산에서 제외
    text = article[
        "title"
    ].lower()

    score = 0

    # -----------------------------------------------------
    # 업무 관련성
    # -----------------------------------------------------

    for (
        term,
        weight,
    ) in IMPORTANT_TERMS.items():

        if term.lower() in text:
            score += weight

    # -----------------------------------------------------
    # 불필요한 기사 감점
    # -----------------------------------------------------

    for term in EXCLUDE_TERMS:

        if term.lower() in text:
            score -= 10

    # -----------------------------------------------------
    # 최신성 점수
    #
    # 오늘 기사 → 약 +2
    # 3~4일 전 → 약 +1
    # 7일 전   → 약 +0
    # -----------------------------------------------------

    timestamp = (
        article.get(
            "published_timestamp"
        )
        or 0
    )

    freshness_score = 0

    if timestamp:
        age_days = (
            time.time()
            - timestamp
        ) / (
            24
            * 60
            * 60
        )

        age_days = max(
            0,
            age_days,
        )

        freshness_score = max(
            0,
            2
            * (
                1
                - (
                    age_days
                    / LOOKBACK_DAYS
                )
            ),
        )

    return (
        score
        + freshness_score
    )


# =========================================================
# 4. 뉴스 카테고리 분류
# =========================================================

def classify_category(article):
    """
    기사 제목을 기준으로
    간단한 카테고리 분류
    """

    title = article[
        "title"
    ].lower()

    # -----------------------------------------------------
    # 개발자 교육
    # -----------------------------------------------------

    developer_education_terms = [
        "developer education",
        "developer training",
        "coding education",
        "개발자 교육",
        "개발자 훈련",
        "코딩 교육",
    ]

    if any(
        term in title
        for term
        in developer_education_terms
    ):
        return "DEVELOPER_EDUCATION"

    # -----------------------------------------------------
    # AI 교육 / 평가
    # -----------------------------------------------------

    ai_education_terms = [
        "ai tutor",
        "ai 튜터",
        "personalized learning",
        "개인화 학습",
        "ai assessment",
        "교육 평가",
        "학습 평가",
        "ai education",
        "ai 교육",
    ]

    if any(
        term in title
        for term
        in ai_education_terms
    ):
        return "AI_EDUCATION"

    # -----------------------------------------------------
    # AI Agent
    # -----------------------------------------------------

    agent_terms = [
        "coding agent",
        "코딩 에이전트",
        "computer use",
        "ai agent",
        "ai 에이전트",
        "agent",
        "에이전트",
    ]

    if any(
        term in title
        for term
        in agent_terms
    ):
        return "AI_AGENT"

    # -----------------------------------------------------
    # 그 외 AI / LLM
    # -----------------------------------------------------

    return "AI_GENERAL"


# =========================================================
# 5. 최종 뉴스 선정
# =========================================================

def select_news(articles):
    """
    관련도 + 최신성 점수가 높은 순으로 선정하되
    동일 카테고리는 최대 3개까지만 선정한다.
    """

    scored_articles = []

    # -----------------------------------------------------
    # 점수 + 카테고리 계산
    # -----------------------------------------------------

    for article in articles:
        score = relevance_score(
            article
        )

        # 관련성이 거의 없는 뉴스 제외
        if score <= 0:
            continue

        article["category"] = (
            classify_category(
                article
            )
        )

        scored_articles.append(
            (
                article,
                score,
            )
        )

    # -----------------------------------------------------
    # 정렬
    #
    # 1순위: 관련도 + 최신성 점수
    # 2순위: 발행 시간
    # -----------------------------------------------------

    scored_articles.sort(
        key=lambda item: (
            item[1],
            item[0].get(
                "published_timestamp"
            )
            or 0,
        ),
        reverse=True,
    )

    # -----------------------------------------------------
    # 카테고리 쏠림 방지
    # -----------------------------------------------------

    selected = []

    category_count = {}

    for (
        article,
        score,
    ) in scored_articles:

        category = article[
            "category"
        ]

        current_count = (
            category_count.get(
                category,
                0,
            )
        )

        # 동일 카테고리 최대 3개
        if (
            current_count
            >= MAX_NEWS_PER_CATEGORY
        ):
            continue

        selected.append(
            article
        )

        category_count[
            category
        ] = (
            current_count
            + 1
        )

        if (
            len(selected)
            >= MAX_SELECTED_NEWS
        ):
            break

    return selected


# =========================================================
# 6. Slack Block Kit
# =========================================================

def build_slack_blocks(articles):
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": (
                    "☁️ AI & Education "
                    "Weekly Briefing"
                ),
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "🔥 *이번 주 주요 뉴스*\n"
                    "AI · Agent · 교육 · "
                    "개발자 교육 관련 "
                    f"뉴스 {len(articles)}개를 "
                    "모았습니다."
                ),
            },
        },
        {
            "type": "divider",
        },
    ]

    for (
        index,
        article,
    ) in enumerate(
        articles,
        1,
    ):

        article_link = (
            f"<{article['link']}|"
            f"🔗 기사 읽기>"
            if article.get("link")
            else "기사 링크 없음"
        )

        published_date = (
            format_published_date(
                article
            )
        )

        title = shorten_title(
            article["title"]
        )

        text = (
            f"*{index}. {title}*\n"
            f"_출처: "
            f"{article['source']} "
            f"· {published_date}_\n"
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

        blocks.append(
            {
                "type": "divider",
            }
        )

    return blocks


# =========================================================
# 7. Slack 전송
# =========================================================

def send_slack(articles):
    if not SLACK_WEBHOOK_URL:
        raise RuntimeError(
            "SLACK_WEBHOOK_URL이 없습니다. "
            "GitHub Repository Secret 또는 "
            ".env를 확인하세요."
        )

    if not articles:
        print(
            "Slack으로 보낼 뉴스가 없습니다."
        )
        return

    payload = {
        "text": (
            "☁️ AI & Education "
            "Weekly Briefing"
        ),
        "blocks": (
            build_slack_blocks(
                articles
            )
        ),
    }

    response = requests.post(
        SLACK_WEBHOOK_URL,
        json=payload,
        timeout=15,
    )

    response.raise_for_status()

    print(
        "✅ Slack 전송 완료"
    )


# =========================================================
# Main
# =========================================================

def main():
    print(
        "=" * 60
    )

    print(
        "AI & Education Weekly News"
    )

    print(
        "=" * 60
    )

    all_articles = []

    print(
        f"\n최근 {LOOKBACK_DAYS}일 "
        "뉴스 수집 시작\n"
    )

    # -----------------------------------------------------
    # 뉴스 수집
    # -----------------------------------------------------

    for keyword in KEYWORDS:
        print(
            f"[검색] {keyword}"
        )

        try:
            articles = (
                get_google_news(
                    keyword
                )
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

    all_articles = (
        remove_duplicates(
            all_articles
        )
    )

    print(
        f"\n중복 제거 후 뉴스: "
        f"{len(all_articles)}개"
    )

    if not all_articles:
        print(
            "최근 뉴스가 없습니다."
        )
        return

    # -----------------------------------------------------
    # 최종 선정
    # -----------------------------------------------------

    selected_articles = (
        select_news(
            all_articles
        )
    )

    print(
        f"\n최종 선정: "
        f"{len(selected_articles)}개"
    )

    # -----------------------------------------------------
    # 결과 확인
    # -----------------------------------------------------

    for (
        index,
        article,
    ) in enumerate(
        selected_articles,
        1,
    ):

        score = relevance_score(
            article
        )

        print()

        print(
            f"{index}. "
            f"{article['title']}"
        )

        print(
            f"   카테고리: "
            f"{article['category']}"
        )

        print(
            f"   점수: "
            f"{score:.2f}"
        )

        print(
            f"   출처: "
            f"{article['source']}"
        )

        print(
            f"   URL: "
            f"{article['link']}"
        )

    # -----------------------------------------------------
    # Slack
    # -----------------------------------------------------

    send_slack(
        selected_articles
    )


if __name__ == "__main__":
    main()