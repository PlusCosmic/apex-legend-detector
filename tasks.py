from celery import Celery
import os
import logging
import json
import redis
from datetime import datetime, timezone
from detector import ApexDetector

logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'))
logger = logging.getLogger(__name__)

redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
app = Celery('apex-detector', broker=redis_url, backend=redis_url)

app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    task_track_started=True,
    task_time_limit=300,
    worker_prefetch_multiplier=1,
    task_default_queue='apex_detection_queue',
)

redis_client = redis.from_url(redis_url, decode_responses=True)
detector = ApexDetector()

@app.task(bind=True, name='tasks.process_video_screenshots')
def process_video_screenshots(self, task_id, clip_id, screenshot_urls):
    """Process screenshots for character detection"""
    try:
        logger.info(f"Processing {len(screenshot_urls)} screenshots for clip {clip_id}")

        detections_list = []
        best_overall = None
        highest_confidence = 0
        unique_characters = set()
        successful_detections = 0

        result = detector.process_screenshots(screenshot_urls)

        if result:
            best_overall = {
                'CharacterName': result['character_name'],
                'Confidence': result['confidence'],
                'ScreenshotIndex': result['screenshot_index'],
                'ScreenshotUrl': result['url']
            }
            detections_list.append(best_overall)
            unique_characters.add(result['character_name'])
            successful_detections = 1

        response = {
            'TaskId': task_id,
            'VideoId': clip_id,
            'Status': 'completed',
            'Detections': detections_list,
            'BestOverall': best_overall,
            'UniqueCharacters': list(unique_characters),
            'TotalScreenshots': len(screenshot_urls),
            'SuccessfulDetections': successful_detections,
            'CompletedAt': datetime.now(timezone.utc).isoformat(),
            'Error': None
        }

        redis_client.setex(
            f"result:{task_id}",
            604800,
            json.dumps(response)
        )

        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        redis_client.incr(f"stats:completed:{today}")

        return response

    except Exception as e:
        logger.error(f"Task {task_id} failed: {str(e)}")

        error_result = {
            'TaskId': task_id,
            'VideoId': clip_id,
            'Status': 'failed',
            'Detections': [],
            'BestOverall': None,
            'UniqueCharacters': [],
            'TotalScreenshots': len(screenshot_urls),
            'SuccessfulDetections': 0,
            'CompletedAt': datetime.now(timezone.utc).isoformat(),
            'Error': str(e)
        }

        redis_client.setex(
            f"result:{task_id}",
            86400,
            json.dumps(error_result)
        )

        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        redis_client.incr(f"stats:failed:{today}")

        raise
