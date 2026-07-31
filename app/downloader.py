import os
import json
import logging
from typing import Dict, Optional, Tuple
import httpx

from app.scraper import get_browser_context, USER_AGENT
from app.models import StoryItem

logger = logging.getLogger("tiktok_story_api.downloader")

DATA_DIR = "data"
LAST_STORIES_FILE = os.path.join(DATA_DIR, "last_stories.json")


def load_last_stories() -> Dict[str, str]:
    """Safely load last stories state from data/last_stories.json."""
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(LAST_STORIES_FILE):
        return {}
    try:
        with open(LAST_STORIES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning(f"Failed loading last_stories.json: {e}")
        return {}


def save_last_story_id(username: str, story_id: str):
    """Save latest story ID for duplicate detection."""
    os.makedirs(DATA_DIR, exist_ok=True)
    current = load_last_stories()
    current[username] = story_id
    try:
        with open(LAST_STORIES_FILE, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)
    except Exception as e:
        logger.error(f"Failed writing to last_stories.json: {e}")


def get_last_story_id(username: str) -> Optional[str]:
    """Retrieve stored latest story ID for a username."""
    current = load_last_stories()
    return current.get(username)


async def fetch_media_binary(
    media_url: str, media_type: str, story_id: str
) -> Tuple[bytes, str, str]:
    """
    Fetch media binary using the Playwright browser context request API
    or httpx with custom browser cookies and headers to bypass TikTok 403 CDN restrictions.
    Returns: (binary_data, content_type, filename)
    """
    if not media_url:
        raise ValueError("Media URL is missing")

    logger.info(f"Downloading story media ({media_type}) for story ID {story_id} from {media_url[:60]}...")

    # Determine headers & filename
    if media_type == "video":
        content_type = "video/mp4"
        filename = f"story_{story_id}.mp4"
    elif media_type == "audio":
        content_type = "audio/mpeg"
        filename = f"story_{story_id}.mp3"
    else:  # image
        content_type = "image/jpeg"
        filename = f"story_{story_id}.jpg"

    # Attempt fetching using Playwright context request API (uses active browser cookies & headers)
    try:
        _, _, context = await get_browser_context()
        response = await context.request.get(
            media_url,
            headers={
                "Referer": "https://www.tiktok.com/",
                "User-Agent": USER_AGENT,
                "Accept": "*/*",
            },
            timeout=30000
        )
        if response.ok:
            data = await response.body()
            header_content_type = response.headers.get("content-type")
            if header_content_type and ("video" in header_content_type or "image" in header_content_type or "audio" in header_content_type):
                content_type = header_content_type
            logger.info(f"Successfully fetched {len(data)} bytes via Playwright context")
            return data, content_type, filename
        else:
            logger.warning(f"Playwright context request returned HTTP {response.status}, trying httpx fallback...")
    except Exception as exc:
        logger.warning(f"Playwright context fetch exception: {exc}, attempting httpx fallback...")

    # Fallback: httpx AsyncClient with TikTok browser headers
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": "https://www.tiktok.com/",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
    }
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        res = await client.get(media_url, headers=headers)
        if res.status_code == 200:
            header_content_type = res.headers.get("content-type")
            if header_content_type and ("video" in header_content_type or "image" in header_content_type or "audio" in header_content_type):
                content_type = header_content_type
            logger.info(f"Successfully fetched {len(res.content)} bytes via httpx client")
            return res.content, content_type, filename
        else:
            logger.error(f"Failed downloading media binary: HTTP {res.status_code}")
            raise ValueError(f"Failed to fetch media (HTTP {res.status_code})")
