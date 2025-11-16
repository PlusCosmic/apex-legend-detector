# Apex Legends Character Detection System

This service uses computer vision to detect Apex Legends characters from gameplay screenshots using Celery task queues.

## Architecture

```
C# API (Nucleus.Apex)
  ↓ (queues task via Redis)
Celery Worker (Python)
  ↓ (downloads screenshots & runs CV detection)
Redis (stores results)
  ↑ (polls for results)
C# Background Service
```

## How It Works

1. **DetectionEndpoints.cs** - API receives clip ID + screenshot URLs
2. **DetectionQueueService.cs** - Creates Celery task and pushes to Redis queue
3. **tasks.py** - Celery worker picks up task from Redis
4. **detector.py** - Downloads screenshots, extracts portrait region, compares against references
5. **tasks.py** - Stores result back in Redis with 7-day TTL
6. **DetectionBackgroundService.cs** - Polls Redis every 5 seconds for completed tasks
7. **ApexStatements.cs** - Updates database with detected character

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

## Configuration

### Environment Variables

**apex-legend-detector service:**
- `REDIS_URL` - Redis connection string (default: `redis://redis:6379/0`)
- `LOG_LEVEL` - Logging level (default: `INFO`)
- `PORTRAIT_REGION` - Screenshot crop region as `x,y,w,h` (default: `80,955,92,74`)
- `MIN_CONFIDENCE` - Minimum confidence threshold 0-1 (default: `0.7`)

**nucleus-apex service:**
- `RedisConnectionString` - Redis host:port (default: `redis:6379`)

## Detection Algorithm

1. **Download** screenshot from provided URL
2. **Extract** portrait region at coordinates (80, 955) with size 92x74
3. **Compare** extracted portrait against all reference portraits using:
   - Template Matching (TM_CCOEFF_NORMED)
   - Correlation (TM_CCORR_NORMED)
   - Squared Difference (TM_SQDIFF_NORMED)
4. **Average** scores from all three methods
5. **Return** best match if confidence ≥ 0.7

## API Usage

### Queue Detection Task

```http
POST /api/apexdetection/enqueue
Content-Type: application/json

{
  "clipId": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "screenshotUrls": [
    "https://cdn.example.com/screenshot1.jpg",
    "https://cdn.example.com/screenshot2.jpg"
  ]
}
```

**Limits:**
- Maximum 10 screenshots per request
- Task timeout: 300 seconds

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
      "ScreenshotUrl": "https://..."
    }
  ],
  "BestOverall": { ... },
  "UniqueCharacters": ["Wraith"],
  "TotalScreenshots": 2,
  "SuccessfulDetections": 1,
  "CompletedAt": "2025-01-09T12:34:56.789Z",
  "Error": null
}
```

## Database Schema

```sql
CREATE TABLE apex_clip_detection (
    clip_id UUID PRIMARY KEY,
    task_id UUID,
    status INTEGER,              -- 0=NotStarted, 1=InProgress, 2=Completed, 3=Failed
    primary_detection INTEGER,   -- ApexLegend enum value
    secondary_detection INTEGER
);
```

## Monitoring

### Check Celery Worker Status

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
- Verify Celery worker running: `docker ps | grep apex-legend-detector`
- Check Redis connectivity: `docker exec apex-legend-detector redis-cli -h redis ping`
- Check queue: `docker exec redis redis-cli LLEN apex_detection_queue`

**Low confidence scores:**
- Adjust `MIN_CONFIDENCE` environment variable (lower = more permissive)
- Verify `PORTRAIT_REGION` coordinates match your screenshot resolution
- Ensure reference portraits are high quality and well-lit

**Character not detected:**
- Check character name mapping in `ApexLegend.cs`
- Ensure portrait PNG filename matches character name
- Review logs for "Loaded portrait for {name}" messages
