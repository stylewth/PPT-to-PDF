import json
import shutil
import subprocess
import sys
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))
TMP_ROOT = Path(__file__).resolve().parents[1] / "workspace" / "test_runs"
TMP_ROOT.mkdir(parents=True, exist_ok=True)
SAMPLE_PPTX = Path(__file__).resolve().parents[1] / "samples" / "course_animation_occlusion.pptx"

from converter import convert_pptx
from native_converter import NativeConversionError, convert_pptx_to_pdf


@contextmanager
def workspace_tmpdir():
    path = TMP_ROOT / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


class FakeSofficeRunner:
    def __init__(self, *, returncode=0, stdout="converted", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.commands = []

    def __call__(self, command, *, timeout, capture_output, text, **kwargs):
        self.commands.append(command)
        if self.returncode == 0:
            outdir = Path(command[command.index("--outdir") + 1])
            source = Path(command[-1])
            (outdir / f"{source.stem}.pdf").write_bytes(b"%PDF-1.7\n%fake native pdf\n")
        return subprocess.CompletedProcess(
            command,
            self.returncode,
            stdout=self.stdout,
            stderr=self.stderr,
        )


class V3NativeConverterTest(unittest.TestCase):
    def test_native_converter_reports_missing_libreoffice(self):
        with workspace_tmpdir() as tmp:
            with self.assertRaisesRegex(NativeConversionError, "LibreOffice"):
                convert_pptx_to_pdf(
                    SAMPLE_PPTX,
                    tmp,
                    search_paths=[],
                )

    def test_native_converter_writes_base_pdf_from_soffice_output(self):
        with workspace_tmpdir() as tmp:
            fake_soffice = tmp / "soffice.exe"
            fake_soffice.write_text("fake executable", encoding="utf-8")
            runner = FakeSofficeRunner()

            pdf_path = convert_pptx_to_pdf(
                SAMPLE_PPTX,
                tmp,
                soffice_path=fake_soffice,
                command_runner=runner,
            )

            self.assertEqual(pdf_path.name, "base.pdf")
            self.assertTrue(pdf_path.exists())
            self.assertGreater(pdf_path.stat().st_size, 0)
            self.assertIn("--headless", runner.commands[0])
            self.assertIn("--convert-to", runner.commands[0])
            self.assertTrue(
                any(str(arg).startswith("-env:UserInstallation=file:///") for arg in runner.commands[0])
            )

    def test_converter_outputs_v3a_package_fields(self):
        with workspace_tmpdir() as tmp:
            fake_soffice = tmp / "soffice.exe"
            fake_soffice.write_text("fake executable", encoding="utf-8")
            output_dir = tmp / "out"

            result = convert_pptx(
                SAMPLE_PPTX,
                output_dir,
                render_pdf=True,
                soffice_path=fake_soffice,
                command_runner=FakeSofficeRunner(),
            )

            self.assertEqual(result["status"], "ok")
            self.assertTrue(Path(result["base_pdf_path"]).exists())
            self.assertTrue(Path(result["guide_pdf_path"]).exists())
            self.assertTrue(Path(result["analysis_path"]).exists())
            self.assertTrue(Path(result["augment_plan_path"]).exists())
            self.assertTrue(Path(result["report_path"]).exists())
            self.assertTrue(Path(result["preview_html_path"]).exists())

            report = json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))
            self.assertEqual(report["version"], "v3d")
            self.assertEqual(report["outputs"]["base_pdf"], "base.pdf")
            self.assertEqual(report["outputs"]["guide_pdf"], "guide.pdf")
            self.assertEqual(report["outputs"]["analysis_json"], "analysis.json")
            self.assertEqual(report["outputs"]["augment_plan_json"], "augment_plan.json")


if __name__ == "__main__":
    unittest.main()
