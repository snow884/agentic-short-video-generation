"""Collect platform analytics for uploaded videos."""

import os
from typing import Any, Dict, List

from prefect import task
from prefect.logging import get_run_logger

from sql_utils import get_db
from tables import Video

try:
    from upload_post import UploadPostClient
except ImportError:  # pragma: no cover - optional dependency
    UploadPostClient = None


@task(task_run_name="collect-video-analytics-{video_id}")
def main(video_id: int):
    """Fetch analytics for each published URL attached to a video record.

    Args:
        video_id: Identifier of the video whose published URLs should be analyzed.

    Returns:
        The updated video record object.
    """

    logger = get_run_logger()
    session = next(get_db())

    video = session.query(Video).filter(Video.id == video_id).first()
    if video is None:
        logger.info(f"No video found for id {video_id}")
        return None

    if UploadPostClient is None:
        logger.info("UploadPost client is not available; skipping analytics collection")
        return video

    client = UploadPostClient(api_key=os.environ.get("UPLOAD_POST_API_KEY"))
    urls = [value for value in [video.instagram_url, video.youtube_url, video.tiktok_url] if value]
    summaries: List[Dict[str, Any]] = []

    for url in urls:
        analytics = client.get_post_analytics(url)
        if not analytics:
            continue

        platform = _infer_platform(url)
        summaries.append(
            {
                "platform": platform,
                "url": url,
                "views": analytics.get("views", 0),
                "likes": analytics.get("likes", 0),
                "comments": analytics.get("comments", 0),
                "shares": analytics.get("shares", 0),
                "watch_time_seconds": analytics.get("watch_time_seconds", 0),
            }
        )

        if platform == "instagram":
            video.views_count = analytics.get("views", 0)
            video.likes_count = analytics.get("likes", 0)
            video.comments_count = analytics.get("comments", 0)
            video.shares_count = analytics.get("shares", 0)
            video.watch_time_seconds = analytics.get("watch_time_seconds", 0)

    video.analytics_summary = _render_summary(summaries)
    session.commit()
    session.close()

    return video


def _infer_platform(url: str) -> str:
    """Infer the platform name from a published URL."""

    lowered = url.lower()
    if "instagram" in lowered:
        return "instagram"
    if "youtube" in lowered or "youtu.be" in lowered:
        return "youtube"
    if "tiktok" in lowered:
        return "tiktok"
    return "unknown"


def _render_summary(summaries: List[Dict[str, Any]]) -> str:
    """Convert analytics rows into a human-readable summary string."""

    if not summaries:
        return "No analytics collected"

    lines = []
    for summary in summaries:
        lines.append(
            f"{summary['platform']}: views={summary['views']}, likes={summary['likes']}, "
            f"comments={summary['comments']}, shares={summary['shares']}, "
            f"watch_time_seconds={summary['watch_time_seconds']}"
        )
    return " | ".join(lines)
