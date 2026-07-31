import logging
from typing import Any, Dict, List, Optional, Tuple
from app.models import ProfileInfo, StoryItem

logger = logging.getLogger("tiktok_story_api.parser")


def get_nested(data: Any, *keys: str, default: Any = None) -> Any:
    """Safely retrieve nested keys from dictionaries/lists."""
    curr = data
    for k in keys:
        if isinstance(curr, dict) and k in curr:
            curr = curr[k]
        elif isinstance(curr, list) and isinstance(k, int) and 0 <= k < len(curr):
            curr = curr[k]
        else:
            return default
    return curr if curr is not None else default


def extract_url_from_list_or_str(val: Any) -> Optional[str]:
    """Extract a single string URL from various nested structures (url_list, dict, or str)."""
    if isinstance(val, str):
        return val
    if isinstance(val, list) and len(val) > 0:
        first = val[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            return first.get("url") or first.get("url_list", [None])[0]
    if isinstance(val, dict):
        if "url_list" in val and isinstance(val["url_list"], list) and len(val["url_list"]) > 0:
            return val["url_list"][0]
        if "url" in val:
            return val["url"]
    return None


def parse_author_profile(data: Dict[str, Any], default_username: str = "") -> ProfileInfo:
    """
    Parse author profile information from TikTok JSON payloads.
    Look in 'author', 'user', 'userInfo', 'authorStats', etc.
    """
    author = (
        data.get("author")
        or get_nested(data, "userInfo", "user")
        or get_nested(data, "storyDetails", 0, "author")
        or {}
    )

    stats = (
        data.get("authorStats")
        or get_nested(data, "userInfo", "stats")
        or get_nested(data, "stats")
        or {}
    )

    username = author.get("uniqueId") or author.get("unique_id") or default_username
    nickname = author.get("nickname")
    avatar = extract_url_from_list_or_str(
        author.get("avatarLarger")
        or author.get("avatarMedium")
        or author.get("avatarThumb")
        or author.get("avatar_thumb")
    )

    followers = stats.get("followerCount") or stats.get("follower_count")
    following = stats.get("followingCount") or stats.get("following_count")
    likes = stats.get("heartCount") or stats.get("heart") or stats.get("diggCount")
    videos = stats.get("videoCount") or stats.get("video_count")

    return ProfileInfo(
        username=username,
        nickname=nickname,
        avatar=avatar,
        followers=int(followers) if followers is not None else None,
        following=int(following) if following is not None else None,
        likes=int(likes) if likes is not None else None,
        videos=int(videos) if videos is not None else None,
    )


def parse_story_item(item: Dict[str, Any], username: str = "") -> Optional[StoryItem]:
    """
    Parse a single story object from TikTok JSON payload.
    Supports video stories, image stories, and image stories with audio.
    """
    if not isinstance(item, dict):
        return None

    # Story ID extraction
    story_id = str(
        item.get("id")
        or item.get("aweme_id")
        or item.get("story_id")
        or item.get("itemId")
        or ""
    ).strip()

    if not story_id:
        return None

    # Timestamps
    created_at = int(
        item.get("createTime")
        or item.get("created_at")
        or item.get("create_time")
        or 0
    )

    # TikTok story expiration is usually 24h after creation or specified in expiration field
    expiration = item.get("expiration") or item.get("expire_time") or item.get("expires_at")
    if expiration:
        expires_at = int(expiration)
    elif created_at > 0:
        # Default 24 hours in milliseconds
        expires_at = (created_at + 86400) * 1000
    else:
        expires_at = 0

    # Engagement stats
    stats = item.get("stats") or item.get("statistics") or {}
    views = stats.get("playCount") or stats.get("play_count") or item.get("views")
    likes = stats.get("diggCount") or stats.get("digg_count") or item.get("likes")

    # Audio/Music extraction
    music_obj = item.get("music") or item.get("audio") or item.get("music_info") or {}
    audio_url = None
    audio_duration = None

    if isinstance(music_obj, dict):
        audio_url = (
            music_obj.get("playUrl")
            or music_obj.get("play_url")
            or extract_url_from_list_or_str(music_obj.get("play_addr"))
        )
        raw_audio_dur = music_obj.get("duration")
        if raw_audio_dur is not None:
            try:
                dur_val = float(raw_audio_dur)
                audio_duration = dur_val / 1000.0 if dur_val > 500 else dur_val
            except (ValueError, TypeError):
                audio_duration = None

    # Detect if Image story or Video story
    # Check image_post_info / images
    image_post_info = item.get("image_post_info") or item.get("image_post") or item.get("images")
    images_list: List[str] = []

    if image_post_info:
        if isinstance(image_post_info, list):
            for img in image_post_info:
                url = extract_url_from_list_or_str(img)
                if url:
                    images_list.append(url)
        elif isinstance(image_post_info, dict):
            raw_images = image_post_info.get("images") or image_post_info.get("image_list") or []
            if isinstance(raw_images, list):
                for img in raw_images:
                    url = extract_url_from_list_or_str(img.get("display_image") or img)
                    if url:
                        images_list.append(url)

    if images_list:
        # Image story
        download_url = f"/download/{story_id}?username={username}&media=image" if username else None
        return StoryItem(
            id=story_id,
            type="image",
            created_at=created_at,
            expires_at=expires_at,
            images=images_list,
            video_url=None,
            download_url=download_url,
            cover=None,
            duration=None,
            views=int(views) if views is not None else None,
            likes=int(likes) if likes is not None else None,
            audio_url=audio_url,
            audio_duration=audio_duration,
        )

    # Video story parsing
    video_obj = item.get("video") or {}
    video_url = None
    cover = None
    duration = None

    if isinstance(video_obj, dict):
        video_url = (
            extract_url_from_list_or_str(video_obj.get("play_addr"))
            or extract_url_from_list_or_str(video_obj.get("download_addr"))
            or extract_url_from_list_or_str(video_obj.get("play_addr_h264"))
        )
        cover = extract_url_from_list_or_str(
            video_obj.get("cover")
            or video_obj.get("origin_cover")
            or video_obj.get("dynamic_cover")
        )
        raw_dur = video_obj.get("duration")
        if raw_dur is not None:
            try:
                dur_val = float(raw_dur)
                duration = dur_val / 1000.0 if dur_val > 500 else dur_val
            except (ValueError, TypeError):
                duration = None

    # Fallback to direct download_addr / play_addr at item level if video_obj not present
    if not video_url:
        video_url = extract_url_from_list_or_str(item.get("video_url") or item.get("play_url"))

    # If neither images nor video found, but story item exists, mark type based on video_url
    story_type = "video" if video_url else ("image" if images_list else "video")
    download_url = f"/download/{story_id}?username={username}&media={story_type}" if username else None

    return StoryItem(
        id=story_id,
        type=story_type,
        created_at=created_at,
        expires_at=expires_at,
        images=images_list if images_list else None,
        video_url=video_url,
        download_url=download_url,
        cover=cover,
        duration=duration,
        views=int(views) if views is not None else None,
        likes=int(likes) if likes is not None else None,
        audio_url=audio_url,
        audio_duration=audio_duration,
    )


def extract_stories_from_json(
    raw_payload: Dict[str, Any], username: str = ""
) -> Tuple[List[StoryItem], Optional[ProfileInfo], Dict[str, Any]]:
    """
    Extract list of StoryItems, ProfileInfo, and pagination info from a captured TikTok JSON response.
    """
    stories: List[StoryItem] = []
    profile: Optional[ProfileInfo] = None
    pagination: Dict[str, Any] = {
        "has_more": False,
        "max_cursor": None,
        "total_count": 0,
    }

    if not isinstance(raw_payload, dict):
        return stories, profile, pagination

    # Check pagination fields
    has_more = (
        raw_payload.get("hasMore")
        or raw_payload.get("has_more")
        or raw_payload.get("HasMoreAfter")
        or raw_payload.get("hasMoreAfter")
        or False
    )
    max_cursor = (
        raw_payload.get("maxCursor")
        or raw_payload.get("max_cursor")
        or raw_payload.get("cursor")
    )
    total_count = (
        raw_payload.get("totalCount")
        or raw_payload.get("total_count")
        or raw_payload.get("total")
        or 0
    )

    pagination["has_more"] = bool(has_more)
    pagination["max_cursor"] = max_cursor
    pagination["total_count"] = int(total_count) if total_count else 0

    # Extract profile info
    profile = parse_author_profile(raw_payload, default_username=username)

    # Extract items list candidates
    items_list = (
        raw_payload.get("storyDetails")
        or raw_payload.get("story_list")
        or raw_payload.get("items")
        or raw_payload.get("itemList")
        or raw_payload.get("aweme_list")
        or raw_payload.get("stories")
        or []
    )

    # Some TikTok payloads wrap items in storyDetails -> stories or items
    if isinstance(items_list, list):
        for raw_item in items_list:
            if isinstance(raw_item, dict):
                # Check nested story list inside detail object
                nested_items = raw_item.get("stories") or raw_item.get("items") or [raw_item]
                if isinstance(nested_items, list):
                    for sub_item in nested_items:
                        parsed = parse_story_item(sub_item, username=username)
                        if parsed:
                            stories.append(parsed)

    return stories, profile, pagination


def deduplicate_and_sort_stories(stories: List[StoryItem]) -> List[StoryItem]:
    """
    Remove duplicate story IDs and sort stories chronologically (most recent first).
    """
    seen_ids = set()
    unique_stories: List[StoryItem] = []

    for story in stories:
        if story.id not in seen_ids:
            seen_ids.add(story.id)
            unique_stories.append(story)

    # Sort descending by created_at (newest first)
    unique_stories.sort(key=lambda s: s.created_at, reverse=True)
    return unique_stories
