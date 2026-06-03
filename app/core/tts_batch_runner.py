import csv
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import Event
from typing import Dict, List

import numpy as np
from PySide6.QtCore import QObject, Signal

from .audio_processor import (
    ensure_mono,
    normalize_lufs,
    prevent_clipping,
    resample_to_48k,
    sanitize_audio,
    save_wav_24bit,
)
from .excel_loader import safe_filename
from .output_namer import build_output_path, resolve_existing_path


@dataclass
class BatchRowResult:
    row_index: int
    VoiceID: str
    台本ID: str
    区域: str
    细分区域: str
    TOTTS: str
    output_path: str
    status: str
    error_message: str
    used_reference_wav: str
    is_reference_created: bool
    original_lufs: float | None
    target_lufs: float | None
    final_lufs: float | None
    duration_seconds: float
    created_at: str


class BatchRunner(QObject):
    row_status = Signal(int, str, str)
    progress = Signal(int, int)
    current = Signal(str, str, str)
    finished = Signal(dict)
    log = Signal(str)

    @staticmethod
    def parse_totts(text: str) -> tuple[str, str, str]:
        raw = str(text or "").strip()
        if not raw:
            return "", "", ""
        if raw.startswith("(") and ")" in raw:
            idx = raw.find(")")
            control = raw[1:idx].strip()
            target = raw[idx + 1 :].strip()
            combined = raw
            return combined, control, target
        return raw, "", raw

    def __init__(self, df, config, tts_model, voice_cache_manager, logger):
        super().__init__()
        self.df = df
        self.config = config
        self.tts_model = tts_model
        self.voice_cache_manager = voice_cache_manager
        self.logger = logger
        self.pause_event = Event()
        self.stop_event = Event()
        self.pause_event.set()

    def pause(self):
        self.pause_event.clear()

    def resume(self):
        self.pause_event.set()

    def stop(self):
        self.stop_event.set()
        self.pause_event.set()

    def _synthesize_one(self, text, used_ref, path, control_instruction=""):
        txt = str(text or "").strip()
        ctrl = str(control_instruction or "").strip()
        final_text = f"({ctrl}){txt}" if ctrl else txt

        wav, sr = self.tts_model.generate(
            text=final_text,
            cfg_value=float(self.config.cfg_value),
            inference_timesteps=int(self.config.inference_timesteps),
            reference_wav_path=used_ref if used_ref else None,
            random_seed=int(self.config.random_seed) if str(self.config.random_seed).strip().isdigit() else None,
        )

        audio = sanitize_audio(np.asarray(wav))
        audio = ensure_mono(audio)
        audio = resample_to_48k(audio, sr)
        audio = prevent_clipping(audio, 0.0)

        lufs_info = None
        if self.config.enable_loudness_normalization:
            audio, lufs_info = normalize_lufs(
                audio,
                48000,
                float(self.config.target_lufs),
                float(self.config.true_peak_ceiling),
            )

        save_wav_24bit(str(path), audio, sr=48000)
        return audio, lufs_info

    def run(self):
        results: List[BatchRowResult] = []
        total = len(self.df)
        done = 0
        failed_ref_voice: Dict[str, bool] = {}

        for i, row in self.df.iterrows():
            if self.stop_event.is_set():
                self.logger.info("收到停止请求，安全停止。")
                break
            self.pause_event.wait()

            row_idx = int(row.get("_row_index", i + 2))
            voice_id = safe_filename(row.get("VoiceID", ""))
            script_id = safe_filename(row.get("台本ID", ""))
            region = safe_filename(row.get("区域", "UNKNOWN"))
            subregion = safe_filename(row.get("细分区域", ""))
            if subregion == "UNKNOWN":
                subregion = ""
            totts_cn = str(row.get("TOTTS_CN", row.get("TOTTS", "")))
            totts_en = str(row.get("TOTTS_EN", row.get("TOTTS_EN_AUTO", "")))
            control_instruction = str(row.get("CONTROL_INSTRUCTION", "")).strip()

            if not voice_id or voice_id == "UNKNOWN" or not script_id or script_id == "UNKNOWN":
                self.row_status.emit(i, "Skipped", "VoiceID/台本ID为空")
                done += 1
                self.progress.emit(done, total)
                continue

            if not totts_cn.strip():
                self.row_status.emit(i, "Skipped", "TOTTS为空")
                done += 1
                self.progress.emit(done, total)
                continue

            if failed_ref_voice.get(voice_id):
                self.row_status.emit(i, "Skipped", "等待参考失败")
                done += 1
                self.progress.emit(done, total)
                continue

            self.row_status.emit(i, "Generating", "")
            ref_created = False
            used_ref = ""

            try:
                ref_path = self.voice_cache_manager.get_effective_reference_path(voice_id)
                requested_ref_wav = str(row.get("REFERENCE_WAV_PATH", "")).strip()
                if requested_ref_wav:
                    custom_ref_path = Path(requested_ref_wav)
                    if not custom_ref_path.exists() or not custom_ref_path.is_file():
                        raise ValueError(f"参考音频文件不存在: {requested_ref_wav}")
                    ref_path = custom_ref_path
                has_ref = ref_path is not None
                if not self.config.reuse_voice_cache:
                    has_ref = False
                    ref_path = None
                if has_ref and ref_path is not None:
                    used_ref = str(ref_path)

                # CN
                cn_path = build_output_path(self.config.output_dir, "CN", region, subregion, voice_id, script_id)
                cn_skip, cn_path = resolve_existing_path(cn_path, self.config.overwrite_policy)
                if not cn_skip:
                    self.current.emit(voice_id, script_id, str(cn_path))
                    audio_cn, lufs_cn = self._synthesize_one(totts_cn, used_ref, cn_path, control_instruction=control_instruction)
                    if not has_ref:
                        self.voice_cache_manager.save_reference(voice_id, str(cn_path), script_id, totts_cn, 48000)
                        ref_created = True
                        new_ref = self.voice_cache_manager.get_effective_reference_path(voice_id)
                        used_ref = str(new_ref) if new_ref else used_ref
                    duration_cn = len(audio_cn) / 48000.0
                    status_cn = "Done" if (lufs_cn is None or lufs_cn.normalized_ok) else "Done (NormalizeFailed)"
                    msg_cn = "" if status_cn == "Done" else lufs_cn.message
                    results.append(BatchRowResult(
                        row_index=row_idx, VoiceID=voice_id, 台本ID=script_id, 区域=region, 细分区域=subregion,
                        TOTTS=totts_cn, output_path=str(cn_path), status=status_cn, error_message=msg_cn,
                        used_reference_wav=used_ref, is_reference_created=ref_created,
                        original_lufs=(None if lufs_cn is None else lufs_cn.original_lufs),
                        target_lufs=(None if lufs_cn is None else lufs_cn.target_lufs),
                        final_lufs=(None if lufs_cn is None else lufs_cn.final_lufs),
                        duration_seconds=duration_cn, created_at=datetime.now().isoformat(),
                    ))
                else:
                    results.append(BatchRowResult(
                        row_index=row_idx, VoiceID=voice_id, 台本ID=script_id, 区域=region, 细分区域=subregion,
                        TOTTS=totts_cn, output_path=str(cn_path), status="Skipped", error_message="CN文件已存在",
                        used_reference_wav=used_ref, is_reference_created=False, original_lufs=None,
                        target_lufs=None, final_lufs=None, duration_seconds=0.0, created_at=datetime.now().isoformat(),
                    ))

                # EN
                if totts_en.strip():
                    en_path = build_output_path(self.config.output_dir, "EN", region, subregion, voice_id, script_id)
                    en_skip, en_path = resolve_existing_path(en_path, self.config.overwrite_policy)
                    if not en_skip:
                        self.current.emit(voice_id, script_id, str(en_path))
                        audio_en, lufs_en = self._synthesize_one(totts_en, used_ref, en_path, control_instruction=control_instruction)
                        duration_en = len(audio_en) / 48000.0
                        status_en = "Done" if (lufs_en is None or lufs_en.normalized_ok) else "Done (NormalizeFailed)"
                        msg_en = "" if status_en == "Done" else lufs_en.message
                        results.append(BatchRowResult(
                            row_index=row_idx, VoiceID=voice_id, 台本ID=script_id, 区域=region, 细分区域=subregion,
                            TOTTS=totts_en, output_path=str(en_path), status=status_en, error_message=msg_en,
                            used_reference_wav=used_ref, is_reference_created=False,
                            original_lufs=(None if lufs_en is None else lufs_en.original_lufs),
                            target_lufs=(None if lufs_en is None else lufs_en.target_lufs),
                            final_lufs=(None if lufs_en is None else lufs_en.final_lufs),
                            duration_seconds=duration_en, created_at=datetime.now().isoformat(),
                        ))
                    else:
                        results.append(BatchRowResult(
                            row_index=row_idx, VoiceID=voice_id, 台本ID=script_id, 区域=region, 细分区域=subregion,
                            TOTTS=totts_en, output_path=str(en_path), status="Skipped", error_message="EN文件已存在",
                            used_reference_wav=used_ref, is_reference_created=False, original_lufs=None,
                            target_lufs=None, final_lufs=None, duration_seconds=0.0, created_at=datetime.now().isoformat(),
                        ))
                else:
                    self.logger.info("Row %s 无英文文本，跳过EN导出", row_idx)

                self.row_status.emit(i, "Done", "CN/EN 导出完成(若EN有文本)")
            except Exception as e:
                self.logger.exception("Row failed: %s", e)
                if not self.voice_cache_manager.has_reference(voice_id):
                    failed_ref_voice[voice_id] = True
                self.row_status.emit(i, "Failed", str(e))
                results.append(BatchRowResult(
                    row_index=row_idx, VoiceID=voice_id, 台本ID=script_id, 区域=region, 细分区域=subregion,
                    TOTTS=totts_cn, output_path="", status="Failed", error_message=str(e),
                    used_reference_wav=used_ref, is_reference_created=False, original_lufs=None,
                    target_lufs=(float(self.config.target_lufs) if self.config.enable_loudness_normalization else None),
                    final_lufs=None, duration_seconds=0.0, created_at=datetime.now().isoformat()
                ))

            done += 1
            self.progress.emit(done, total)
            if float(self.config.batch_pause_seconds) > 0:
                time.sleep(float(self.config.batch_pause_seconds))

        report_path = self._write_report(results)
        summary = {
            "total": total,
            "done": sum(1 for r in results if r.status.startswith("Done")),
            "skipped": sum(1 for r in results if r.status == "Skipped"),
            "failed": sum(1 for r in results if r.status == "Failed"),
            "report_path": str(report_path),
        }
        self.finished.emit(summary)

    def _write_report(self, results: List[BatchRowResult]) -> Path:
        out = Path(self.config.output_dir)
        out.mkdir(parents=True, exist_ok=True)
        rp = out / f"generation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        fields = [
            "row_index", "VoiceID", "台本ID", "区域", "细分区域", "TOTTS", "output_path", "status",
            "error_message", "used_reference_wav", "is_reference_created", "original_lufs", "target_lufs",
            "final_lufs", "duration_seconds", "created_at",
        ]
        with rp.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for r in results:
                writer.writerow(r.__dict__)
        return rp
