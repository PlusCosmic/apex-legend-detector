import os
import logging
import json
import redis
import time
from datetime import datetime, timezone
from detector import ApexDetector

logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'))
logger = logging.getLogger(__name__)

redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
redis_client = redis.from_url(redis_url, decode_responses=True)
detector = ApexDetector()

logger.info("Worker starting...")
logger.info(f"Connected to Redis at {redis_url}")

def process_task(task_data):
    """Process a single detection task"""
    task_id = task_data['task_id']
    clip_id = task_data['clip_id']
    screenshot_urls = task_data['screenshot_urls']

    try:
        logger.info(f"Processing task {task_id} for clip {clip_id} with {len(screenshot_urls)} screenshots")

        detections_list = []
        best_overall = None
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

        logger.info(f"Task {task_id} completed successfully. Best match: {best_overall['CharacterName'] if best_overall else 'None'}")
        return response

    except Exception as e:
        logger.error(f"Task {task_id} failed: {str(e)}", exc_info=True)

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

        return error_result

def main():
    """Main worker loop"""
    logger.info("Worker ready and waiting for tasks...")

    while True:
        try:
            task_json = redis_client.brpop('apex_detection_queue', timeout=5)

            if task_json:
                _, task_str = task_json
                task_data = json.loads(task_str)
                process_task(task_data)

        except KeyboardInterrupt:
            logger.info("Worker shutting down...")
            break
        except Exception as e:
            logger.error(f"Error in worker loop: {str(e)}", exc_info=True)
            time.sleep(1)

if __name__ == '__main__':
    main()
