"""
dots.tts (rednote-hilab) 本地推理封装
支持 dots.tts-base / dots.tts-soar / dots.tts-mf 三个变体。
接口兼容 VoxCPMManager / IndexTTSManager 的 generate() 签名。

【子进程方式】
主 venv（transformers 4.52.1）与 dots.tts 专用 venv（.venv_dots，transformers 5.x）存在依赖冲突，
因此 dots.tts 的推理通过子进程调用 .venv_dots 中的 dots_tts_worker.py 来完成。
"""

import json
import struct
import subprocess
import sys
from pathlib import Path
from typing import Optional

import numpy as np

BASE_DIR = Path(__file__).resolve().parents[2]
WORKER_PATH = Path(__file__).with_name("dots_tts_worker.py")
DOTS_VENV_PYTHON = BASE_DIR / ".venv_dots" / "bin" / "python"

# ---------------------------------------------------------------------------
# 控制指令翻译字典
# ---------------------------------------------------------------------------
DOTS_CONTROL_INSTRUCTION_MAP: dict[str, str] = {
    "happy":        "请用开心愉快的语气说",
    "sad":          "请用悲伤难过的语气说",
    "angry":        "请用生气愤怒的语气说",
    "fearful":      "请用恐惧害怕的语气说",
    "surprised":    "请用惊讶惊喜的语气说",
    "disgusted":    "请用厌恶嫌弃的语气说",
    "calm":         "请用平静淡然的语气说",
    "excited":      "请用兴奋激动的语气说",
    "tender":       "请用温柔体贴的语气说",
    "serious":      "请用严肃认真的语气说",
    "confident":    "请用自信骄傲的语气说",
    "depressed":    "请用沮丧低落的语气说",
    "slow":         "请放慢语速说",
    "fast":         "请加快语速说",
    "very_slow":    "请用非常慢的语速说",
    "very_fast":    "请用非常快的语速说",
    "quiet":        "请用较小的音量说",
    "loud":         "请用较大的音量说",
    "whisper":      "请用轻声耳语的方式说",
    "storytelling": "请用讲故事的语气说",
}


def translate_control_instruction(raw: str) -> Optional[str]:
    key = raw.strip().lower()
    if not key:
        return None
    return DOTS_CONTROL_INSTRUCTION_MAP.get(key, raw.strip())


def _find_dots_python() -> str:
    """查找 dots.tts 专用 venv 的 Python 路径，不存在则返回当前解释器路径。"""
    # Windows 兼容路径
    win_path = BASE_DIR / ".venv_dots" / "Scripts" / "python.exe"
    if DOTS_VENV_PYTHON.exists():
        return str(DOTS_VENV_PYTHON)
    if win_path.exists():
        return str(win_path)
    return sys.executable


class DotsTTSManager:
    """
    dots.tts 子进程推理封装。
    以子进程方式启动 .venv_dots/bin/python + dots_tts_worker.py，
    通过 stdin 传入 JSON 请求，从 stdout 接收 float32 PCM 音频数据。
    """

    DEFAULT_MODEL_VARIANT = "dots.tts-soar"

    def __init__(
        self,
        logger,
        model_path: str = "",
        model_variant: str = "dots.tts-soar",
        num_steps: int = 10,
        guidance_scale: float = 1.2,
    ):
        self.logger = logger
        self.model_variant = model_variant
        self.num_steps = num_steps
        self.guidance_scale = guidance_scale
        self.device = "cpu"
        self._ready = False
        self._python_bin = _find_dots_python()

        if model_path and Path(model_path).exists():
            self._model_name_or_path = model_path
        else:
            local_dir = BASE_DIR / "models" / model_variant
            if local_dir.exists():
                self._model_name_or_path = str(local_dir)
            else:
                self._model_name_or_path = f"rednote-hilab/{model_variant}"

    def load_model(self, device: str = "auto", load_denoiser: bool = False) -> str:
        """
        子进程方式下，实际的模型加载在 generate() 调用时由子进程完成。
        此方法仅检查专用 venv 和 worker 脚本是否存在。
        """
        if not WORKER_PATH.exists():
            raise RuntimeError(f"未找到 dots_tts_worker.py：{WORKER_PATH}")

        dots_venv_ok = DOTS_VENV_PYTHON.exists() or (
            BASE_DIR / ".venv_dots" / "Scripts" / "python.exe"
        ).exists()
        if not dots_venv_ok:
            raise RuntimeError(
                f"未找到 .venv_dots，请执行以下命令创建 dots.tts 专用环境：\n"
                f"  python3.11 -m venv {BASE_DIR / '.venv_dots'}\n"
                f"  {BASE_DIR / '.venv_dots' / 'bin' / 'pip'} install "
                "'git+https://github.com/rednote-hilab/dots.tts.git' --no-deps\n"
                f"  {BASE_DIR / '.venv_dots' / 'bin' / 'pip'} install "
                "'transformers>=4.57.0' loguru 'langcodes[data]' "
                "lingua-language-detector torchdiffeq 'safetensors>=0.8.0' "
                "'librosa>=0.11.0' 'pydantic>=2.0' soundfile pynini WeTextProcessing"
            )

        # MPS 回退到 CPU
        if device == "auto" or device == "mps":
            self.device = "cpu"
        else:
            self.device = device

        self._ready = True
        self.logger.info(
            "dots.tts 子进程模式: python=%s model=%s device=%s",
            self._python_bin, self._model_name_or_path, self.device,
        )
        return self.device

    def generate(
        self,
        text: str,
        cfg_value: float = 2.0,
        inference_timesteps: int = 10,
        reference_wav_path: Optional[str] = None,
        random_seed: Optional[int] = None,
        prompt_text: str = "",
        control_instruction: str = "",
    ):
        if not self._ready:
            self.load_model()

        if not reference_wav_path:
            raise ValueError("dots.tts 需要参考音频 (reference_wav_path)")

        num_steps = inference_timesteps if inference_timesteps > 0 else self.num_steps

        final_text = str(text).strip()
        template_name: Optional[str] = None
        instruction_str = translate_control_instruction(control_instruction) if control_instruction else None
        if instruction_str:
            final_text = f"{instruction_str}：{final_text}"
            template_name = "instruction_tts"

        precision = "bfloat16" if self.device == "cuda" else "float32"

        request = {
            "model_path": self._model_name_or_path,
            "device": self.device,
            "precision": precision,
            "text": final_text,
            "prompt_audio_path": str(reference_wav_path),
            "num_steps": num_steps,
            "guidance_scale": self.guidance_scale,
            "random_seed": random_seed,
        }
        if prompt_text:
            request["prompt_text"] = str(prompt_text).strip()
        if template_name:
            request["template_name"] = template_name

        self.logger.info(
            "dots.tts 合成 (subprocess): len=%d, steps=%d, cfg=%.1f, template=%s, ref=%s",
            len(final_text), num_steps, self.guidance_scale,
            template_name or "tts", Path(reference_wav_path).name,
        )

        return self._run_worker(request)

    def _run_worker(self, request: dict):
        """启动子进程，发送请求并接收音频数据。"""
        request_json = json.dumps(request, ensure_ascii=False) + "\n"

        try:
            proc = subprocess.Popen(
                [self._python_bin, str(WORKER_PATH)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError as e:
            raise RuntimeError(
                f"未找到 dots.tts 专用 Python：{self._python_bin}\n"
                "请先创建 .venv_dots 后重试。"
            ) from e

        stdout_data, stderr_data = proc.communicate(
            input=request_json.encode("utf-8"),
            timeout=600,
        )

        # stderr 内容作为日志输出
        if stderr_data:
            for line in stderr_data.decode("utf-8", errors="replace").splitlines():
                self.logger.info("[dots-worker] %s", line)

        if proc.returncode != 0:
            raise RuntimeError(
                f"dots_tts_worker 异常退出 (code={proc.returncode}):\n"
                + stderr_data.decode("utf-8", errors="replace")[-2000:]
            )

        if len(stdout_data) < 8:
            raise RuntimeError(
                f"dots_tts_worker 输出数据过短 ({len(stdout_data)} bytes)"
            )

        sr = struct.unpack(">I", stdout_data[0:4])[0]
        wav_len = struct.unpack(">I", stdout_data[4:8])[0]
        wav_bytes = stdout_data[8: 8 + wav_len]

        if len(wav_bytes) != wav_len:
            raise RuntimeError(
                f"音频数据长度不匹配：expected={wav_len} got={len(wav_bytes)}"
            )

        wav = np.frombuffer(wav_bytes, dtype=np.float32).copy()
        return wav, sr
