"""
citeflex/engines/youtube_engine.py

YouTube video metadata extraction via the oEmbed API.

The oEmbed API is free and requires no authentication.
Documentation: https://oembed.com/

Version History:
    2025-12-08: Initial creation
"""

import re
from typing import Optional
from datetime import datetime
from urllib.parse import urlparse, parse_qs

from engines.base import SearchEngine
from models import CitationMetadata, CitationType


class YouTubeEngine(SearchEngine):
    """
    YouTube video metadata engine.
    
    Uses the YouTube oEmbed API to fetch video metadata.
    The oEmbed API is free and requires no authentication.
    
    Handles:
    - youtube.com/watch?v=VIDEO_ID
    - youtu.be/VIDEO_ID
    - youtube.com/embed/VIDEO_ID
    """
    
    name = "YouTube"
    base_url = "https://www.youtube.com/oembed"
    
    def search(self, query: str) -> Optional[CitationMetadata]:
        """
        Search/fetch YouTube video by URL or ID.
        
        Args:
            query: YouTube URL or video ID
            
        Returns:
            CitationMetadata if found, None otherwise
        """
        # Extract video ID
        video_id = self._extract_video_id(query)
        if video_id:
            return self.get_by_id(video_id)
        
        # If query looks like a video ID directly
        if re.match(r'^[a-zA-Z0-9_-]{11}$', query.strip()):
            return self.get_by_id(query.strip())
        
        return None
    
    def get_by_id(self, video_id: str) -> Optional[CitationMetadata]:
        """
        Fetch metadata by YouTube video ID.
        
        Args:
            video_id: 11-character YouTube video ID
            
        Returns:
            CitationMetadata if found, None otherwise
        """
        if not video_id:
            return None
        
        video_id = video_id.strip()
        print(f"[{self.name}] Fetching video: {video_id}")
        
        # Build the video URL for oEmbed
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        
        params = {
            'url': video_url,
            'format': 'json',
        }
        
        response = self._make_request(self.base_url, params=params)
        if not response:
            return None
        
        try:
            data = response.json()
            return self._normalize(data, video_url, video_id)
        except Exception as e:
            print(f"[{self.name}] Parse error: {e}")
            return None
    
    def _extract_video_id(self, text: str) -> Optional[str]:
        """Extract YouTube video ID from URL or text."""
        if not text:
            return None
        
        text = text.strip()
        
        # youtu.be/VIDEO_ID
        match = re.search(r'youtu\.be/([a-zA-Z0-9_-]{11})', text)
        if match:
            return match.group(1)
        
        # youtube.com/watch?v=VIDEO_ID
        match = re.search(r'[?&]v=([a-zA-Z0-9_-]{11})', text)
        if match:
            return match.group(1)
        
        # youtube.com/embed/VIDEO_ID
        match = re.search(r'/embed/([a-zA-Z0-9_-]{11})', text)
        if match:
            return match.group(1)
        
        # youtube.com/v/VIDEO_ID
        match = re.search(r'/v/([a-zA-Z0-9_-]{11})', text)
        if match:
            return match.group(1)
        
        # youtube.com/shorts/VIDEO_ID
        match = re.search(r'/shorts/([a-zA-Z0-9_-]{11})', text)
        if match:
            return match.group(1)
        
        return None
    
    def _normalize(self, data: dict, video_url: str, video_id: str) -> CitationMetadata:
        """Convert YouTube oEmbed response to CitationMetadata."""
        
        title = data.get('title', '')
        author = data.get('author_name', '')
        author_url = data.get('author_url', '')
        
        # Access date
        access_date = datetime.now().strftime('%B %d, %Y').replace(' 0', ' ')
        
        # YouTube videos are cited as URL/online video type
        # Chicago style typically cites as: "Title." YouTube video, duration. Posted by Author. Date. URL.
        # Since oEmbed doesn't provide upload date, we'll leave date blank
        
        return self._create_metadata(
            citation_type=CitationType.URL,
            raw_source=video_url,
            title=title,
            authors=[author] if author else [],
            url=video_url,
            access_date=access_date,
            raw_data={
                **data,
                'video_id': video_id,
                'author_url': author_url,
                'source': 'YouTube',
                'media_type': 'video',
            }
        )


class VimeoEngine(SearchEngine):
    """
    Vimeo video metadata engine.
    
    Uses the Vimeo oEmbed API to fetch video metadata.
    The oEmbed API is free and requires no authentication.
    """
    
    name = "Vimeo"
    base_url = "https://vimeo.com/api/oembed.json"
    
    def search(self, query: str) -> Optional[CitationMetadata]:
        """
        Fetch Vimeo video by URL or ID.
        
        Args:
            query: Vimeo URL or video ID
            
        Returns:
            CitationMetadata if found, None otherwise
        """
        video_id = self._extract_video_id(query)
        if video_id:
            return self.get_by_id(video_id)
        
        # If query is just a number, try it as video ID
        if query.strip().isdigit():
            return self.get_by_id(query.strip())
        
        return None
    
    def get_by_id(self, video_id: str) -> Optional[CitationMetadata]:
        """
        Fetch metadata by Vimeo video ID.
        
        Args:
            video_id: Vimeo video ID (numeric)
            
        Returns:
            CitationMetadata if found, None otherwise
        """
        if not video_id:
            return None
        
        video_id = video_id.strip()
        print(f"[{self.name}] Fetching video: {video_id}")
        
        video_url = f"https://vimeo.com/{video_id}"
        
        params = {
            'url': video_url,
        }
        
        response = self._make_request(self.base_url, params=params)
        if not response:
            return None
        
        try:
            data = response.json()
            return self._normalize(data, video_url, video_id)
        except Exception as e:
            print(f"[{self.name}] Parse error: {e}")
            return None
    
    def _extract_video_id(self, text: str) -> Optional[str]:
        """Extract Vimeo video ID from URL."""
        if not text:
            return None
        
        # vimeo.com/12345678
        match = re.search(r'vimeo\.com/(\d+)', text)
        if match:
            return match.group(1)
        
        # player.vimeo.com/video/12345678
        match = re.search(r'player\.vimeo\.com/video/(\d+)', text)
        if match:
            return match.group(1)
        
        return None
    
    def _normalize(self, data: dict, video_url: str, video_id: str) -> CitationMetadata:
        """Convert Vimeo oEmbed response to CitationMetadata."""
        
        title = data.get('title', '')
        author = data.get('author_name', '')
        author_url = data.get('author_url', '')
        
        # Vimeo provides upload date in some cases
        upload_date = data.get('upload_date', '')
        year = None
        if upload_date:
            year_match = re.search(r'(\d{4})', upload_date)
            if year_match:
                year = year_match.group(1)
        
        access_date = datetime.now().strftime('%B %d, %Y').replace(' 0', ' ')
        
        return self._create_metadata(
            citation_type=CitationType.URL,
            raw_source=video_url,
            title=title,
            authors=[author] if author else [],
            year=year,
            url=video_url,
            access_date=access_date,
            raw_data={
                **data,
                'video_id': video_id,
                'author_url': author_url,
                'source': 'Vimeo',
                'media_type': 'video',
            }
        )
