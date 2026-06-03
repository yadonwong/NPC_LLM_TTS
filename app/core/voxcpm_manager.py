import random
from pathlib import Path
from typing import Optional

import numpy as np


class VoxCPMManager:
    def __init__(self, model_path: str, logger):
        self.model_path = Path(model_path)
        self.logger = logger
        self.model = None
        self.device = "cpu"

    def resolve_device(self, device_str: str) -> str:
        if device_str != "auto":
            return device_str
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
        except Exception:
            self.logger.warning("torch 不可用，设备自动回退到 CPU")
        return "cpu"

    def load_model(self, device: str = "auto", load_denoiser: bool = False) -> str:
        if self.model is not None:
            return self.device
        self.device = self.resolve_device(device)
        self.logger.info("正在加载 VoxCPM2 模型: %s", self.model_path)
        from voxcpm import VoxCPM

        self.model = VoxCPM.from_pretrained(str(self.model_path), load_denoiser=load_denoiser)
        self.logger.info("模型加载完成，设备=%s", self.device)
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

        if random_seed is not None:
            random.seed(random_seed)
            np.random.seed(random_seed)
            try:
                import torch
                torch.manual_seed(random_seed)
                if torch.cuda.is_available():
                    torch.cuda.manual_seed_all(random_seed)
            except Exception:
                pass

        kwargs = {
            "text": text,
            "cfg_value": cfg_value,
            "inference_timesteps": inference_timesteps,
        }
        if reference_wav_path:
            kwargs["reference_wav_path"] = reference_wav_path

        wav = self.model.generate(**kwargs)
        sr = getattr(self.model, "sample_rate", 48000)
        try:
            import torch
            if isinstance(wav, torch.Tensor):
                wav = wav.detach().cpu().numpy()
        except Exception:
            pass
        return wav, int(sr)
