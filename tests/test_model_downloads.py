import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]


def module(name, **attributes):
    result = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(result, key, value)
    return result


class ModelDownloadTests(unittest.TestCase):
    def test_downloads_selected_models_and_speech_vocoders(self):
        whisper = Mock()
        snapshot = Mock()
        tts = Mock()
        dependencies = {
            "faster_whisper": module("faster_whisper"),
            "faster_whisper.utils": module("faster_whisper.utils", download_model=whisper),
            "huggingface_hub": module("huggingface_hub", snapshot_download=snapshot),
            "TTS": module("TTS"),
            "TTS.api": module("TTS.api", TTS=Mock(return_value=tts)),
            "OpenEduVoice.core.audio.transcriber": module(
                "OpenEduVoice.core.audio.transcriber", DEFAULT_WHISPER_MODEL="medium"
            ),
            "OpenEduVoice.core.translation.nllb_model": module(
                "OpenEduVoice.core.translation.nllb_model",
                _pick_model_name=Mock(return_value="selected-model"),
            ),
        }
        with patch.dict(sys.modules, dependencies):
            spec = importlib.util.spec_from_file_location(
                "download_models", ROOT / "scripts" / "download_models.py"
            )
            downloader = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(downloader)
            downloader.main()
        snapshot.assert_called_once_with(
            "selected-model", ignore_patterns=["*.h5", "*.msgpack", "*.onnx"]
        )
        whisper.assert_called_once_with("medium")
        self.assertEqual(tts.download_model_by_name.call_count, 2)

    def test_download_errors_are_not_suppressed(self):
        snapshot = Mock(side_effect=RuntimeError("network unavailable"))
        dependencies = {
            "faster_whisper": module("faster_whisper"),
            "faster_whisper.utils": module("faster_whisper.utils", download_model=Mock()),
            "huggingface_hub": module("huggingface_hub", snapshot_download=snapshot),
            "TTS": module("TTS"),
            "TTS.api": module("TTS.api", TTS=Mock()),
            "OpenEduVoice.core.audio.transcriber": module(
                "OpenEduVoice.core.audio.transcriber", DEFAULT_WHISPER_MODEL="medium"
            ),
            "OpenEduVoice.core.translation.nllb_model": module(
                "OpenEduVoice.core.translation.nllb_model",
                _pick_model_name=Mock(return_value="selected-model"),
            ),
        }
        with patch.dict(sys.modules, dependencies):
            spec = importlib.util.spec_from_file_location(
                "download_models_failure", ROOT / "scripts" / "download_models.py"
            )
            downloader = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(downloader)
            with self.assertRaisesRegex(RuntimeError, "network unavailable"):
                downloader.main()


if __name__ == "__main__":
    unittest.main()
