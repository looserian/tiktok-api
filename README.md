# TikTok Story API 🚀

A lightweight, self-hosted FastAPI service that scrapes active TikTok user stories (videos, photos, and photo stories with background audio), handles pagination, tracks story changes for n8n automations, and proxies media downloads to bypass TikTok CDN `HTTP 403 Forbidden` restrictions.

---

## 📁 Project Structure

```
tiktok-story-api/
│
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI app initialization, lifespan, OpenAPI setup
│   ├── config.py        # Environment settings (pydantic-settings)
│   ├── auth.py          # API key authentication (X-API-Key or Bearer)
│   ├── models.py        # Pydantic data schemas & response models
│   ├── scraper.py       # Playwright browser manager & network interceptor
│   ├── parser.py        # TikTok Story JSON parser & extractor
│   ├── downloader.py     # Authenticated proxy media fetcher & state storage
│   └── routers/
│       ├── __init__.py
│       ├── health.py    # Public endpoints (GET / and GET /health)
│       └── stories.py   # Protected endpoints (/stories, /stories/latest, /download)
│
├── data/
│   └── last_stories.json# Persistent store for duplicate story detection
│
├── screenshots/         # Auto-created directory for debug artifacts
├── requirements.txt     # Pinned Python dependencies
├── Dockerfile           # Playwright Python noble Docker image build definition
├── docker-compose.yml   # Docker compose configuration
├── .env.example         # Environment template
├── .gitignore           # Git ignore configuration
└── README.md            # Comprehensive documentation
```

---

## ⚙️ Environment Variables

The application configures settings via `pydantic-settings` from `.env` or container environment variables:

| Variable | Default | Description |
| :--- | :--- | :--- |
| `API_KEYS` | *(Required)* | Comma-separated list of valid secret API keys (e.g. `secret-key-1,secret-key-2`) |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `REQUEST_TIMEOUT` | `30` | Playwright page navigation timeout in seconds |
| `MAX_RETRIES` | `3` | Maximum scraper retry attempts |
| `PLAYWRIGHT_HEADLESS` | `true` | Run Chromium in headless mode |

---

## 🚀 Running Locally

### Prerequisites
- Python 3.12+
- Playwright browsers installed locally (for non-docker local development)

### Setup Steps

1. **Clone & install dependencies**:
   ```bash
   git clone <your-repo-url>
   cd tiktok-story-api
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   playwright install chromium
   ```

2. **Configure Environment**:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and set `API_KEYS`:
   ```env
   API_KEYS=my-secret-key-123
   LOG_LEVEL=INFO
   REQUEST_TIMEOUT=30
   PLAYWRIGHT_HEADLESS=true
   ```

3. **Start Development Server**:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

4. Access OpenAPI Swagger Docs at `http://localhost:8000/docs`.

---

## 🐳 Docker Setup

The build uses the official `mcr.microsoft.com/playwright/python:v1.49.1-noble` image. Playwright versions are explicitly pinned between `requirements.txt` and `Dockerfile`.

### Build & Run with Docker Compose

```bash
docker compose up -d --build
```

### Build & Run directly with Docker

```bash
docker build -t tiktok-story-api .
docker run -d \
  --name tiktok-story-api \
  -p 8000:8000 \
  -e API_KEYS="my-secret-key-123" \
  -v $(pwd)/data:/app/data \
  tiktok-story-api
```

---

## ☁️ Deployment on Coolify

1. Push this repository to GitHub or GitLab.
2. In Coolify:
   - Create a new **Public / Private GitHub Repository** resource.
   - Set Build Pack to **Docker Compose** or **Dockerfile**.
   - Expose Port: `8000`.
3. Set Environment Variables in Coolify UI:
   ```env
   API_KEYS=your-coolify-secret-key
   LOG_LEVEL=INFO
   REQUEST_TIMEOUT=30
   PLAYWRIGHT_HEADLESS=true
   ```
4. Attach a domain with HTTPS certificate (e.g. `https://tiktok-api.yourdomain.com`).
5. Deploy the application.

---

## 🔐 API Authentication

All protected endpoints require an API Key supplied in either:

- Header: `X-API-Key: YOUR_KEY` *(Recommended)*
- Header: `Authorization: Bearer YOUR_KEY`

If missing or invalid, the API returns `401 Unauthorized`:
```json
{
  "success": false,
  "error": "Invalid API key"
}
```

---

## 📖 API Endpoints & `curl` Examples

### 1. Root Information (Public)
`GET /`

```bash
curl -X GET "http://localhost:8000/"
```
**Response**:
```json
{
  "name": "TikTok Story API",
  "version": "1.0.0",
  "status": "running"
}
```

### 2. Health Check (Public)
`GET /health`

```bash
curl -X GET "http://localhost:8000/health"
```
**Response**:
```json
{
  "status": "ok",
  "version": "1.0.0"
}
```

### 3. Get All Active Stories (Protected)
`GET /stories?username=rtrt2805`

```bash
curl -X GET "http://localhost:8000/stories?username=rtrt2805" \
  -H "X-API-Key: my-secret-key-123"
```

**Response**:
```json
{
  "success": true,
  "username": "rtrt2805",
  "nickname": "User Nickname",
  "avatar": "https://...",
  "followers": 2249,
  "following": 3,
  "likes": 12200,
  "videos": 40,
  "story_count": 2,
  "stories": [
    {
      "id": "7667154335628889365",
      "type": "video",
      "created_at": 1785148493,
      "expires_at": 1785234893000,
      "images": null,
      "video_url": "https://...",
      "download_url": "/download/7667154335628889365?username=rtrt2805&media=video",
      "cover": "https://...",
      "duration": 10,
      "views": 38,
      "likes": 8,
      "audio_url": null,
      "audio_duration": null
    },
    {
      "id": "7667153728281120021",
      "type": "image",
      "created_at": 1785148348,
      "expires_at": 1785234748000,
      "images": [
        "https://..."
      ],
      "video_url": null,
      "download_url": "/download/7667153728281120021?username=rtrt2805&media=image",
      "cover": null,
      "duration": null,
      "views": 15,
      "likes": 3,
      "audio_url": "https://...",
      "audio_duration": 15
    }
  ]
}
```

### 4. Get Latest Story with Duplicate Detection (Protected)
`GET /stories/latest?username=rtrt2805`

```bash
curl -X GET "http://localhost:8000/stories/latest?username=rtrt2805" \
  -H "X-API-Key: my-secret-key-123"
```

**First Run Response** (`new_story: false` to establish baseline):
```json
{
  "success": true,
  "username": "rtrt2805",
  "new_story": false,
  "latest_story": {
    "id": "7667154335628889365",
    "type": "video",
    "created_at": 1785148493,
    "expires_at": 1785234893000,
    "download_url": "/download/7667154335628889365?username=rtrt2805&media=video"
  }
}
```

### 5. Download Story Media Binary Proxy (Protected)
`GET /download/{story_id}?username=rtrt2805&media=video`

```bash
curl -X GET "http://localhost:8000/download/7667154335628889365?username=rtrt2805&media=video" \
  -H "X-API-Key: my-secret-key-123" \
  --output story.mp4
```

Supported `media` parameter options:
- `video`: Download `.mp4` video binary
- `image`: Download `.jpg` image binary
- `audio`: Download `.mp3` audio binary (for image stories containing background music)

---

## ⚡ n8n Workflow Integration

### Workflow Architecture

```
[ Schedule Trigger ]
       ↓
[ HTTP Request: GET /stories/latest?username=... ]
       ↓
[ IF Node: {{ $json.new_story }} == true ]
       │
       ├─ (TRUE) ──> [ Switch Node by {{ $json.latest_story.type }} ]
       │                    ├─ video ─> [ HTTP Request Download Video ] ─> [ Telegram Send Video ]
       │                    └─ image ─> [ HTTP Request Download Image ] ─> [ Telegram Send Photo ]
       │                                     └─ IF audio_url ─> [ HTTP Request Download Audio ] ─> [ Telegram Send Audio ]
       │
       └─ (FALSE) ──> (Stop / Do nothing)
```

### Essential n8n Expressions

- **Check New Story**:
  `{{ $json.new_story }}` (boolean `true` / `false`)

- **Newest Story ID**:
  `{{ $json.latest_story.id }}`

- **Story Type**:
  `{{ $json.latest_story.type }}` (`"video"` or `"image"`)

- **Has Audio (Image Story)**:
  `{{ $json.latest_story.audio_url != null }}`

- **Video Download URL**:
  `https://your-api-domain.com/download/{{ $json.latest_story.id }}?username={{ $json.username }}&media=video`

- **Image Download URL**:
  `https://your-api-domain.com/download/{{ $json.latest_story.id }}?username={{ $json.username }}&media=image`

- **Audio Download URL**:
  `https://your-api-domain.com/download/{{ $json.latest_story.id }}?username={{ $json.username }}&media=audio`

- **Telegram Header / Caption**:
  `New story from @{{ $json.username }}! Created at: {{ new Date($json.latest_story.created_at * 1000).toLocaleString() }}`
