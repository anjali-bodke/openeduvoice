import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

from OpenEduVoice.core.audio import audio_converter, transcriber, tts_generator
from OpenEduVoice.core.reintegration.reintegrator_all import reintegrate_audio_to_pptx


class AudioConversionTests(unittest.TestCase):
    def test_conversion_failure_is_reported_to_the_workflow(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_dir = root / "input"
            input_dir.mkdir()
            (input_dir / "broken.mp3").touch()

            with (
                patch.object(
                    audio_converter.AudioSegment,
                    "from_file",
                    side_effect=OSError("invalid audio"),
                ),
                self.assertRaisesRegex(RuntimeError, "broken.mp3"),
            ):
                audio_converter.convert_audio_to_wav(
                    input_dir, root / "output", log_fn=lambda _: None
                )


class TranscriptionTests(unittest.TestCase):
    def test_empty_input_does_not_load_whisper_model(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_dir = root / "input"
            input_dir.mkdir()
            with patch.object(transcriber, "_init_model") as init_model:
                result = transcriber.transcribe_audio_files(
                    input_dir, root / "output", log_fn=lambda _: None
                )

        self.assertEqual(result, [])
        init_model.assert_not_called()

    def test_model_initialization_failure_is_propagated(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_dir = root / "input"
            input_dir.mkdir()
            (input_dir / "audio.wav").touch()

            with (
                patch.object(
                    transcriber, "_init_model", side_effect=RuntimeError("model unavailable")
                ),
                self.assertRaisesRegex(RuntimeError, "model unavailable"),
            ):
                transcriber.transcribe_audio_files(
                    input_dir, root / "output", log_fn=lambda _: None
                )

    def test_per_file_transcription_failure_is_propagated(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_dir = root / "input"
            input_dir.mkdir()
            (input_dir / "broken.wav").touch()
            model = Mock()
            model.transcribe.side_effect = OSError("decode failed")

            with (
                patch.object(transcriber, "_init_model", return_value=model),
                self.assertRaisesRegex(RuntimeError, "broken.wav"),
            ):
                transcriber.transcribe_audio_files(
                    input_dir, root / "output", log_fn=lambda _: None
                )


class TtsTests(unittest.TestCase):
    def _install_tts_stub(self, model):
        tts_module = types.ModuleType("TTS")
        api_module = types.ModuleType("TTS.api")
        api_module.TTS = Mock(return_value=model)
        tts_module.api = api_module
        return patch.dict("sys.modules", {"TTS": tts_module, "TTS.api": api_module})

    def test_per_file_tts_failure_is_propagated(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_dir = root / "input"
            input_dir.mkdir()
            (input_dir / "broken.txt").write_text("Hello", encoding="utf-8")
            model = Mock()
            model.tts_to_file.side_effect = OSError("synthesis failed")

            with self._install_tts_stub(model), self.assertRaisesRegex(
                RuntimeError, "broken.txt"
            ):
                tts_generator.text_to_speech(
                    input_dir,
                    root / "output",
                    "en",
                    {"English": "test-model"},
                    log=lambda _: None,
                    tts_lang="English",
                )

    def test_empty_text_does_not_generate_silent_audio(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_dir = root / "input"
            input_dir.mkdir()
            (input_dir / "empty.txt").write_text("", encoding="utf-8")
            model = Mock()

            with (
                self._install_tts_stub(model),
                patch.object(tts_generator.AudioSegment, "silent") as silent,
                self.assertRaisesRegex(RuntimeError, "empty.txt"),
            ):
                tts_generator.text_to_speech(
                    input_dir,
                    root / "output",
                    "en",
                    {"English": "test-model"},
                    log=lambda _: None,
                    tts_lang="English",
                )

        silent.assert_not_called()


class AudioReintegrationTests(unittest.TestCase):
    def test_invalid_content_types_stop_audio_reintegration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pptx_path = root / "lesson.pptx"
            tts_dir = root / "tts"
            tts_dir.mkdir()
            with zipfile.ZipFile(pptx_path, "w") as archive:
                archive.writestr("[Content_Types].xml", "not valid XML")
            original = pptx_path.read_bytes()

            with self.assertRaisesRegex(RuntimeError, "content types"):
                reintegrate_audio_to_pptx(
                    pptx_path, tts_dir, log_fn=lambda _: None
                )

            self.assertEqual(pptx_path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
