"""
Web & YouTube Source Ingestor and Academic Citation Generator.
Fetches web articles, YouTube metadata/descriptions, generates AI summaries,
and formats citations in MLA 9th, APA 7th, and Standard Report/Chicago styles.
"""

import re
import json
import urllib.request
import urllib.parse
import datetime
from typing import Dict, Any, List, Optional
from core.logger import get_logger

logger = get_logger("playground.web_source")


class WebSourceIngestor:
    """Fetches, parses, and extracts structured content from Web and YouTube URLs."""

    YOUTUBE_REGEX = re.compile(
        r"(?:https?://)?(?:www\.)?(?:youtube\.com/(?:watch\?v=|embed/|shorts/)|youtu\.be/)([a-zA-Z0-9_-]{11})",
        re.IGNORECASE,
    )
    URL_REGEX = re.compile(
        r"https?://[^\s<>\"']+",
        re.IGNORECASE,
    )

    @classmethod
    def extract_youtube_urls(cls, text: str) -> List[str]:
        """Finds and canonicalizes all YouTube video URLs in a block of text."""
        if not text:
            return []
        matches = cls.YOUTUBE_REGEX.findall(text)
        seen = set()
        urls = []
        for vid in matches:
            canonical = f"https://www.youtube.com/watch?v={vid}"
            if canonical not in seen:
                seen.add(canonical)
                urls.append(canonical)
        return urls

    @classmethod
    def extract_all_urls(cls, text: str) -> List[str]:
        """Extracts all HTTP/HTTPS URLs from text."""
        if not text:
            return []
        raw_urls = cls.URL_REGEX.findall(text)
        return list(dict.fromkeys(r.rstrip(".,;!?)") for r in raw_urls))

    @classmethod
    def is_youtube_url(cls, url: str) -> bool:
        return bool(cls.YOUTUBE_REGEX.search(url))

    @classmethod
    def fetch(cls, url: str, ai_client=None) -> Dict[str, Any]:
        """Convenience alias for fetch_source."""
        return cls.fetch_source(url, ai_client)

    @classmethod
    def fetch_source(cls, url: str, ai_client=None) -> Dict[str, Any]:
        """
        Fetches web page or YouTube video details, extracts key metadata,
        and generates an academic research summary.
        """
        url = url.strip()
        try:
            if cls.is_youtube_url(url):
                res = cls._fetch_youtube(url, ai_client)
            else:
                res = cls._fetch_webpage(url, ai_client)

            res["success"] = True
            res["is_youtube"] = (res.get("source_type") == "youtube")
            if "summary_content" not in res:
                res["summary_content"] = res.get("content", "")
            return res
        except Exception as e:
            logger.error(f"Error fetching source for {url}: {e}", exc_info=True)
            is_yt = cls.is_youtube_url(url)
            return {
                "success": False,
                "error": str(e),
                "url": url,
                "is_youtube": is_yt,
                "source_type": "youtube" if is_yt else "web",
                "title": url,
                "author": "",
                "site_name": "YouTube" if is_yt else "Web",
                "content": f"Source URL: {url}",
                "summary_content": f"Source URL: {url}",
            }

    @classmethod
    def _fetch_youtube(cls, url: str, ai_client=None) -> Dict[str, Any]:
        """Fetches YouTube video metadata via public oEmbed API and page scrape."""
        logger.info(f"Fetching YouTube metadata for: {url}")
        
        # Canonicalize YouTube URL to watch?v= format
        m_vid = cls.YOUTUBE_REGEX.search(url)
        vid = m_vid.group(1) if m_vid else ""
        canonical_url = f"https://www.youtube.com/watch?v={vid}" if vid else url

        title = f"YouTube Video ({vid})" if vid else "YouTube Video"
        author = "YouTube Channel"
        site_name = "YouTube"
        publish_date = datetime.date.today().strftime("%d %b %Y")
        description = ""

        # 1. Query official public YouTube oEmbed endpoint (no API key required)
        try:
            oembed_url = f"https://www.youtube.com/oembed?url={urllib.parse.quote(canonical_url)}&format=json"
            req = urllib.request.Request(
                oembed_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
                title = data.get("title", title)
                author = data.get("author_name", author)
                provider = data.get("provider_name", "YouTube")
                site_name = provider
        except Exception as e:
            logger.warning(f"YouTube oEmbed lookup failed for {canonical_url}: {e}")

        # 2. Scrape raw page meta tags for description and title if oEmbed didn't provide
        try:
            req = urllib.request.Request(
                canonical_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                html = response.read().decode("utf-8", errors="ignore")
                m_desc = re.search(r'<meta\s+(?:name|property)="description"\s+content="([^"]+)"', html, re.IGNORECASE)
                if m_desc and m_desc.group(1).strip():
                    description = m_desc.group(1).strip()
                m_og_title = re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"', html, re.IGNORECASE)
                if m_og_title and m_og_title.group(1).strip() and title.startswith("YouTube Video ("):
                    title = m_og_title.group(1).strip()
        except Exception as e:
            logger.debug(f"YouTube page scrape failed: {e}")

        # 3. AI synthesis of summary
        content_text = f"Title: {title}\nChannel: {author}\nDescription: {description if description else 'No description available.'}\nURL: {canonical_url}"
        if ai_client:
            try:
                prompt = (
                    f"Synthesize an academic source reference for a research document from this YouTube video info:\n\n"
                    f"{content_text}\n\n"
                    "Provide a comprehensive, high-density summary (150-250 words) outlining:\n"
                    "1. Core premise, argument, or findings discussed\n"
                    "2. Key factual points, data, or expert claims\n"
                    "3. How a student can cite and apply this source in academic writing"
                )
                summary = ai_client.generate_text_response(
                    prompt=prompt,
                    system_instruction="You are an expert academic research assistant summarizing video source materials.",
                )
                if summary and len(summary.strip()) > 30:
                    content_text = summary.strip()
            except Exception as e:
                logger.warning(f"AI video summarization failed: {e}")

        return {
            "success": True,
            "title": title,
            "author": author,
            "site_name": site_name,
            "publish_date": publish_date,
            "content": content_text,
            "summary_content": content_text,
            "url": canonical_url,
            "source_type": "youtube",
            "is_youtube": True,
        }

    @classmethod
    def _fetch_webpage(cls, url: str, ai_client=None) -> Dict[str, Any]:
        """Fetches and cleans an online webpage, article, or documentation."""
        logger.info(f"Fetching web article for: {url}")
        parsed = urllib.parse.urlparse(url)
        domain = parsed.netloc or "Website"
        site_name = domain.replace("www.", "").capitalize()

        title = site_name
        author = ""
        publish_date = datetime.date.today().strftime("%d %b %Y")
        body_text = ""

        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                }
            )
            with urllib.request.urlopen(req, timeout=12) as response:
                raw_html = response.read().decode("utf-8", errors="ignore")

            # Extract Title
            m_title = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.IGNORECASE | re.DOTALL)
            if m_title:
                t = re.sub(r"\s+", " ", m_title.group(1)).strip()
                t = re.split(r"[-–—|]", t)[0].strip()
                if t:
                    title = t

            # Extract Author
            m_auth = re.search(r'<meta\s+name=["\'](?:author|byl|dc\.creator)["\']\s+content=["\']([^"\']+)["\']', raw_html, re.IGNORECASE)
            if m_auth:
                author = m_auth.group(1).strip()

            # Extract Site Name
            m_site = re.search(r'<meta\s+property=["\']og:site_name["\']\s+content=["\']([^"\']+)["\']', raw_html, re.IGNORECASE)
            if m_site:
                site_name = m_site.group(1).strip()

            # Extract Publish Date
            m_date = re.search(r'<meta\s+(?:property|name)=["\'](?:article:published_time|date|pubdate)["\']\s+content=["\']([^"\']+)["\']', raw_html, re.IGNORECASE)
            if m_date:
                try:
                    dt = datetime.datetime.fromisoformat(m_date.group(1).split("T")[0])
                    publish_date = dt.strftime("%d %b %Y")
                except Exception:
                    pass

            # Clean body HTML
            cleaned = re.sub(r"<(?:script|style|nav|footer|header|aside|noscript)[^>]*>.*?</(?:script|style|nav|footer|header|aside|noscript)>", " ", raw_html, flags=re.DOTALL | re.IGNORECASE)
            cleaned = re.sub(r"<[^>]+>", " ", cleaned)
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            body_text = cleaned[:4000]

        except Exception as e:
            logger.warning(f"Failed to fetch webpage content: {e}")
            body_text = f"URL Source: {url} (Content fetch was blocked or limited)."

        content_text = f"Title: {title}\nSite: {site_name}\nAuthor: {author if author else 'Staff Writer'}\nURL: {url}\n\nContent:\n{body_text[:2500]}"
        if ai_client and len(body_text) > 100:
            try:
                prompt = (
                    f"Synthesize an academic source summary from this online article:\n\n"
                    f"{content_text[:3000]}\n\n"
                    "Extract and organize:\n"
                    "1. Primary thesis or central argument\n"
                    "2. 3-4 key factual evidence points, statistics, or quotations\n"
                    "3. Relevance for citation in a student research paper"
                )
                summary = ai_client.generate_text_response(
                    prompt=prompt,
                    system_instruction="You are an academic researcher creating factual research source summaries.",
                )
                if summary and len(summary.strip()) > 30:
                    content_text = summary.strip()
            except Exception as e:
                logger.warning(f"AI webpage summarization failed: {e}")

        return {
            "title": title,
            "author": author,
            "site_name": site_name,
            "publish_date": publish_date,
            "content": content_text,
            "url": url,
            "source_type": "web",
        }


class CitationGenerator:
    """Generates formal academic bibliographic citations according to style guides."""

    @classmethod
    def generate(
        cls,
        source_data: Optional[Dict[str, Any]] = None,
        style: str = "MLA",
        format_style: Optional[str] = None,
        **kwargs,
    ) -> str:
        chosen = format_style or style or "MLA"
        return cls.generate_citation(source_data, style=chosen, **kwargs)

    @classmethod
    def generate_citation(
        cls,
        source_data: Optional[Dict[str, Any]] = None,
        style: str = "MLA",
        format_style: Optional[str] = None,
        **kwargs,
    ) -> str:
        """
        Creates a formatted citation string for Works Cited / References.
        Supported styles: 'MLA', 'APA', 'Standard Report' (Chicago).
        """
        if not source_data:
            source_data = {}
        chosen_style = format_style or style or "MLA"
        style_norm = (chosen_style or "MLA").upper()
        title = source_data.get("title") or "Source Material"
        author = source_data.get("author") or ""
        url = source_data.get("url") or source_data.get("file_path") or ""
        is_yt = source_data.get("is_youtube") or ("youtube.com" in url.lower() or "youtu.be" in url.lower())
        source_type = source_data.get("source_type") or ("youtube" if is_yt else "web")
        site_name = source_data.get("site_name") or ("YouTube" if source_type == "youtube" else "Web")
        pub_date = source_data.get("publish_date") or ""
        today_str = datetime.date.today().strftime("%d %b. %Y")
        today_apa = datetime.date.today().strftime("%Y, %B %d")

        if "MLA" in style_norm:
            return cls._format_mla(title, author, site_name, url, pub_date, source_type, today_str)
        elif "APA" in style_norm:
            return cls._format_apa(title, author, site_name, url, pub_date, source_type)
        else:
            return cls._format_report(title, author, site_name, url, pub_date, source_type)

    @classmethod
    def _format_mla(cls, title: str, author: str, site: str, url: str, pub_date: str, stype: str, today: str) -> str:
        """MLA 9th Edition format."""
        if stype == "youtube":
            creator = f"uploaded by {author}, " if author else ""
            date_part = f"{pub_date}, " if pub_date else ""
            url_part = f"{url}. " if url else ""
            return f'"{title}." YouTube, {creator}{date_part}{url_part}Accessed {today}.'

        # Article / Webpage
        author_part = ""
        if author:
            parts = author.split()
            if len(parts) >= 2:
                author_part = f"{parts[-1]}, {' '.join(parts[:-1])}. "
            else:
                author_part = f"{author}. "

        date_part = f"{pub_date}, " if pub_date else ""
        url_part = f"{url}. " if url else ""
        return f'{author_part}"{title}." {site}, {date_part}{url_part}Accessed {today}.'

    @classmethod
    def _format_apa(cls, title: str, author: str, site: str, url: str, pub_date: str, stype: str) -> str:
        """APA 7th Edition format."""
        year_part = "(n.d.)."
        if pub_date:
            m_yr = re.search(r"\b(19\d\d|20\d\d)\b", pub_date)
            if m_yr:
                year_part = f"({m_yr.group(1)})."

        if stype == "youtube":
            channel = author if author else "YouTube Channel"
            url_part = f" {url}" if url else ""
            return f"{channel}. {year_part} {title} [Video]. YouTube.{url_part}"

        # Webpage
        auth_part = ""
        if author:
            parts = author.split()
            if len(parts) >= 2:
                initials = " ".join(f"{p[0]}." for p in parts[:-1])
                auth_part = f"{parts[-1]}, {initials} "
            else:
                auth_part = f"{author} "
        else:
            auth_part = f"{site}. "

        url_part = f" {url}" if url else ""
        return f"{auth_part}{year_part} {title}. {site}.{url_part}"

    @classmethod
    def _format_report(cls, title: str, author: str, site: str, url: str, pub_date: str, stype: str) -> str:
        """Standard Report / Chicago Notes & Bibliography style."""
        auth_part = f"{author}. " if author else ""
        type_part = " [Online Video]." if stype == "youtube" else "."
        date_part = f" Published {pub_date}." if pub_date else ""
        url_part = f" Available at: {url}" if url else ""
        return f'{auth_part}"{title}." {site}{type_part}{date_part}{url_part}'
