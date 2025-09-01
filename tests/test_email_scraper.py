import pytest
from src.email_scraper import _extract_emails_from_html


def test_extract_emails_from_html():
    html_doc = """
    <div>
      <p>Contact us at info@example.com for more info.</p>
      <a href="mailto:support@example.org?subject=Help">Support</a>
      <p>This is a junk email: myemail@2x-123.jpg</p>
      <p>Technical email: 2062d0a4929b45348643784b5cb39c36@sentry.wixpress.com</p>
    </div>
    """

    expected_emails = {
        "info@example.com",
        "support@example.org",
        "myemail@2x-123.jpg",
        "2062d0a4929b45348643784b5cb39c36@sentry.wixpress.com"
    }

    found_emails = _extract_emails_from_html(html_doc)

    assert found_emails == expected_emails