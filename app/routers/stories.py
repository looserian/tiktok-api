import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query, Path, HTTPException, status
from fastapi.responses import Response, JSONResponse

from app.auth import verify_api_key
from app.models import StoriesResponse, LatestStoryResponse, ErrorResponse
from app.scraper import TikTokScraper
from app.downloader import (
    get_last_story_id,
    save_last_story_id,
    fetch_media_binary
)

logger = logging.getLogger("tiktok_story_api.stories")

router = APIRouter(tags=["Stories & Media"])


@router.get(
    "/stories",
    response_model=StoriesResponse,
    responses={
        200: {"model": StoriesResponse},
        401: {"model": ErrorResponse, "description": "Unauthorized - Missing or Invalid API Key"},
        404: {"model": ErrorResponse, "description": "User Not Found or No Active Stories"},
        500: {"model": ErrorResponse, "description": "Internal Server Error"},
    },
    summary="Get All Active Stories",
    description="Fetches all currently active video and image stories for a given TikTok username."
)
async def get_stories(
    username: str = Query(..., description="Public TikTok username (e.g. rtrt2805)"),
    api_key: str = Depends(verify_api_key)
):
    clean_username = username.strip().lstrip("@")
    if not clean_username:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "error": "Username cannot be empty"}
        )

    logger.info(f"Received request GET /stories for username: {clean_username}")

    try:
        scraper = TikTokScraper(username=clean_username)
        stories, profile = await scraper.fetch_all_stories()

        if not stories:
            logger.info(f"No active stories found for @{clean_username}")
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"success": False, "error": "No active stories"}
            )

        nickname = profile.nickname if profile else None
        avatar = profile.avatar if profile else None
        followers = profile.followers if profile else None
        following = profile.following if profile else None
        likes = profile.likes if profile else None
        videos = profile.videos if profile else None

        return StoriesResponse(
            success=True,
            username=clean_username,
            nickname=nickname,
            avatar=avatar,
            followers=followers,
            following=following,
            likes=likes,
            videos=videos,
            story_count=len(stories),
            stories=stories
        )

    except ValueError as ve:
        logger.warning(f"Validation error for @{clean_username}: {ve}")
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"success": False, "error": str(ve)}
        )
    except Exception as exc:
        logger.error(f"Unexpected error fetching stories for @{clean_username}: {exc}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": "Temporary failure fetching TikTok stories"}
        )


@router.get(
    "/stories/latest",
    response_model=LatestStoryResponse,
    responses={
        200: {"model": LatestStoryResponse},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        404: {"model": ErrorResponse, "description": "No active stories"},
    },
    summary="Get Latest Story with Duplicate Detection",
    description="Retrieves the newest active story and flags whether it is a new story compared to the last check."
)
async def get_latest_story(
    username: str = Query(..., description="Public TikTok username"),
    api_key: str = Depends(verify_api_key)
):
    clean_username = username.strip().lstrip("@")
    if not clean_username:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "error": "Username cannot be empty"}
        )

    logger.info(f"Received request GET /stories/latest for username: {clean_username}")

    try:
        scraper = TikTokScraper(username=clean_username)
        stories, _ = await scraper.fetch_all_stories()

        if not stories:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"success": False, "error": "No active stories"}
            )

        # Stories are sorted newest first
        latest = stories[0]
        stored_id = get_last_story_id(clean_username)

        if stored_id is None:
            # First time baseline run -> save and return new_story: False
            save_last_story_id(clean_username, latest.id)
            new_story = False
            logger.info(f"Baseline established for @{clean_username} with story ID {latest.id}")
        elif stored_id == latest.id:
            new_story = False
            logger.info(f"Story ID {latest.id} matches saved baseline for @{clean_username}")
        else:
            # New story detected -> update baseline and return new_story: True
            save_last_story_id(clean_username, latest.id)
            new_story = True
            logger.info(f"New story ID {latest.id} detected for @{clean_username}")

        return LatestStoryResponse(
            success=True,
            username=clean_username,
            new_story=new_story,
            latest_story=latest
        )

    except ValueError as ve:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"success": False, "error": str(ve)}
        )
    except Exception as exc:
        logger.error(f"Error fetching latest story for @{clean_username}: {exc}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": "Failed to fetch latest story"}
        )


@router.get(
    "/download/{story_id}",
    summary="Download Story Media Proxy",
    description="Protected media download endpoint that proxies TikTok media binary files to avoid 403 Forbidden CDN errors in n8n.",
    responses={
        200: {"description": "Binary media file response (video/mp4, image/jpeg, audio/mpeg)"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        404: {"model": ErrorResponse, "description": "Media not found"},
    }
)
async def download_story_media(
    story_id: str = Path(..., description="TikTok story item ID"),
    username: str = Query(..., description="TikTok username"),
    media: Optional[str] = Query(None, description="Media type to download: video, image, or audio"),
    api_key: str = Depends(verify_api_key)
):
    clean_username = username.strip().lstrip("@")
    clean_story_id = story_id.strip()

    logger.info(f"Media download requested for story {clean_story_id} (@{clean_username}, media={media})")

    # Fetch active stories for user to locate the target media URL
    try:
        scraper = TikTokScraper(username=clean_username)
        stories, _ = await scraper.fetch_all_stories()

        target_story = next((s for s in stories if s.id == clean_story_id), None)
        if not target_story:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"success": False, "error": f"Story ID {clean_story_id} not found for @{clean_username}"}
            )

        # Infer media type if omitted
        target_media_type = (media or "").lower().strip()
        if not target_media_type:
            target_media_type = "video" if target_story.type == "video" else "image"

        target_url: Optional[str] = None

        if target_media_type == "video":
            target_url = target_story.video_url
        elif target_media_type == "audio":
            target_url = target_story.audio_url
        elif target_media_type == "image":
            if target_story.images and len(target_story.images) > 0:
                target_url = target_story.images[0]

        if not target_url:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"success": False, "error": f"No {target_media_type} media available for story {clean_story_id}"}
            )

        binary_data, content_type, filename = await fetch_media_binary(
            media_url=target_url,
            media_type=target_media_type,
            story_id=clean_story_id
        )

        return Response(
            content=binary_data,
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "public, max-age=3600"
            }
        )

    except ValueError as ve:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"success": False, "error": str(ve)}
        )
    except Exception as exc:
        logger.error(f"Error serving media download for story {clean_story_id}: {exc}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": "Media download failure"}
        )
