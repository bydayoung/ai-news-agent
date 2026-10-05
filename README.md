# ☁️ AI & Education Weekly News Agent

> AI · LLM Agent · AI Education 관련 주요 뉴스를 자동으로 수집하고  
> 업무 관련성이 높은 뉴스를 선별하여 Slack으로 전달하는 News Curation Agent

---

## 📌 Overview

매주 쏟아지는 AI 뉴스를 직접 찾아보는 대신,

**AI Agent / Developer Tool / AI Education / Developer Education**과 관련된 뉴스를 자동으로 수집하고  
관련도와 최신성을 기준으로 핵심 뉴스만 선별하여 Slack으로 전달합니다.

GitHub Actions를 통해 자동 실행할 수 있도록 구성되어 있어  
별도의 서버 없이 정기적인 뉴스 브리핑을 받을 수 있습니다.

---

## ✨ Features

### 🔎 AI News Collection

Google News RSS를 활용하여 주요 AI 관련 키워드의 뉴스를 수집합니다.

주요 관심 분야:

- AI Agent
- LLM Agent
- AI Coding Agent
- Computer Use AI
- AI Education
- AI Tutor
- Personalized Learning
- AI Assessment
- Developer Education
- Coding Education
- AI Developer Training

---

### 🧹 Duplicate Filtering

여러 검색 키워드에서 동일한 뉴스가 반복적으로 수집될 수 있기 때문에  
기사 제목을 정규화하여 중복 뉴스를 제거합니다.

---

### 🎯 Relevance Ranking

수집된 모든 뉴스를 그대로 전달하지 않고  
업무 관련성과 최신성을 기준으로 우선순위를 계산합니다.

```text
AI Coding Agent     █████
Computer Use Agent  █████
AI Tutor            █████
AI Agent            ████
Developer Tool      ████
AI Education        ████
LLM                 ███
AI                  █
```

주가·증권 등 AI 업무와 직접적인 관련성이 낮은 뉴스는 우선순위를 낮춥니다.

---

### 🗂 Category Balancing

특정 분야의 뉴스만 과도하게 선택되지 않도록 뉴스를 다음 카테고리로 분류합니다.

```text
AI_AGENT
AI_EDUCATION
DEVELOPER_EDUCATION
AI_GENERAL
```

동일 카테고리의 뉴스 수를 제한하여  
다양한 분야의 뉴스를 한 번에 확인할 수 있도록 구성했습니다.

---

### 💬 Slack Weekly Briefing

최종 선정된 뉴스는 Slack Block Kit 형식으로 전달됩니다.

```text
☁️ AI & Education Weekly Briefing

🔥 이번 주 주요 뉴스
AI · Agent · 교육 · 개발자 교육 관련 뉴스 5개를 모았습니다.

1. News Title
   Source · Published Date
   🔗 기사 읽기

2. News Title
   Source · Published Date
   🔗 기사 읽기
```

최대 **5개의 핵심 뉴스**를 전달합니다.

---

## ⚙️ Pipeline

```text
Google News RSS
      │
      ▼
Keyword-based Collection
      │
      ▼
Recent News Filtering
      │
      ▼
Duplicate Removal
      │
      ▼
Relevance + Freshness Scoring
      │
      ▼
Category Classification
      │
      ▼
Top News Selection
      │
      ▼
Slack Weekly Briefing
```

---

## 🛠 Tech Stack

| Category | Technology |
|---|---|
| Language | Python |
| News Source | Google News RSS |
| RSS Parser | feedparser |
| HTTP Client | requests |
| Notification | Slack Incoming Webhook |
| Message UI | Slack Block Kit |
| Automation | GitHub Actions |
| Environment | python-dotenv |

---

## 🚀 Setup

### 1. Clone Repository

```bash
git clone <repository-url>
cd <repository-name>
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Slack Webhook

로컬 실행 시 `.env` 파일에 Slack Webhook URL을 설정합니다.

```env
SLACK_WEBHOOK_URL=your_slack_webhook_url
```

GitHub Actions에서 실행할 경우 Repository Secret에 다음 값을 등록합니다.

```text
SLACK_WEBHOOK_URL
```

---

## ▶️ Run

```bash
python news.py
```

실행하면 다음 순서로 처리됩니다.

```text
뉴스 수집
→ 중복 제거
→ 관련도 계산
→ 카테고리 분류
→ 주요 뉴스 선정
→ Slack 전송
```

---

## 🔐 Environment Variables

| Variable | Description |
|---|---|
| `SLACK_WEBHOOK_URL` | Slack Incoming Webhook URL |

Webhook URL은 코드에 직접 작성하지 않고  
환경 변수 또는 GitHub Repository Secret으로 관리합니다.

---

## 📂 Project Structure

```text
.
├── news.py
├── requirements.txt
├── .env
└── .github/
    └── workflows/
        └── news.yml
```

---

## 🎯 Purpose

정보가 빠르게 변화하는 AI 분야에서  
모든 뉴스를 직접 확인하지 않고도 업무와 관련된 핵심 변화만 빠르게 파악하는 것을 목표로 합니다.

특히 다음 분야의 동향을 지속적으로 확인할 수 있도록 설계했습니다.

- AI / LLM
- AI Agent
- Coding Agent
- Developer Tool
- AI Education
- Personalized Learning
- Developer Education

---

## 📬 Output

**Slack**

```text
☁️ AI & Education Weekly Briefing
```

관련도와 최신성을 기준으로 선정된 AI 뉴스를  
Slack 채널에서 정기적으로 확인할 수 있습니다.
