import unittest
from unittest.mock import Mock, patch

from app.adapters.sources.email import EmailSourceAdapter


def _message(sender: str, subject: str, message_id: str) -> bytes:
    return (
        f"From: {sender}\r\n"
        f"Subject: {subject}\r\n"
        f"Message-ID: <{message_id}>\r\n"
        "Date: Wed, 19 Aug 2026 09:00:00 +0000\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Newsletter body"
    ).encode()


class EmailSourceAdapterTests(unittest.TestCase):
    @patch("app.adapters.sources.email.imaplib.IMAP4_SSL")
    def test_filters_shared_sender_address_by_display_name(self, imap_ssl):
        client = Mock()
        imap_ssl.return_value = client
        client.select.return_value = ("OK", [b""])
        client.search.return_value = ("OK", [b"1 2 3"])
        messages = {
            b"1": _message("TLDR AI <dan@tldrnewsletter.com>", "AI issue", "ai-1"),
            b"2": _message("TLDR Product <dan@tldrnewsletter.com>", "Product issue", "product-1"),
            b"3": _message("TLDR AI <other@example.com>", "Spoofed issue", "spoof-1"),
        }
        client.fetch.side_effect = lambda message_id, _: ("OK", [(b"RFC822", messages[message_id])])

        source = {
            "id": "email-tldr-ai",
            "name": "TLDR AI Email",
            "category": "AI 快讯与工具",
            "imap_host": "imap.gmail.com",
            "username_env": "AI_EMAIL_USERNAME",
            "password_env": "AI_EMAIL_PASSWORD",
            "from_address": "dan@tldrnewsletter.com",
            "from_name": "TLDR AI",
        }
        with patch.dict(
            "os.environ",
            {"AI_EMAIL_USERNAME": "reader@example.com", "AI_EMAIL_PASSWORD": "app-password"},
        ):
            items = EmailSourceAdapter().fetch(source)

        self.assertEqual([item.title for item in items], ["AI issue"])
        search_args = client.search.call_args.args
        self.assertEqual(search_args[0], None)
        self.assertIn("FROM", search_args)
        self.assertIn('"dan@tldrnewsletter.com"', search_args)
        imap_ssl.assert_called_once_with("imap.gmail.com", 993, timeout=20)
        client.select.assert_called_once_with("INBOX", readonly=True)
        client.logout.assert_called_once()


if __name__ == "__main__":
    unittest.main()
