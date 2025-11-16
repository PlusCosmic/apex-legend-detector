import os
import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Optional

import cv2
import numpy as np
import aiohttp
from pydantic import BaseModel, HttpUrl

logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'))
logger = logging.getLogger(__name__)

class ScreenshotRequest(BaseModel):
    video_id: str
    screenshot_urls: List[HttpUrl]

class CharacterMatch(BaseModel):
    character_name: str
    confidence: float
    screenshot_index: int
    video_id: str
    matched_screenshot_url: str

class ApexDetector:
    def __init__(self):
        self.portrait_region = self._parse_region(
            os.getenv('PORTRAIT_REGION', '90,955,77,66')
        )
        self.min_confidence = float(os.getenv('MIN_CONFIDENCE', '0.44'))
        logger.info(f"Minimum confidence: {self.min_confidence}")
        self.reference_portraits = {}
        self.load_reference_portraits()

    def _parse_region(self, region_str: str) -> tuple:
        """Parse region string like '90, 955, 77, 66' to tuple"""
        return tuple(map(int, region_str.split(',')))

    def load_reference_portraits(self):
        """Load all reference portraits from the portraits directory"""
        portrait_dir = Path('/app/portraits')
        if not portrait_dir.exists():
            logger.warning("Portraits directory not found, creating it...")
            portrait_dir.mkdir(parents=True)
            return

        for portrait_file in portrait_dir.glob('*.png'):
            character_name = portrait_file.stem
            portrait_img = cv2.imread(str(portrait_file))
            if portrait_img is not None:
                self.reference_portraits[character_name] = portrait_img
                logger.info(f"Loaded portrait for {character_name}")

        logger.info(f"Loaded {len(self.reference_portraits)} character portraits")

    def resize_to_1080p(self, image: np.ndarray) -> np.ndarray:
        """Resize image to 1080p if it's larger, maintaining aspect ratio"""
        target_height = 1080
        target_width = 1920

        height, width = image.shape[:2]

        # If already 1080p or smaller, return as-is
        if height <= target_height and width <= target_width:
            return image

        # Calculate scaling factor to fit within 1080p bounds
        scale_h = target_height / height
        scale_w = target_width / width
        scale = min(scale_h, scale_w)

        new_width = int(width * scale)
        new_height = int(height * scale)

        resized = cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_AREA)
        logger.info(f"Resized image from {width}x{height} to {new_width}x{new_height}")

        return resized

    def extract_portrait_from_image(self, image: np.ndarray) -> np.ndarray:
        """Extract the portrait region from a full screenshot"""
        x, y, w, h = self.portrait_region

        if image.shape[0] < y + h or image.shape[1] < x + w:
            logger.error(f"Image too small: {image.shape}, need at least ({x+w}, {y+h})")
            raise ValueError("Image dimensions too small for portrait extraction")

        return image[y:y+h, x:x+w]

    def calculate_similarity(self, portrait1: np.ndarray, portrait2: np.ndarray) -> float:
        """Calculate similarity between two portraits using template matching"""
        if portrait1.shape != portrait2.shape:
            portrait2 = cv2.resize(portrait2, (portrait1.shape[1], portrait1.shape[0]))

        gray1 = cv2.cvtColor(portrait1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(portrait2, cv2.COLOR_BGR2GRAY)

        methods = [
            cv2.TM_CCOEFF_NORMED,
            cv2.TM_CCORR_NORMED,
            cv2.TM_SQDIFF_NORMED
        ]

        scores = []
        for method in methods:
            result = cv2.matchTemplate(gray1, gray2, method)
            if method == cv2.TM_SQDIFF_NORMED:
                score = 1 - result[0][0]
            else:
                score = result[0][0]
            scores.append(score)

        return np.mean(scores)

    async def download_image(self, session: aiohttp.ClientSession, url: str) -> Optional[np.ndarray]:
        """Download image from URL and convert to numpy array"""
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status != 200:
                    logger.error(f"Failed to download image from {url}: HTTP {response.status}")
                    return None

                image_bytes = await response.read()
                nparr = np.frombuffer(image_bytes, np.uint8)
                image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                if image is None:
                    logger.error(f"Failed to decode image from {url}")
                    return None

                return image

        except asyncio.TimeoutError:
            logger.error(f"Timeout downloading image from {url}")
            return None
        except Exception as e:
            logger.error(f"Error downloading image from {url}: {str(e)}")
            return None

    async def process_screenshot_url(self, session: aiohttp.ClientSession, url: str) -> Optional[Dict]:
        """Process a single screenshot from URL"""
        try:
            image = await self.download_image(session, url)
            if image is None:
                return None

            # Resize to 1080p if necessary
            image = self.resize_to_1080p(image)

            portrait = self.extract_portrait_from_image(image)

            best_match = None
            highest_confidence = 0

            for char_name, ref_portrait in self.reference_portraits.items():
                confidence = self.calculate_similarity(portrait, ref_portrait)
                if confidence > highest_confidence:
                    highest_confidence = confidence
                    best_match = {
                        'character_name': char_name,
                        'confidence': float(confidence),
                        'url': url
                    }

            return best_match if highest_confidence >= self.min_confidence else None

        except Exception as e:
            logger.error(f"Error processing screenshot from {url}: {str(e)}")
            return None

    async def process_multiple_screenshots(self, screenshot_urls: List[str]) -> Optional[Dict]:
        """Process multiple screenshot URLs and return the best match"""
        best_overall = None
        highest_confidence = 0
        best_index = -1

        async with aiohttp.ClientSession() as session:
            tasks = [self.process_screenshot_url(session, url) for url in screenshot_urls]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for idx, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Error processing screenshot {idx}: {str(result)}")
                    continue

                if result and result['confidence'] > highest_confidence:
                    highest_confidence = result['confidence']
                    best_overall = result
                    best_index = idx

        if best_overall:
            best_overall['screenshot_index'] = best_index

        return best_overall

    def process_screenshots(self, screenshot_urls: List[str]) -> Optional[Dict]:
        """Synchronous wrapper for process_multiple_screenshots"""
        return asyncio.run(self.process_multiple_screenshots(screenshot_urls))
