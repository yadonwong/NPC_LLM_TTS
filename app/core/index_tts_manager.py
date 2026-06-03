from pathlib import Path
from typing import Optional
import sys
import os

import librosa
import numpy as np
import soundfile as sf

BASE_DIR = Path(__file__).resolve().parents[2]


class IndexTTSManager:
    def __init__(self, model_path: str, logger):
        self.model_path = Path(model_path)
        self.logger = logger
        self.model = None
        self.device = "cpu"

    def _local_maskgct_candidates(self) -> list[Path]:
        return [
            BASE_DIR / "models" / "MaskGCT" / "semantic_codec" / "model.safetensors",
            Path.home() / ".cache" / "modelscope" / "hub" / "models" / "amphion" / "MaskGCT" / "semantic_codec" / "model.safetensors",
        ]

    def _resolve_local_maskgct_semantic_codec(self) -> Optional[Path]:
        for p in self._local_maskgct_candidates():
            if p.exists() and p.is_file() and p.stat().st_size > 50 * 1024 * 1024:
                return p
        return None

    def _local_bigvgan_candidates(self) -> list[Path]:
        return [
            BASE_DIR / "models" / "bigvgan_v2_22khz_80band_256x",
            BASE_DIR / "models" / "BigVGAN" / "bigvgan_v2_22khz_80band_256x",
        ]

    def _resolve_local_bigvgan_dir(self) -> Optional[Path]:
        for d in self._local_bigvgan_candidates():
            if not (d.exists() and d.is_dir()):
                continue
            cfg = d / "config.json"
            pt = d / "bigvgan_generator.pt"
            sf = d / "model.safetensors"
            if cfg.exists() and ((pt.exists() and pt.stat().st_size > 100 * 1024 * 1024) or (sf.exists() and sf.stat().st_size > 500 * 1024 * 1024)):
                return d
        return None

    def _invalid_local_bigvgan_file(self) -> Optional[Path]:
        for d in self._local_bigvgan_candidates():
            sf = d / "model.safetensors"
            pt = d / "bigvgan_generator.pt"
            if sf.exists() and sf.stat().st_size <= 1024 * 1024:
                return sf
            if pt.exists() and pt.stat().st_size <= 1024 * 1024:
                return pt
        return None

    def check_offline_dependencies(self) -> list[str]:
        missing = []

        try:
            from huggingface_hub import hf_hub_download
        except Exception:
            missing.append("Python 包缺失: huggingface_hub")
            return missing

        local_codec = self._resolve_local_maskgct_semantic_codec()
        if local_codec is None:
            try:
                hf_hub_download(
                    repo_id="amphion/MaskGCT",
                    filename="semantic_codec/model.safetensors",
                    local_files_only=True,
                )
            except Exception:
                missing.append("缺少缓存文件: amphion/MaskGCT -> semantic_codec/model.safetensors")
        else:
            self.logger.info("发现本地 MaskGCT semantic codec: %s", local_codec)

        # BigVGAN vocoder weights used by IndexTTS2
        local_bigvgan = self._resolve_local_bigvgan_dir()
        if local_bigvgan is None:
            bad_file = self._invalid_local_bigvgan_file()
            if bad_file is not None:
                missing.append(f"本地 BigVGAN 文件无效(体积异常): {bad_file}")
            else:
                missing.append("缺少本地 BigVGAN 权重目录（需包含 config.json + bigvgan_generator.pt，或 model.safetensors）")
        else:
            self.logger.info("发现本地 BigVGAN: %s", local_bigvgan)

        return missing

    def resolve_device(self, device_str: str) -> str:
        if device_str != "auto":
            return device_str
        try:
            import torch

            if torch.cuda.is_available():
                return "cuda:0"
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
        except Exception:
            self.logger.warning("torch 不可用，设备自动回退到 CPU")
        return "cpu"

    def load_model(self, device: str = "auto", load_denoiser: bool = False) -> str:
        if self.model is not None:
            return self.device
        self.device = self.resolve_device(device)

        # Prefer full downloaded model dir in /models first
        full_model_dir = BASE_DIR / "models" / "IndexTTS-2"
        selected_model_path = self.model_path
        if (not (selected_model_path / "qwen0.6bemo4-merge").exists()) and (full_model_dir / "qwen0.6bemo4-merge").exists():
            selected_model_path = full_model_dir
            self.logger.info("IndexTTS 模型目录自动切换为: %s", selected_model_path)

        self.model_path = selected_model_path
        self.logger.info("正在加载 IndexTTS 模型: %s", self.model_path)

        # Force local repo first to avoid importing stale global indextts package
        repo_root = BASE_DIR / "third_party" / "index-tts"
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))

        cfg_path = self.model_path / "config.yaml"

        local_codec = self._resolve_local_maskgct_semantic_codec()
        if local_codec is not None:
            os.environ["MASKGCT_SEMANTIC_CODEC_PATH"] = str(local_codec)
            self.logger.info("使用本地 MaskGCT semantic codec: %s", local_codec)

        local_bigvgan = self._resolve_local_bigvgan_dir()
        if local_bigvgan is not None:
            os.environ["BIGVGAN_LOCAL_DIR"] = str(local_bigvgan)
            self.logger.info("使用本地 BigVGAN: %s", local_bigvgan)

        try:
            from indextts.infer_v2 import IndexTTS2
            self.logger.info("IndexTTS import path(infer_v2): %s", Path(sys.modules['indextts'].__file__).resolve())

            self.model = IndexTTS2(
                cfg_path=str(cfg_path),
                model_dir=str(self.model_path),
                device=self.device,
                use_fp16=(self.device != "cpu"),
                use_cuda_kernel=False,
                use_deepspeed=False,
            )
            self.logger.info("IndexTTS2 模型加载完成，设备=%s", self.device)
            return self.device
        except ImportError as e:
            self.logger.warning("无法导入 infer_v2，尝试 legacy infer: %s", e)

        # legacy fallback (only when infer_v2 import is unavailable)
        from indextts.infer import IndexTTS
        self.logger.info("IndexTTS import path(infer): %s", Path(sys.modules['indextts'].__file__).resolve())

        self.model = IndexTTS(cfg_path=str(cfg_path), model_dir=str(self.model_path), device=self.device, use_fp16=True)
        self.logger.info("IndexTTS(legacy) 模型加载完成，设备=%s", self.device)
        return self.device

    def generate(
        self,
        text: str,
        cfg_value: float = 2.0,
        inference_timesteps: int = 10,
        reference_wav_path: Optional[str] = None,
        random_seed: Optional[int] = None,
    ):
        if self.model is None:
            raise RuntimeError("Model not loaded")
        if not reference_wav_path:
            raise ValueError("IndexTTS 需要参考音频(reference_wav_path)")

        tmp_path = self.model_path / "_tmp_infer.wav"
        if hasattr(self.model, "infer"):
            # IndexTTS2 signature
            try:
                self.model.infer(
                    spk_audio_prompt=str(reference_wav_path),
                    text=str(text),
                    output_path=str(tmp_path),
                    verbose=False,
                    max_text_tokens_per_segment=80,
                    num_beams=1,
                    max_mel_tokens=600,
                    top_p=0.9,
                    top_k=20,
                    temperature=0.7,
                )
            except TypeError:
                # legacy IndexTTS signature
                self.model.infer(
                    audio_prompt=str(reference_wav_path),
                    text=str(text),
                    output_path=str(tmp_path),
                    verbose=False,
                    max_text_tokens_per_segment=80,
                )

        wav, sr = sf.read(str(tmp_path), dtype="float32")
        if wav.ndim > 1:
            wav = np.mean(wav, axis=1)
        if int(sr) != 48000:
            wav = librosa.resample(wav.astype(np.float32), orig_sr=int(sr), target_sr=48000)
            sr = 48000
        return wav, int(sr)
