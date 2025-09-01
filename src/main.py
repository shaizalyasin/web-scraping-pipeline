from pathlib import Path
import argparse
import csv
import yaml
from utils.logger import setup_logger

from link_extractor import extract_profiles as europages_extractor
from yellowpages_extractor import extract_profiles as yellowpages_extractor
from email_scraper import scrape_emails_for_profiles, _normalize_url
from data_cleaner import clean_and_validate_emails


def sector_slug_from_key(key: str) -> str:
    return key.split("_", 1)[1] if "_" in key else key


def main():
    parser = argparse.ArgumentParser(description="Full pipeline: extract profiles, links and emails.")
    parser.add_argument("--root", default="..", help="Repo root (parent of src/)")
    parser.add_argument("--sector", required=True, help="Sector key (e.g., 'europages_wine' or 'yellowpages_uae')")
    parser.add_argument("--category", help="Category for yellowpages_uae sector (e.g., 'event-management')")
    parser.add_argument("--skip-emails", action="store_true", help="Run link extraction only")
    args = parser.parse_args()

    root = Path(args.root).resolve()

    # Select config file based on sector name
    if "yellowpages" in args.sector:
        cfg_path = root / "config" / "yellowpages-uae.yaml"
    else:
        cfg_path = root / "config" / "sectors.yaml"

    logs_dir = root / "logs"
    data_raw = root / "data" / "raw"
    data_processed = root / "data" / "processed"

    logger = setup_logger("pipeline", logs_dir)

    with open(cfg_path, "r", encoding="utf-8") as f:
        all_cfg = yaml.safe_load(f)

    cfg_key = args.sector
    if cfg_key not in all_cfg:
        logger.error(f"Sector '{cfg_key}' not found in {cfg_path}")
        return

    cfg = all_cfg[cfg_key]

    # Handle category for yellowpages_uae
    if "yellowpages" in args.sector:
        if not args.category:
            logger.error("Category must be provided for yellowpages sector. Use --category <name>.")
            return
        cfg["category"] = args.category

    slug = args.category if "yellowpages" in args.sector else sector_slug_from_key(args.sector)
    logger.info(f"Using slug '{slug}' for file names.")

    # 1. Extract profiles (profile metadata + website_url)
    if "yellowpages" in args.sector:
        profiles = yellowpages_extractor(cfg, logger)
    else:
        profiles = europages_extractor(cfg, logger)

    logger.info(f"Number of profiles extracted: {len(profiles)}")

    # Save profiles as a checkpoint
    profiles_path = data_raw / f"profiles_{slug}.csv"
    profiles_path.parent.mkdir(parents=True, exist_ok=True)
    with open(profiles_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["company_name", "country", "profile_url", "website_url"])
        w.writeheader()
        for r in profiles:
            w.writerow({
                "company_name": r.get("company_name", ""),
                "country": r.get("country", ""),
                "profile_url": r.get("profile_url", ""),
                "website_url": r.get("website_url", ""),
            })
    logger.info(f"Saved {len(profiles)} profiles -> {profiles_path}")

    # 2. Save personal websites (normalized and deduplicated)
    personal_sites = [
        _normalize_url(p["website_url"]) for p in profiles if p.get("website_url")
    ]
    personal_sites = sorted(set(personal_sites))
    links_out = data_processed / f"links_{slug}.csv"
    links_out.parent.mkdir(parents=True, exist_ok=True)
    with open(links_out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["url"])
        for u in personal_sites:
            w.writerow([u])
    logger.info(f"Saved {len(personal_sites)} personal websites -> {links_out}")

    if args.skip_emails:
        logger.info("skip-emails set; stopping after link extraction.")
        return

    # 3. Run email scraper
    email_cfg = cfg.get("email", {})
    request_cfg = {
        "timeout": cfg.get("timeout", 20),
        "retries": cfg.get("retries", 3),
        "backoff_factor": float(cfg.get("backoff_factor", 1.5)),
        "min_delay_seconds": float(cfg.get("min_delay", 0.8)),
        "max_delay_seconds": float(cfg.get("max_delay", 1.8)),
        "headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36"
            ),
        }
    }

    try:
        raw_emails = scrape_emails_for_profiles(profiles, email_cfg, request_cfg, logger)
    except Exception as e:
        logger.error(f"Email scraping failed: {e}")
        raw_emails = []

    # 4. Clean and validate the extracted emails
    ignore_domains = set(email_cfg.get("ignore_domains", []))
    cleaned_emails = clean_and_validate_emails(raw_emails, ignore_domains)

    # 5. Save final emails -> data/processed/emails_<sector>.csv
    emails_out = data_processed / f"emails_{slug}.csv"
    emails_out.parent.mkdir(parents=True, exist_ok=True)
    with open(emails_out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["company_name", "country", "email"])
        w.writeheader()
        for r in cleaned_emails:
            w.writerow({
                "company_name": r.get("company_name", ""),
                "country": r.get("country", ""),
                "email": r.get("email", "")
            })
    logger.info(f"Saved {len(cleaned_emails)} email rows -> {emails_out}")


if __name__ == "__main__":
    main()
