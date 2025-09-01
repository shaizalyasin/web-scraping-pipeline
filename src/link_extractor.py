from __future__ import annotations
import random
import time
import re
from dataclasses import dataclass
from typing import Dict, List, Tuple, Set
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


@dataclass
class RequestCfg:
    """
    Configuration for HTTP requests.
    """
    timeout: int = 25
    retries: int = 3
    backoff_factor: float = 1.8
    min_delay: float = 1.0
    max_delay: float = 2.0
    headers: dict | None = None


def _sleep(min_s: float, max_s: float):
    """
    Sleep for a random duration between min_s and max_s seconds.
    Used to avoid hitting servers too fast and reduce detection.
    """
    time.sleep(random.uniform(min_s, max_s))


def _request_text(url: str, cfg: RequestCfg, logger) -> str:
    """
    Fetches the content of the URL using HTTP GET with retries and backoff.
    Raises RuntimeError if all attempts fail.
    """
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


def _build_pages(search_url: str, max_pages: int) -> List[str]:
    """
    Build a list of paginated search URLs based on max_pages.
    Supports URLs with query strings.
    """
    pages = [search_url]
    if "?" in search_url:
        prefix, qs = search_url.split("?", 1)
        for i in range(2, max_pages + 1):
            pages.append(f"{prefix}/page/{i}?{qs}")
    else:
        for i in range(2, max_pages + 1):
            pages.append(f"{search_url}/page/{i}")
    return pages


def _extract_product_links_from_page(html: str, base_url: str, selectors: Dict) -> Set[str]:
    """
    Extract product links from a search results page.
    Returns absolute URLs.
    Prioritizes product cards, but can fallback to any anchor matching `product_links`.
    """
    soup = BeautifulSoup(html, "html.parser")
    found: Set[str] = set()

    card_sel = selectors.get("product_cards") if selectors else None
    link_sel = selectors.get("product_links") if selectors else "a[href*='/en/company/'][href*='/products/']"

    cards = soup.select(card_sel) if card_sel else []
    if cards:
        for card in cards:
            for a in card.select(link_sel):
                href = (a.get("href") or "").strip()
                if not href:
                    continue
                if href.startswith("/"):
                    href = urljoin(base_url, href)
                if "/en/company/" in href and "/products/" in href:
                    found.add(href)
    else:
        for a in soup.select(link_sel):
            href = (a.get("href") or "").strip()
            if not href:
                continue
            if href.startswith("/"):
                href = urljoin(base_url, href)
            if "/en/company/" in href and "/products/" in href:
                found.add(href)

    return found


def _normalize_to_profile_url(product_or_profile_url: str, base_url: str) -> str | None:
    """
    Convert a product URL to its company profile URL.
    Example:
      https://.../en/company/<slug-id>/products/... -> https://.../en/company/<slug-id>
    """
    if not product_or_profile_url:
        return None
    try:
        p = urlparse(product_or_profile_url)
        path = p.path
        m = re.search(r"(/en/company/[^/]+-\d+)", path)
        if not m:
            return None
        profile_path = m.group(1)
        return urljoin(f"{p.scheme}://{p.netloc}/", profile_path)
    except Exception:
        return None


def _extract_website_from_profile_html(html: str, selectors: Dict) -> str | None:
    """
    Extract external website from profile page HTML.
    Prefers selector in config, falls back to any external HTTP link not pointing to Europages itself.
    """
    soup = BeautifulSoup(html, "html.parser")
    sel = selectors.get("website_button", "a.website-button[href^='http']")
    a = soup.select_one(sel)
    if a and a.get("href"):
        href = a.get("href").strip()
        if href.startswith("//"):
            href = "https:" + href
        return href
    for a in soup.select("a[href^='http']"):
        href = a.get("href").strip()
        if "europages." not in urlparse(href).netloc:
            return href
    return None


def _extract_text_field(soup: BeautifulSoup, sel: str | None) -> str:
    """
    Extract text from the first element matching the CSS selector.
    Returns empty string if element not found.
    """
    if not sel:
        return ""
    el = soup.select_one(sel)
    return el.get_text(strip=True) if el else ""


def extract_country(soup, parent_class):
    """
    Extract country name from Europages profile page.
    Looks for a div with `parent_class` and returns the text from the second <span>.
    """
    parent_div = soup.find('div', class_=parent_class)
    if parent_div:
        spans = parent_div.find_all('span')
        if len(spans) > 1:
            country_name = spans[1].get_text(strip=True)
            return country_name
    return None


def extract_profiles(cfg: Dict, logger) -> List[Dict]:
    """
    Main function to extract company profiles for a sector from Europages.

    Steps:
    1. Build paginated URLs from search page.
    2. Extract product URLs from each page, mapping them to company profile URLs.
    3. Visit each profile (or fallback to a sample product page) to extract:
       - company_name
       - country
       - profile_url
       - website_url

    Returns a list of dicts with these keys.
    """
    base_url = cfg["base_url"].rstrip("/")
    search_url = cfg["search_url"]
    max_pages = int(cfg.get("max_pages", 1))
    selectors = cfg.get("selectors", {})
    timeout = int(cfg.get("timeout", 25))
    req_cfg = RequestCfg(
        timeout=timeout,
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

    pages = _build_pages(search_url, max_pages)
    profile_to_sample_product: Dict[str, str] = {}

    # 1) Collect product links and map them to their profile URLs
    for idx, url in enumerate(pages, start=1):
        logger.info(f"Fetching results page {idx}/{len(pages)}: {url}")
        html = _request_text(url, req_cfg, logger)
        product_links = _extract_product_links_from_page(html, base_url, selectors)
        if not product_links:
            logger.warning(f"No product links found on page {idx}: {url}")

        for p in product_links:
            profile = _normalize_to_profile_url(p, base_url)
            if profile:
                profile_to_sample_product.setdefault(profile, p)

        _sleep(req_cfg.min_delay, req_cfg.max_delay)

    logger.info(f"Found {len(profile_to_sample_product)} unique company profiles across pages.")

    # 2) Visit each profile to extract metadata and external website
    profiles: List[Dict] = []
    for i, (profile_url, sample_product_url) in enumerate(profile_to_sample_product.items(), start=1):
        company_name = ""
        country = ""
        website = ""

        try:
            html_prof = _request_text(profile_url, req_cfg, logger)
            soup_prof = BeautifulSoup(html_prof, "html.parser")

            company_name = _extract_text_field(soup_prof, selectors.get("company_name"))
            country_class = 'flex gap-1 items-center mt-0.5'
            country = extract_country(soup_prof, country_class)

            website = _extract_website_from_profile_html(html_prof, selectors) or ""
        except Exception as e:
            logger.debug(f"Failed to fetch profile {profile_url}: {e}")

        if not website and sample_product_url:
            try:
                html_prod = _request_text(sample_product_url, req_cfg, logger)
                website = _extract_website_from_profile_html(html_prod, selectors) or ""
                if not company_name:
                    soup_prod = BeautifulSoup(html_prod, "html.parser")
                    company_name = _extract_text_field(soup_prod, selectors.get("company_name"))
                if not country:
                    soup_prod = BeautifulSoup(html_prod, "html.parser")
                    country = _extract_text_field(soup_prod, selectors.get("country"))
            except Exception as e:
                logger.debug(f"Failed to fetch product fallback {sample_product_url}: {e}")

        website = website or ""
        try:
            if website and "europages." in urlparse(website).netloc:
                website = ""
        except Exception:
            website = ""

        profiles.append({
            "company_name": company_name,
            "country": country,
            "profile_url": profile_url,
            "website_url": website,
        })

        _sleep(req_cfg.min_delay, req_cfg.max_delay)

    return profiles
