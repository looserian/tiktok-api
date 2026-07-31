import os
import json
import asyncio
import logging
from typing import Dict, List, Optional, Tuple, Any
from playwright.async_api import async_playwright, Playwright, Browser, BrowserContext, Page, Response

from app.config import settings
from app.models import ProfileInfo, StoryItem
from app.parser import extract_stories_from_json, deduplicate_and_sort_stories

logger = logging.getLogger("tiktok_story_api.scraper")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Global browser manager singleton
_playwright_instance: Optional[Playwright] = None
_browser_instance: Optional[Browser] = None
_context_instance: Optional[BrowserContext] = None


async def get_browser_context() -> Tuple[Playwright, Browser, BrowserContext]:
    """Get or initialize the shared async Playwright browser context."""
    global _playwright_instance, _browser_instance, _context_instance

    if _playwright_instance is None or _browser_instance is None or not _browser_instance.is_connected():
        logger.info("Initializing Playwright Chromium instance...")
        _playwright_instance = await async_playwright().start()
        _browser_instance = await _playwright_instance.chromium.launch(
            headless=settings.PLAYWRIGHT_HEADLESS,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ]
        )
        _context_instance = await _browser_instance.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 720},
            locale="en-US",
            timezone_id="America/New_York",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.tiktok.com/",
            }
        )
        logger.info("Playwright browser context created successfully.")

    if _context_instance is None:
        _context_instance = await _browser_instance.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 720},
            locale="en-US"
        )

    return _playwright_instance, _browser_instance, _context_instance


async def close_browser():
    """Cleanup Playwright browser resources on shutdown."""
    global _playwright_instance, _browser_instance, _context_instance
    if _context_instance:
        await _context_instance.close()
        _context_instance = None
    if _browser_instance:
        await _browser_instance.close()
        _browser_instance = None
    if _playwright_instance:
        await _playwright_instance.stop()
        _playwright_instance = None
    logger.info("Playwright browser resources closed.")


def save_debug_artifacts(
    page_content: Optional[str] = None,
    network_urls: Optional[List[str]] = None,
    captured_responses: Optional[List[Dict[str, Any]]] = None
):
    """Save debugging files in screenshots/ directory when needed."""
    try:
        os.makedirs("screenshots", exist_ok=True)
        if page_content:
            with open("screenshots/debug.html", "w", encoding="utf-8") as f:
                f.write(page_content)

        if network_urls is not None:
            with open("screenshots/network.json", "w", encoding="utf-8") as f:
                json.dump(network_urls, f, indent=2)

        if captured_responses:
            with open("screenshots/story_response.json", "w", encoding="utf-8") as f:
                json.dump(captured_responses, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed saving debug artifacts: {e}")


class TikTokScraper:
    """Scrapes user stories and profile data using Playwright network interception."""

    def __init__(self, username: str):
        self.username = username.strip().lstrip("@")
        self.captured_payloads: List[Dict[str, Any]] = []
        self.network_urls: List[str] = []

    async def fetch_all_stories(self) -> Tuple[List[StoryItem], Optional[ProfileInfo]]:
        """
        Main method to navigate to TikTok profile, capture story network requests,
        handle pagination, parse story data, and return all active stories.
        """
        if not self.username:
            raise ValueError("Username cannot be empty")

        _, _, context = await get_browser_context()
        page: Page = await context.new_page()

        # Listen to response events BEFORE navigation
        async def on_response(response: Response):
            url = response.url
            self.network_urls.append(url)

            # Intercept Story API network responses
            if "/api/story/item_list/" in url or "/api/story/" in url:
                try:
                    if response.status == 200:
                        content_type = response.headers.get("content-type", "")
                        if "application/json" in content_type or "json" in content_type or "text/plain" in content_type:
                            data = await response.json()
                            if isinstance(data, dict):
                                logger.info(f"Captured Story API response from URL: {url}")
                                self.captured_payloads.append(data)
                except Exception as err:
                    logger.warning(f"Error parsing story network response: {err}")

        page.on("response", on_response)

        profile_url = f"https://www.tiktok.com/@{self.username}"
        logger.info(f"Navigating to TikTok profile: {profile_url}")

        try:
            # Navigate to user profile page
            res = await page.goto(
                profile_url,
                wait_until="domcontentloaded",
                timeout=settings.REQUEST_TIMEOUT * 1000
            )

            if res and res.status == 404:
                logger.warning(f"TikTok user @{self.username} not found (HTTP 404)")
                raise ValueError(f"TikTok account @{self.username} not found")

            # Wait briefly for background story API fetch to complete
            await page.wait_for_timeout(3000)

            # Check if page reports invalid / private user or page error
            page_title = await page.title()
            page_content = await page.content()

            if "Couldn't find this account" in page_content or "User not found" in page_content:
                raise ValueError(f"TikTok account @{self.username} not found")

            if "This account is private" in page_content:
                raise ValueError(f"TikTok account @{self.username} is private")

            # Also check page evaluation for embedded story/rehydration data if network call was not intercepted
            if not self.captured_payloads:
                logger.info("Attempting in-page rehydration data extraction...")
                embedded_json = await page.evaluate("""
                    () => {
                        const sigi = document.getElementById('SIGI_STATE');
                        if (sigi) return JSON.parse(sigi.textContent);
                        const rehydration = document.getElementById('__UNIVERSAL_DATA_FOR_REHYDRATION__');
                        if (rehydration) return JSON.parse(rehydration.textContent);
                        return null;
                    }
                """)
                if embedded_json and isinstance(embedded_json, dict):
                    self.captured_payloads.append(embedded_json)

            # PAGINATION / FETCH ALL STORIES
            # Check intercepted responses for hasMore / cursor pagination
            collected_stories: List[StoryItem] = []
            extracted_profile: Optional[ProfileInfo] = None
            reported_total: int = 0

            has_more = False
            max_cursor = None

            for payload in self.captured_payloads:
                st, pr, pag = extract_stories_from_json(payload, username=self.username)
                collected_stories.extend(st)
                if pr and (not extracted_profile or not extracted_profile.nickname):
                    extracted_profile = pr
                if pag.get("has_more"):
                    has_more = True
                    max_cursor = pag.get("max_cursor")
                if pag.get("total_count") > reported_total:
                    reported_total = pag.get("total_count")

            # If pagination indicates more stories exist, click on avatar/story circle or trigger scroll to load all
            if has_more and max_cursor:
                logger.info("TikTok reported additional story pages (hasMore=True). Attempting pagination interaction...")

                # Try clicking avatar story ring if present on page
                story_avatar_selector = '[data-e2e="user-avatar"], [class*="avatar"], div[class*="Story"]'
                try:
                    avatar_el = await page.query_selector(story_avatar_selector)
                    if avatar_el:
                        await avatar_el.click()
                        await page.wait_for_timeout(3000)
                except Exception as click_err:
                    logger.debug(f"Avatar story click attempt: {click_err}")

                # Scroll or wait for additional network requests
                for _ in range(3):
                    await page.mouse.wheel(0, 500)
                    await page.wait_for_timeout(1500)
                    # Re-evaluate payloads
                    for payload in self.captured_payloads:
                        st, _, _ = extract_stories_from_json(payload, username=self.username)
                        collected_stories.extend(st)

            # Save screenshot for debug if requested/failed
            try:
                os.makedirs("screenshots", exist_ok=True)
                await page.screenshot(path="screenshots/debug.png")
            except Exception:
                pass

            # Final deduplication and sorting
            final_stories = deduplicate_and_sort_stories(collected_stories)

            logger.info(f"Stories reported by TikTok: {reported_total or len(collected_stories)}")
            logger.info(f"Stories finally returned: {len(final_stories)}")

            # Save debug response json artifact
            save_debug_artifacts(
                page_content=page_content,
                network_urls=self.network_urls,
                captured_responses=self.captured_payloads
            )

            return final_stories, extracted_profile

        except Exception as exc:
            logger.error(f"Error scraping stories for @{self.username}: {exc}")
            # Try saving debug artifacts on failure
            try:
                content = await page.content()
                save_debug_artifacts(
                    page_content=content,
                    network_urls=self.network_urls,
                    captured_responses=self.captured_payloads
                )
            except Exception:
                pass
            raise exc
        finally:
            await page.close()
