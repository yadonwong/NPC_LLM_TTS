"""
dots.tts (rednote-hilab) 本地推理封装
支持 dots.tts-base / dots.tts-soar / dots.tts-mf 三个变体。
接口兼容 VoxCPMManager / IndexTTSManager 的 generate() 签名。
"""

from pathlib import Path
from typing import Optional

import numpy as np

BASE_DIR = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# 控制指令翻译字典
# dots.tts 使用 instruction_tts 模板，将指令作为自然语言前缀嵌入文本。
# 格式：模型接收 "[带指令文本]{instruction}，{text}[文本对应语音]{audio}"
# ---------------------------------------------------------------------------
DOTS_CONTROL_INSTRUCTION_MAP: dict[str, str] = {
    # 情感类
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
    # 语速类
    "slow":         "请放慢语速说",
    "fast":         "请加快语速说",
    "very_slow":    "请用非常慢的语速说",
    "very_fast":    "请用非常快的语速说",
    # 音量类
    "quiet":        "请用较小的音量说",
    "loud":         "请用较大的音量说",
    # 其他
    "whisper":      "请用轻声耳语的方式说",
    "storytelling": "请用讲故事的语气说",
}


def translate_control_instruction(raw: str) -> Optional[str]:
    """
    将 (xxx) 括号指令转换为 dots.tts instruction_tts 模板的前缀字符串。
    先精确匹配字典（忽略大小写），匹配不到则透传原始字符串。
    返回 None 表示没有指令。
    """
    key = raw.strip().lower()
    if not key:
        return None
    return DOTS_CONTROL_INSTRUCTION_MAP.get(key, raw.strip())


class DotsTTSManager:
    """
    本地 dots.tts 推理封装。

    需要参考音频 + 参考文本来克隆音色（零样本 continuation cloning）。
    参考文本可留空，此时模型会做纯音色克隆（音质略降，官方建议提供）。
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
        self._runtime = None
        self._ready = False

        # model_path 优先使用用户指定路径，否则用 models/<variant>
        if model_path and Path(model_path).exists():
            self._model_name_or_path = model_path
        else:
            local_dir = BASE_DIR / "models" / model_variant
            if local_dir.exists():
                self._model_name_or_path = str(local_dir)
            else:
                # 自动从 HuggingFace 下载
                self._model_name_or_path = f"rednote-hilab/{model_variant}"

    def load_model(self, device: str = "auto", load_denoiser: bool = False) -> str:
        try:
            from dots_tts.runtime import DotsTtsRuntime
        except ImportError as e:
            raise RuntimeError(
                "缺少 dots_tts 依赖，请运行:\n"
                "  pip install 'git+https://github.com/rednote-hilab/dots.tts.git' "
                "-c 'https://raw.githubusercontent.com/rednote-hilab/dots.tts/main/constraints/recommended.txt'"
            ) from e

        import torch

        if device == "auto":
            if torch.cuda.is_available():
                self.device = "cuda"
            else:
                # MPS は speaker_embedding dtype 不一致 / 未対応演算が出るため CPU を使う
                self.device = "cpu"
        else:
            # 明示指定でも MPS は CPU に落とす
            self.device = "cpu" if device == "mps" else device

        precision = "bfloat16" if self.device == "cuda" else "float32"

        self.logger.info(
            "加载 dots.tts 模型: %s，设备=%s，精度=%s",
            self._model_name_or_path,
            self.device,
            precision,
        )
        self._runtime = DotsTtsRuntime.from_pretrained(
            self._model_name_or_path,
            precision=precision,
        )
        self._ready = True
        self.logger.info("dots.tts 模型加载完成，设备=%s", self.device)
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
        """
        兼容现有 generate() 调用签名，返回 (numpy_float32_array, sample_rate)。

        reference_wav_path:  参考音频路径（必须，用于音色克隆）
        prompt_text:         参考音频的文字内容（推荐填写，可提升相似度）
        control_instruction: 控制指令 key（如 happy/sad/slow），
                             通过 DOTS_CONTROL_INSTRUCTION_MAP 翻译后作为
                             instruction_tts 模板的自然语言前缀注入到 text 中。
        """
        if not self._ready:
            self.load_model()

        if not reference_wav_path:
            raise ValueError("dots.tts 需要参考音频 (reference_wav_path)")

        import torch

        num_steps = inference_timesteps if inference_timesteps > 0 else self.num_steps

        # 控制指令处理：翻译后前缀到 text，并切换到 instruction_tts 模板
        final_text = str(text).strip()
        template_name: Optional[str] = None
        instruction_str = translate_control_instruction(control_instruction) if control_instruction else None
        if instruction_str:
            final_text = f"{instruction_str}：{final_text}"
            template_name = "instruction_tts"

        gen_kwargs: dict = dict(
            text=final_text,
            prompt_audio_path=str(reference_wav_path),
            num_steps=num_steps,
            guidance_scale=self.guidance_scale,
        )
        if prompt_text:
            gen_kwargs["prompt_text"] = str(prompt_text).strip()
        if template_name:
            gen_kwargs["template_name"] = template_name

        if random_seed is not None:
            torch.manual_seed(random_seed)

        self.logger.info(
            "dots.tts 合成: len=%d, steps=%d, cfg=%.1f, template=%s, ref=%s",
            len(final_text),
            num_steps,
            self.guidance_scale,
            template_name or "tts",
            Path(reference_wav_path).name,
        )

        result = self._runtime.generate(**gen_kwargs)

        audio_tensor = result["audio"].float().cpu().squeeze()
        sr = int(result["sample_rate"])
        wav = audio_tensor.numpy().astype(np.float32)
        return wav, sr
