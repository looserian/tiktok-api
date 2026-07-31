from typing import List, Optional
from pydantic import BaseModel, Field


class StoryItem(BaseModel):
    id: str = Field(..., description="Unique story ID from TikTok")
    type: str = Field(..., description="Story type: 'video' or 'image'")
    created_at: int = Field(0, description="Creation timestamp in Unix seconds")
    expires_at: int = Field(0, description="Expiration timestamp in Unix milliseconds/seconds")
    images: Optional[List[str]] = Field(None, description="Array of image URLs for photo stories")
    video_url: Optional[str] = Field(None, description="Video stream URL for video stories")
    download_url: Optional[str] = Field(None, description="Internal proxy download URL or direct video URL")
    cover: Optional[str] = Field(None, description="Video cover frame image URL")
    duration: Optional[float] = Field(None, description="Video story duration in seconds")
    views: Optional[int] = Field(None, description="Story view count if available")
    likes: Optional[int] = Field(None, description="Story like count if available")
    audio_url: Optional[str] = Field(None, description="Background audio URL for image stories with music")
    audio_duration: Optional[float] = Field(None, description="Audio duration in seconds")


class ProfileInfo(BaseModel):
    username: str
    nickname: Optional[str] = None
    avatar: Optional[str] = None
    followers: Optional[int] = None
    following: Optional[int] = None
    likes: Optional[int] = None
    videos: Optional[int] = None


class StoriesResponse(BaseModel):
    success: bool = True
    username: str
    nickname: Optional[str] = None
    avatar: Optional[str] = None
    followers: Optional[int] = None
    following: Optional[int] = None
    likes: Optional[int] = None
    videos: Optional[int] = None
    story_count: int
    stories: List[StoryItem]


class LatestStoryResponse(BaseModel):
    success: bool = True
    username: str
    new_story: bool
    latest_story: Optional[StoryItem] = None


class ErrorResponse(BaseModel):
    success: bool = False
    error: str


class RootStatusResponse(BaseModel):
    name: str = "TikTok Story API"
    version: str = "1.0.0"
    status: str = "running"


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
