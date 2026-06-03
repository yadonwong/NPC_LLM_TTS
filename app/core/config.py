import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict

BASE_DIR = Path(__file__).resolve().parents[2]
SETTINGS_PATH = BASE_DIR / "config" / "settings.json"

DEFAULT_SETTINGS: Dict[str, Any] = {
    "last_excel_path": "",
    "device": "auto",
    "cfg_value": 2.0,
    "inference_timesteps": 10,
    "load_denoiser": False,
    "enable_loudness_normalization": True,
    "target_lufs": -18.0,
    "true_peak_ceiling": -1.0,
    "overwrite_policy": "skip",
    "reuse_voice_cache": True,
    "model_path": str(BASE_DIR / "models" / "VoxCPM2"),
    "output_dir": str(BASE_DIR / "Output"),
    "voice_cache_dir": str(BASE_DIR / "VoiceCache"),
    "ref_dir": str(BASE_DIR / "ref"),
    "batch_pause_seconds": 0.0,
    "random_seed": "",
    "tts_engine": "voxcpm",
    "index_model_path": str(BASE_DIR / "models" / "IndexTTS-2"),
}

@dataclass
class AppConfig:
    last_excel_path: str = ""
    device: str = "auto"
    cfg_value: float = 2.0
    inference_timesteps: int = 10
    load_denoiser: bool = False
    enable_loudness_normalization: bool = True
    target_lufs: float = -18.0
    true_peak_ceiling: float = -1.0
    overwrite_policy: str = "skip"
    reuse_voice_cache: bool = True
    model_path: str = str(BASE_DIR / "models" / "VoxCPM2")
    output_dir: str = str(BASE_DIR / "Output")
    voice_cache_dir: str = str(BASE_DIR / "VoiceCache")
    ref_dir: str = str(BASE_DIR / "ref")
    batch_pause_seconds: float = 0.0
    random_seed: str = ""
    tts_engine: str = "voxcpm"
    index_model_path: str = str(BASE_DIR / "models" / "IndexTTS-2")


def load_settings() -> AppConfig:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not SETTINGS_PATH.exists():
        save_settings(AppConfig())
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        data = DEFAULT_SETTINGS.copy()
    merged = DEFAULT_SETTINGS.copy()
    merged.update(data)

    # migrate legacy IndexTTS path from third_party to models dir
    legacy_suffix = str(Path("third_party") / "index-tts" / "checkpoints")
    current_index_path = str(merged.get("index_model_path", ""))
    preferred_index_path = str(BASE_DIR / "models" / "IndexTTS-2")
    if (not current_index_path) or current_index_path.endswith(legacy_suffix):
        merged["index_model_path"] = preferred_index_path

    config = AppConfig(**merged)
    save_settings(config)
    return config


def save_settings(config: AppConfig) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(
        json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8"
    )
