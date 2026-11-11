import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform == "win32", "Windows launcher tests require Windows")
class WindowsLauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        shutil.copytree(ROOT / "scripts", cls.root / "scripts")
        for name in ("pyproject.toml", "requirements.lock.txt"):
            shutil.copy2(ROOT / name, cls.root / name)
        subprocess.run(
            [sys.executable, "-m", "venv", "--without-pip", str(cls.root / "venv")],
            check=True,
        )
        ffmpeg = cls.root / "tools" / "ffmpeg" / "bin"
        ffmpeg.mkdir(parents=True)
        (ffmpeg / "ffmpeg.exe").touch()
        (ffmpeg / "ffprobe.exe").touch()
        package = cls.root / "stubs" / "OpenEduVoice"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "app.py").write_text("main = None\n", encoding="utf-8")
        translation = package / "core" / "translation"
        translation.mkdir(parents=True)
        (package / "core" / "__init__.py").touch()
        (translation / "__init__.py").touch()
        (translation / "nllb_model.py").write_text("NLLBTranslator = None\n", encoding="utf-8")
        (cls.root / "stubs" / "faster_whisper.py").write_text("WhisperModel = None\n", encoding="utf-8")
        tts = cls.root / "stubs" / "TTS"
        tts.mkdir()
        (tts / "__init__.py").touch()
        (tts / "api.py").write_text("TTS = None\n", encoding="utf-8")
        (package / "__main__.py").write_text(
            "import os\nimport sys\nsys.exit(int(os.environ.get('TEST_APP_EXIT', '0')))\n",
            encoding="utf-8",
        )

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_process(self, command, app_exit=0):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(self.root / "stubs")
        env["TEST_APP_EXIT"] = str(app_exit)
        return subprocess.run(
            command, cwd=self.root, env=env, input="\n", text=True,
            capture_output=True, timeout=60,
        )

    def test_runner_reports_application_success_and_failure(self):
        script = self.root / "scripts" / "run_OpenEduVoice.ps1"
        command = ["powershell", "-NoProfile", "-File", str(script), "-Accel", "cpu"]
        success = self.run_process(command)
        self.assertEqual(success.returncode, 0, success.stdout + success.stderr)
        failure = self.run_process(command, app_exit=7)
        self.assertEqual(failure.returncode, 1, failure.stdout + failure.stderr)
        self.assertIn("OpenEduVoice exited with code 7", failure.stdout)

    def test_runner_configures_project_local_model_caches(self):
        stub = self.root / "stubs" / "OpenEduVoice" / "__main__.py"
        original = stub.read_text(encoding="utf-8")
        stub.write_text(
            "import os\nfrom pathlib import Path\n"
            "Path('cache-paths.txt').write_text(os.environ['HF_HOME'] + '\\n' + "
            "os.environ['HF_HUB_CACHE'] + '\\n' + os.environ['TTS_HOME'], encoding='utf-8')\n",
            encoding="utf-8",
        )
        try:
            result = self.run_process([
                "powershell", "-NoProfile", "-File",
                str(self.root / "scripts" / "run_OpenEduVoice.ps1"), "-Accel", "cpu",
            ])
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(
                (self.root / "cache-paths.txt").read_text(encoding="utf-8").splitlines(),
                [str(self.root / "models" / "huggingface"),
                 str(self.root / "models" / "huggingface" / "hub"),
                 str(self.root / "models" / "coqui")],
            )
        finally:
            stub.write_text(original, encoding="utf-8")

    def test_runner_rejects_broken_application_imports(self):
        stub = self.root / "stubs" / "TTS" / "api.py"
        original = stub.read_text(encoding="utf-8")
        stub.write_text("raise ImportError('broken dependency')\n", encoding="utf-8")
        try:
            result = self.run_process([
                "powershell", "-NoProfile", "-File",
                str(self.root / "scripts" / "run_OpenEduVoice.ps1"), "-Accel", "cpu",
            ])
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("Application dependencies are missing or broken", result.stdout)
        finally:
            stub.write_text(original, encoding="utf-8")

    def test_batch_launcher_propagates_application_failure(self):
        result = self.run_process(
            [os.environ["COMSPEC"], "/d", "/c", str(self.root / "scripts" / "run_OpenEduVoice.bat")],
            app_exit=7,
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("exit code 1", result.stdout)

    def test_installer_preserves_existing_venv_when_mode_changes(self):
        marker = self.root / "venv" / ".openeduvoice_mode.txt"
        marker.write_text("cpu", encoding="utf-8")
        sentinel = self.root / "venv" / "keep.txt"
        sentinel.write_text("preserve", encoding="utf-8")
        try:
            result = self.run_process([
                "powershell", "-NoProfile", "-File",
                str(self.root / "scripts" / "install_OpenEduVoice.ps1"),
                "-Accel", "cuda",
            ])
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("Back up or remove it manually", result.stdout)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve")
        finally:
            marker.unlink()
            sentinel.unlink()

    def test_batch_installer_reports_missing_lock(self):
        lock = self.root / "requirements.lock.txt"
        backup = self.root / "requirements.lock.backup"
        lock.rename(backup)
        try:
            result = self.run_process([
                os.environ["COMSPEC"], "/d", "/c",
                str(self.root / "scripts" / "install_OpenEduVoice.bat"), "cpu",
            ])
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("Missing required file", result.stdout)
            self.assertIn("Installation failed", result.stdout)
        finally:
            backup.rename(lock)

    def test_installer_extracts_cached_ffmpeg_without_removing_other_files(self):
        ffmpeg = self.root / "tools" / "ffmpeg"
        binary_dir = ffmpeg / "bin"
        cached = ffmpeg / "ffmpeg-release-essentials.zip"
        unrelated = ffmpeg / "_tmp_extract"
        unrelated.mkdir()
        (unrelated / "keep.txt").write_text("keep", encoding="utf-8")
        for name in ("ffmpeg.exe", "ffprobe.exe"):
            (binary_dir / name).unlink()
        with zipfile.ZipFile(cached, "w") as archive:
            for name in ("ffmpeg.exe", "ffprobe.exe"):
                archive.writestr("build/bin/" + name, name)
        marker = self.root / "venv" / ".openeduvoice_mode.txt"
        marker.write_text("cpu", encoding="utf-8")
        try:
            result = self.run_process([
                "powershell", "-NoProfile", "-File",
                str(self.root / "scripts" / "install_OpenEduVoice.ps1"),
                "-Accel", "cuda",
            ])
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("Back up or remove it manually", result.stdout)
            self.assertEqual((binary_dir / "ffmpeg.exe").read_text(), "ffmpeg.exe")
            self.assertEqual((binary_dir / "ffprobe.exe").read_text(), "ffprobe.exe")
            self.assertEqual((unrelated / "keep.txt").read_text(), "keep")
        finally:
            marker.unlink()


if __name__ == "__main__":
    unittest.main()
