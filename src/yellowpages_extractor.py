from __future__ import annotations
import random
import time
from dataclasses import dataclass
from typing import Dict, List, Set
from urllib.parse import urljoin
import re

import requests
from bs4 import BeautifulSoup


@dataclass
class RequestCfg:
    """
    Configuration for HTTP requests including:
      - timeout (seconds)
      - number of retries
      - exponential backoff factor for retry delays
      - minimum and maximum delay between requests
      - optional custom headers
    """
    timeout: int = 25
    retries: int = 1
    backoff_factor: float = 1.8
    min_delay: float = 1.0
    max_delay: float = 2.0
    headers: dict | None = None


def _sleep(min_s: float, max_s: float):
    """
    Sleep for a random duration between min_s and max_s seconds.
    Used to avoid hitting the server too quickly.
    """
    time.sleep(random.uniform(min_s, max_s))


def _request_text(url: str, cfg: RequestCfg, logger) -> str:
    """
    Perform a GET request to fetch HTML content of a URL.
    Retries on failure up to cfg.retries times with exponential backoff.

    Raises RuntimeError if all attempts fail.
    """
    last_err = None
    for attempt in range(1, cfg.retries + 1):
        try:
            r = requests.get(url, headers=cfg.headers, timeout=cfg.timeout, allow_redirects=True)
            r.raise_for_status()
            return r.text
        except Exception as e:
            last_err = e
            logger.warning(f"[{attempt}/{cfg.retries}] GET {url} failed -> {e}")
            if attempt < cfg.retries:
                time.sleep(cfg.backoff_factor ** attempt)
    raise RuntimeError(f"Failed to fetch {url}: {last_err}")


def _extract_data_from_profile_page(html: str, selectors: Dict, profile_url: str, logger) -> Dict | None:
    """
    Extract company metadata from a profile page.

    Returns a dict with:
      - company_name
      - country (city)
      - website_url
      - profile_url

    Uses CSS selectors from the config. If company name is missing, returns None.
    """
    soup = BeautifulSoup(html, 'html.parser')

    # Company Name
    name_elem = soup.select_one(selectors.get("company_name", "h2"))
    name = name_elem.text.strip() if name_elem else None

    # City
    city_elem = soup.select_one(selectors.get("city", "span.city"))
    city = city_elem.text.strip() if city_elem else None

    # Website URL
    website_elem = soup.select_one(selectors.get("website_button", "button[title][data-url]"))
    website = website_elem['title'] if website_elem and website_elem.has_attr('title') else None

    if not name:
        logger.warning(f"Could not extract company name from {profile_url}. Skipping.")
        return None

    return {
        "company_name": name,
        "country": city,
        "website_url": website,
        "profile_url": profile_url
    }


def extract_profiles(cfg: Dict, logger) -> List[Dict]:
    """
    Main function to extract all company profiles for a given category.

    Steps:
      1. Loop through paginated search results (up to cfg['max_pages']).
      2. Extract candidate profile links from each page using CSS selectors.
      3. Filter and normalize links to absolute profile URLs.
      4. Visit each profile URL to scrape detailed metadata using _extract_data_from_profile_page.
      5. Return a list of dictionaries containing company_name, country, website_url, profile_url.
    """
    base_url = cfg["base_url"].rstrip("/")
    category = cfg.get("category")
    max_pages = cfg.get("max_pages", 1)
    selectors = cfg.get("selectors", {})

    if not category:
        logger.error("Category not provided in config.")
        return []

    req_cfg = RequestCfg(
        timeout=int(cfg.get("timeout", 25)),
        retries=int(cfg.get("retries", 3)),
        backoff_factor=float(cfg.get("backoff_factor", 1.8)),
        min_delay=float(cfg.get("min_delay", 1.0)),
        max_delay=float(cfg.get("max_delay", 2.0)),
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
    )

    profile_urls: Set[str] = set()

    # Part 1: Scrape all profile URLs across paginated search results
    for page_num in range(1, max_pages + 1):
        page_url = f"{base_url}/uae/{category}?page={page_num}"
        logger.info(f"Fetching search page {page_num}/{max_pages}: {page_url}")

        try:
            response_text = _request_text(page_url, req_cfg, logger)
        except RuntimeError as e:
            logger.error(e)
            continue

        soup = BeautifulSoup(response_text, 'html.parser')

        listing_links = soup.select(
            selectors.get('profile_links', 'div.text-xl.font-bold a.flex[href^="/"]')
        )

        candidate_urls = [a["href"] for a in listing_links if a.has_attr("href")]
        logger.info(f"Page {page_num}: found {len(candidate_urls)} candidate links")

        for href in candidate_urls:
            if not href:
                continue

            if re.match(r'^/[a-z0-9-]+-\d+', href):
                clean_href = href.split("?")[0]   # strip query params
                full_url = urljoin(base_url, clean_href)
                profile_urls.add(full_url)

        logger.info(f"Total unique links collected so far: {len(profile_urls)}")
        _sleep(req_cfg.min_delay, req_cfg.max_delay)

    logger.info(f"Found {len(profile_urls)} unique company profiles across {max_pages} pages.")
    if not profile_urls:
        return []

    all_businesses: List[Dict] = []

    # Part 2: Visit each profile URL to extract detailed data
    for i, profile_url in enumerate(sorted(profile_urls), start=1):
        logger.info(f"[{i}/{len(profile_urls)}] Scraping profile page: {profile_url}")

        try:
            profile_html = _request_text(profile_url, req_cfg, logger)
            company_data = _extract_data_from_profile_page(profile_html, selectors, profile_url, logger)
            if company_data:
                all_businesses.append(company_data)
        except RuntimeError as e:
            logger.error(f"Failed to scrape profile page {profile_url}: {e}")

        _sleep(req_cfg.min_delay, req_cfg.max_delay)

    return all_businesses
