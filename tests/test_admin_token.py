import tempfile
import unittest
from pathlib import Path

from app.admin_token import configure_admin_token


class AdminTokenTests(unittest.TestCase):
    def test_configure_replaces_existing_token_without_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("OTHER=value\nADMIN_API_TOKEN=old\n", encoding="utf-8")

            fingerprint = configure_admin_token(path)
            lines = path.read_text(encoding="utf-8").splitlines()
            token_lines = [line for line in lines if line.startswith("ADMIN_API_TOKEN=")]

            self.assertEqual(len(fingerprint), 12)
            self.assertEqual(lines[0], "OTHER=value")
            self.assertEqual(len(token_lines), 1)
            self.assertGreaterEqual(len(token_lines[0].split("=", 1)[1]), 32)


if __name__ == "__main__":
    unittest.main()
