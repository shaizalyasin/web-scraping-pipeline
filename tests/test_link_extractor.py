import pytest
from src.link_extractor import _extract_product_links_from_page


def test_extract_product_links_from_page():
    # HTML snippet that mimics the Europages structure
    html_doc = """
    <div data-test='product'>
      <a href="/en/company/example-123456/products/product-a">Product A</a>
    </div>
    <div data-test='product'>
      <a href="/en/company/another-company-789012/products/product-b">Product B</a>
    </div>
    <div data-test='product'>
      <a href="/en/company/third-company-345678">Third Company</a>
    </div>
    """

    base_url = "https://www.europages.com"
    selectors = {
        "product_cards": "[data-test='product']",
        "product_links": "a[href*='/products/']"
    }

    # URLs after normalization
    expected_urls = {
        "https://www.europages.com/en/company/example-123456/products/product-a",
        "https://www.europages.com/en/company/another-company-789012/products/product-b"
    }

    found_links = _extract_product_links_from_page(html_doc, base_url, selectors)

    assert found_links == expected_urls
    assert "https://www.europages.com/en/company/third-company-345678" not in found_links