"""Download the models used by the default workflows into the configured caches."""

from faster_whisper.utils import download_model
from huggingface_hub import snapshot_download
from TTS.api import TTS

from OpenEduVoice.config.constants import TTS_LANGUAGE_MODEL_MAP
from OpenEduVoice.core.audio.transcriber import DEFAULT_WHISPER_MODEL
from OpenEduVoice.core.translation.nllb_model import _pick_model_name


def main() -> None:
    translation_model = _pick_model_name(None)
    print(f"Downloading translation model: {translation_model}", flush=True)
    snapshot_download(
        translation_model,
        ignore_patterns=["*.h5", "*.msgpack", "*.onnx"],
    )
    print(f"Downloading transcription model: {DEFAULT_WHISPER_MODEL}", flush=True)
    download_model(DEFAULT_WHISPER_MODEL)
    manager = TTS(progress_bar=True)
    for model in TTS_LANGUAGE_MODEL_MAP.values():
        print(f"Downloading speech model and vocoder: {model}", flush=True)
        manager.download_model_by_name(model)
    print("Default models are ready.", flush=True)


if __name__ == "__main__":
    main()
