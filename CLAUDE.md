# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python computer vision service that detects Apex Legends characters from gameplay screenshots. It uses Redis queues for task processing and OpenCV for template matching against reference character portraits.

## Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the worker locally (requires Redis)
export REDIS_URL=redis://localhost:6379/0
python worker.py

# Build Docker image
docker build -t apex-legend-detector .

# Run with Docker
docker run -d \
  -e REDIS_URL=redis://redis:6379/0 \
  -v apex_portraits:/app/portraits \
  apex-legend-detector
```

## Architecture

### Worker Modes
The codebase has two worker implementations:
- **worker.py** - Simple Redis queue worker using `brpop` for blocking queue reads
- **tasks.py** - Celery-based alternative (same detection logic, different queue mechanism)

### Detection Flow
1. Task arrives via Redis queue `apex_detection_queue`
2. `ApexDetector.process_screenshots()` downloads images asynchronously via aiohttp
3. Images are resized to 1080p, then portrait region is extracted at configured coordinates
4. Portrait is compared against reference images using three OpenCV template matching methods (TM_CCOEFF_NORMED, TM_CCORR_NORMED, TM_SQDIFF_NORMED)
5. Scores are averaged for robust matching; best match above `MIN_CONFIDENCE` is returned
6. Results stored in Redis at `result:{task_id}` with 7-day TTL (1-day for failures)

### Key Configuration
- `PORTRAIT_REGION` - Screenshot crop coordinates as `x,y,w,h` (default: `90,955,77,66`)
- `MIN_CONFIDENCE` - Detection threshold 0-1 (default: `0.44`)
- `REDIS_URL` - Redis connection string

### Data Models (Pydantic)
- `ScreenshotRequest` - Input: video_id + screenshot_urls
- `CharacterMatch` - Output: character_name, confidence, screenshot_index

### Portrait References
Reference portraits are PNG files in `/app/portraits/` (Docker) or a mounted volume. Filename becomes character name (e.g., `Mad_Maggie.png` → "mad maggie").
