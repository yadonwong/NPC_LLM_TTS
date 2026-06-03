from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf
import librosa
import pyloudnorm as pyln


@dataclass
class LoudnessResult:
    original_lufs: Optional[float]
    target_lufs: Optional[float]
    final_lufs: Optional[float]
    peak_dbfs: Optional[float]
    normalized_ok: bool
    message: str


def ensure_mono(audio: np.ndarray) -> np.ndarray:
    if audio.ndim == 1:
        return audio
    if audio.ndim == 2:
        return audio.mean(axis=1)
    raise ValueError("Unsupported audio shape")


def sanitize_audio(audio: np.ndarray) -> np.ndarray:
    audio = np.asarray(audio, dtype=np.float32)
    audio = np.nan_to_num(audio, nan=0.0, posinf=0.0, neginf=0.0)
    return audio


def resample_to_48k(audio: np.ndarray, source_sr: int) -> np.ndarray:
    if source_sr == 48000:
        return audio
    return librosa.resample(audio, orig_sr=source_sr, target_sr=48000)


def dbfs_peak(audio: np.ndarray) -> float:
    peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
    if peak <= 0:
        return -120.0
    return 20 * np.log10(peak)


def prevent_clipping(audio: np.ndarray, ceiling_db: float = -1.0) -> np.ndarray:
    ceiling_amp = 10 ** (ceiling_db / 20.0)
    peak = np.max(np.abs(audio)) if len(audio) else 0.0
    if peak > ceiling_amp and peak > 0:
        audio = audio * (ceiling_amp / peak)
    return audio


def normalize_lufs(audio: np.ndarray, sr: int, target_lufs: float, true_peak_ceiling: float) -> tuple[np.ndarray, LoudnessResult]:
    try:
        meter = pyln.Meter(sr)
        original = float(meter.integrated_loudness(audio))
        norm = pyln.normalize.loudness(audio, original, target_lufs)
        norm = prevent_clipping(norm, ceiling_db=true_peak_ceiling)
        final = float(meter.integrated_loudness(norm))
        peak = dbfs_peak(norm)
        return norm, LoudnessResult(original, target_lufs, final, peak, True, "ok")
    except Exception as e:
        return audio, LoudnessResult(None, target_lufs, None, dbfs_peak(audio), False, str(e))


def save_wav_24bit(path: str, audio: np.ndarray, sr: int = 48000) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, audio, sr, subtype="PCM_24")
