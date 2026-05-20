import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from env_check import check_environment


class V3EnvCheckTest(unittest.TestCase):
    def test_check_environment_reports_dependencies(self):
        result = check_environment(soffice_search_paths=[])

        self.assertIn("python", result["checks"])
        self.assertIn("libreoffice", result["checks"])
        self.assertIn("pymupdf", result["checks"])
        self.assertIn("pillow", result["checks"])
        self.assertTrue(result["checks"]["python"]["ok"])
        self.assertTrue(result["checks"]["pymupdf"]["ok"])
        self.assertTrue(result["checks"]["pillow"]["ok"])
        self.assertFalse(result["checks"]["libreoffice"]["ok"])
        self.assertIn("LibreOffice", result["checks"]["libreoffice"]["message"])


if __name__ == "__main__":
    unittest.main()
