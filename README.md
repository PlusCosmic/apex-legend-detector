# Apex Legends Character Detection System

This service uses computer vision to detect Apex Legends characters from gameplay screenshots using Redis task queues and Python workers.

## Architecture

```
API / Client Application
  ↓ (queues task via Redis)
Python Worker (worker.py)
  ↓ (downloads screenshots & runs CV detection)
Redis (stores results with TTL)
  ↑ (polls for results)
Client Application
```

## How It Works

1. **Client Application** - Queues detection task to Redis with clip ID + screenshot URLs
2. **worker.py** - Worker picks up task from `apex_detection_queue` using blocking pop
3. **detector.py** - Downloads screenshots asynchronously, extracts portrait region, compares against references
4. **worker.py** - Stores result back in Redis at `result:{task_id}` with 7-day TTL
5. **Client Application** - Polls Redis for completed task results

## Components

### detector.py
The core computer vision module that handles:
- **Async Image Downloading**: Uses aiohttp for concurrent screenshot downloads
- **Image Processing**: Resizes to 1080p and extracts portrait regions using OpenCV
- **Template Matching**: Compares extracted portraits against reference images using multiple algorithms
- **Confidence Scoring**: Averages scores from three different matching methods for robust detection

### worker.py
The Redis queue worker that:
- **Queue Processing**: Blocks on Redis queue (`brpop`) for incoming tasks
- **Task Execution**: Coordinates detection using the ApexDetector class
- **Result Storage**: Stores formatted results in Redis with TTL
- **Statistics Tracking**: Maintains daily counters for completed/failed tasks

## Portrait Setup

The detector requires reference portrait images for each Apex Legend:

1. Extract portrait images (92x74 pixels) from gameplay screenshots
2. Save as PNG files with character names (e.g., `Wraith.png`, `Pathfinder.png`, `Mad_Maggie.png`)
3. Copy to the `apex_portraits` Docker volume:

```bash
# Copy portraits to volume
docker run --rm -v apex_portraits:/portraits -v $(pwd)/your-portraits:/source alpine \
  cp -r /source/* /portraits/

# Verify portraits loaded
docker logs apex-legend-detector | grep "Loaded portrait"
```

### Portrait Naming Convention

Filenames should match character names (case-insensitive, underscores/hyphens converted to spaces):
- `Wraith.png` → "wraith"
- `Mad_Maggie.png` → "mad maggie"
- `Bloodhound.png` → "bloodhound"

## Deployment

### Using Docker

```bash
# Build the image
docker build -t apex-legend-detector .

# Run the worker
docker run -d \
  --name apex-legend-detector \
  -e REDIS_URL=redis://redis:6379/0 \
  -e LOG_LEVEL=INFO \
  -e MIN_CONFIDENCE=0.44 \
  -v apex_portraits:/app/portraits \
  apex-legend-detector
```

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export REDIS_URL=redis://localhost:6379/0
export LOG_LEVEL=INFO

# Run the worker
python worker.py
```

### Dependencies

- **redis** - Redis client for queue and result storage
- **aiohttp** - Async HTTP client for downloading screenshots
- **opencv-python-headless** - Computer vision library for template matching
- **numpy** - Numerical computing for image processing
- **pydantic** - Data validation for request/response models

## Configuration

### Environment Variables

- `REDIS_URL` - Redis connection string (default: `redis://localhost:6379/0`)
- `LOG_LEVEL` - Logging level (default: `INFO`)
- `PORTRAIT_REGION` - Screenshot crop region as `x,y,w,h` (default: `90,955,77,66`)
- `MIN_CONFIDENCE` - Minimum confidence threshold 0-1 (default: `0.44`)

## Detection Algorithm

1. **Download** screenshots asynchronously from provided URLs using aiohttp
2. **Resize** images to 1080p if necessary (maintaining aspect ratio)
3. **Extract** portrait region at configured coordinates (default: 90, 955, 77x66)
4. **Compare** extracted portrait against all reference portraits using:
   - Template Matching (TM_CCOEFF_NORMED)
   - Correlation (TM_CCORR_NORMED)
   - Squared Difference (TM_SQDIFF_NORMED)
5. **Average** scores from all three methods
6. **Return** best match across all screenshots if confidence ≥ configured threshold

## Usage

### Queue Detection Task

Push a task to the Redis queue `apex_detection_queue`:

```python
import redis
import json
import uuid

redis_client = redis.from_url('redis://localhost:6379/0')

task = {
    'task_id': str(uuid.uuid4()),
    'clip_id': '3fa85f64-5717-4562-b3fc-2c963f66afa6',
    'screenshot_urls': [
        'https://cdn.example.com/screenshot1.jpg',
        'https://cdn.example.com/screenshot2.jpg'
    ]
}

redis_client.lpush('apex_detection_queue', json.dumps(task))
```

### Detection Result Structure

Results stored in Redis at `result:{taskId}`:

```json
{
  "TaskId": "task-uuid",
  "VideoId": "clip-uuid",
  "Status": "completed",
  "Detections": [
    {
      "CharacterName": "Wraith",
      "Confidence": 0.92,
      "ScreenshotIndex": 0,
      "ScreenshotUrl": "https://cdn.example.com/screenshot1.jpg"
    }
  ],
  "BestOverall": {
    "CharacterName": "Wraith",
    "Confidence": 0.92,
    "ScreenshotIndex": 0,
    "ScreenshotUrl": "https://cdn.example.com/screenshot1.jpg"
  },
  "UniqueCharacters": ["Wraith"],
  "TotalScreenshots": 2,
  "SuccessfulDetections": 1,
  "CompletedAt": "2025-01-09T12:34:56.789Z",
  "Error": null
}
```

## Monitoring

### Check Worker Status

```bash
docker logs -f apex-legend-detector
```

### Check Redis Queue Length

```bash
docker exec -it redis redis-cli LLEN apex_detection_queue
```

### Check Task Result

```bash
docker exec -it redis redis-cli GET "result:your-task-id"
```

### View Stats

```bash
docker exec -it redis redis-cli GET "stats:completed:2025-01-09"
docker exec -it redis redis-cli GET "stats:failed:2025-01-09"
```

## Troubleshooting

**No portraits loaded:**
- Check volume mount: `docker inspect apex-legend-detector | grep Mounts -A 10`
- Verify PNG files in volume: `docker exec apex-legend-detector ls -la /app/portraits`

**Tasks not processing:**
- Verify worker running: `docker ps | grep apex-legend-detector`
- Check worker logs: `docker logs apex-legend-detector`
- Check Redis connectivity: Test with `redis-cli -h redis ping`
- Check queue: `redis-cli LLEN apex_detection_queue`

**Low confidence scores:**
- Adjust `MIN_CONFIDENCE` environment variable (lower = more permissive)
- Verify `PORTRAIT_REGION` coordinates match your screenshot resolution
- Ensure reference portraits are high quality and well-lit

**Character not detected:**
- Ensure portrait PNG filename matches character name exactly
- Review logs for "Loaded portrait for {name}" messages
- Verify the portrait reference images are high quality
