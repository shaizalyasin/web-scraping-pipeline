from __future__ import annotations
import random
import re
import time
from dataclasses import dataclass
from typing import Dict, List, Set
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


@dataclass
class RequestCfg:
    """
    Configuration for HTTP requests for email scraping.

    Attributes:
      - timeout: maximum seconds to wait for a response
      - retries: number of retry attempts on failure
      - backoff_factor: exponential backoff multiplier between retries
      - min_delay, max_delay: random delay range between requests
      - headers: optional HTTP headers
    """
    timeout: int = 20
    retries: int = 3
    backoff_factor: float = 1.5
    min_delay: float = 0.8
    max_delay: float = 1.8
    headers: dict | None = None


EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)


def _sleep(min_s: float, max_s: float):
    """
    Sleep for a random duration between min_s and max_s seconds.
    Helps to mimic human browsing behavior to avoid server blocks.
    """
    time.sleep(random.uniform(min_s, max_s))


def _normalize_url(url: str) -> str:
    """
    Ensure the URL has a proper scheme (default https:// if missing).

    Args:
      url: raw URL string

    Returns:
      Normalized URL with scheme.
    """
    url = url.strip()
    if not url:
        return ""
    parsed = urlparse(url)
    if not parsed.scheme:
        url = "https://" + url
    return url


def _request_text(url: str, cfg: RequestCfg, logger) -> str:
    """
    Fetch the HTML content of a given URL using requests.

    Retries on failures (timeouts, 5xx errors) with exponential backoff.

    Args:
      url: URL to fetch
      cfg: RequestCfg instance with request settings
      logger: logger instance for logging messages

    Returns:
      The HTML content of the page as a string.

    Raises:
      RuntimeError if all retries fail.
    """
    url = _normalize_url(url)
    last_err = None
    for attempt in range(1, cfg.retries + 1):
        try:
            r = requests.get(url, headers=cfg.headers, timeout=cfg.timeout, allow_redirects=True)
            if r.status_code >= 500:
                raise requests.RequestException(f"Server {r.status_code}")
            return r.text
        except Exception as e:
            last_err = e
            logger.warning(f"[{attempt}/{cfg.retries}] GET {url} failed -> {e}")
            if attempt < cfg.retries:
                time.sleep(cfg.backoff_factor ** attempt)
    raise RuntimeError(f"Failed to fetch {url}: {last_err}")


def _extract_emails_from_html(html: str) -> Set[str]:
    """
    Extract all email addresses from the HTML content.

    Searches both:
      - plain text emails matching regex
      - mailto: links in anchor tags

    Args:
      html: page HTML

    Returns:
      Set of lowercase email addresses
    """
    if not html:
        return set()
    emails = set(EMAIL_RE.findall(html))
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.select("a[href^='mailto:']"):
        href = a.get("href", "")
        m = re.search(r"mailto:([^?]+)", href, re.I)
        if m:
            emails.add(m.group(1).strip())
    return {e.strip().lower() for e in emails}


def scrape_emails_for_profiles(profiles: List[Dict], email_cfg: Dict, request_cfg: Dict, logger) -> List[Dict]:
    """
    Crawl each company's website and profile page to extract email addresses.

    Args:
      profiles: list of company dicts with keys: company_name, country, profile_url, website_url
      email_cfg: config dict for email crawling (crawl_paths, max_pages_per_site)
      request_cfg: dict with timeout, delays, headers for requests
      logger: logger instance for logging info and warnings

    Returns:
      List of dicts: each dict contains name, country, and a single email
    """
    req = RequestCfg(
        timeout=int(request_cfg.get("timeout", 20)),
        retries=int(request_cfg.get("retries", 3)),
        backoff_factor=float(request_cfg.get("backoff_factor", 1.5)),
        min_delay=float(request_cfg.get("min_delay_seconds", 0.8)),
        max_delay=float(request_cfg.get("max_delay_seconds", 1.8)),
        headers=request_cfg.get("headers"),
    )

    crawl_paths = email_cfg.get("crawl_paths", ["/", "/contact", "/contact-us", "/about", "/impressum"])
    max_pages_per_site = int(email_cfg.get("max_pages_per_site", 3))

    results: List[Dict] = []

    for i, row in enumerate(profiles, start=1):
        name = (row.get("company_name") or "").strip()
        country = (row.get("country") or "").strip()
        profile_url = row.get("profile_url", "")
        website_url = row.get("website_url", "")

        logger.info(f"[{i}/{len(profiles)}] Scraping emails for: {name or profile_url}")

        emails_found: Set[str] = set()

        tries = []
        if website_url:
            normalized_website = _normalize_url(website_url)
            tries.append(normalized_website)
            for p in crawl_paths[:max_pages_per_site]:
                try:
                    tries.append(urljoin(normalized_website, p))
                except Exception:
                    pass
        else:
            normalized_profile = _normalize_url(profile_url)
            tries.append(normalized_profile)

        for j, page_url in enumerate(tries[:max_pages_per_site], start=1):
            try:
                html = _request_text(page_url, req, logger)
                emails_found |= _extract_emails_from_html(html)
            except Exception as e:
                logger.debug(f"  failed fetch {page_url}: {e}")
            _sleep(req.min_delay, req.max_delay)

        for em in sorted(emails_found):
            results.append({"name": name, "country": country, "email": em})

        if not emails_found:
            logger.info(f"  No emails found for {name or profile_url}")

    return results
