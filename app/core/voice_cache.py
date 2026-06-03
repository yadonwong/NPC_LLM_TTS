import json
import shutil
from datetime import datetime
from pathlib import Path


class VoiceCacheManager:
    def __init__(self, cache_dir: str, ref_dir: str):
        self.cache_dir = Path(cache_dir)
        self.ref_dir = Path(ref_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ref_dir.mkdir(parents=True, exist_ok=True)

    def voice_dir(self, voice_id: str) -> Path:
        d = self.cache_dir / voice_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def reference_path(self, voice_id: str) -> Path:
        return self.voice_dir(voice_id) / "reference.wav"

    def ref_pool_path(self, voice_id: str) -> Path:
        return self.ref_dir / f"{voice_id}.wav"

    def has_reference(self, voice_id: str) -> bool:
        return self.reference_path(voice_id).exists() or self.ref_pool_path(voice_id).exists()

    def get_effective_reference_path(self, voice_id: str) -> Path | None:
        p1 = self.reference_path(voice_id)
        if p1.exists():
            return p1
        p2 = self.ref_pool_path(voice_id)
        if p2.exists():
            return p2
        return None

    def import_manual_reference(self, voice_id: str, source_wav_path: str) -> Path:
        target = self.ref_pool_path(voice_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_wav_path, target)
        return target

    def save_reference(self, voice_id: str, generated_wav_path: str, script_id: str, source_text: str, sample_rate: int = 48000) -> None:
        vdir = self.voice_dir(voice_id)
        ref = vdir / "reference.wav"
        shutil.copy2(generated_wav_path, ref)
        shutil.copy2(generated_wav_path, self.ref_pool_path(voice_id))
        meta = {
            "voice_id": voice_id,
            "source_script_id": script_id,
            "source_text": source_text,
            "created_at": datetime.now().isoformat(),
            "sample_rate": sample_rate,
            "note": "First generated line used as speaker reference for this VoiceID",
        }
        (vdir / "reference_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    def clear_all(self) -> int:
        count = 0
        for p in self.cache_dir.glob("*/reference.wav"):
            p.unlink(missing_ok=True)
            (p.parent / "reference_meta.json").unlink(missing_ok=True)
            count += 1
        for p in self.ref_dir.glob("*.wav"):
            p.unlink(missing_ok=True)
        return count

    def clear_one(self, voice_id: str) -> bool:
        ref = self.reference_path(voice_id)
        pool = self.ref_pool_path(voice_id)
        existed = ref.exists() or pool.exists()
        ref.unlink(missing_ok=True)
        pool.unlink(missing_ok=True)
        (ref.parent / "reference_meta.json").unlink(missing_ok=True)
        return existed

    def status_map(self, voice_ids):
        return {vid: ("已有参考" if self.has_reference(vid) else "未生成参考") for vid in voice_ids}

    def list_reference_voice_ids(self) -> list[str]:
        ids = set()
        if self.cache_dir.exists():
            for p in self.cache_dir.glob("*/reference.wav"):
                ids.add(p.parent.name)
        if self.ref_dir.exists():
            for p in self.ref_dir.glob("*.wav"):
                ids.add(p.stem)
        return sorted(ids)
