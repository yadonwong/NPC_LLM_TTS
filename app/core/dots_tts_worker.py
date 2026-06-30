"""
dots.tts 子进程工作器
由 .venv_dots 中的 Python 解释器独立运行。

通信协议：
  stdin  <- 一行 JSON（请求）
  stdout <- 4字节 big-endian uint32（wav数据长度）+ wav数据（bytes）
  stderr <- 日志 / 错误信息

请求 JSON 字段：
  {
    "model_path": str,
    "device": str,           # "cpu" | "cuda"
    "precision": str,        # "float32" | "bfloat16"
    "text": str,
    "prompt_audio_path": str,
    "prompt_text": str,      # 可选
    "template_name": str,    # 可选："tts" | "instruction_tts"
    "num_steps": int,
    "guidance_scale": float,
    "random_seed": int | null
  }

返回格式：
  struct.pack(">I", sample_rate) +
  struct.pack(">I", wav_bytes_len) +
  wav_bytes  (float32 LE PCM)
"""

import json
import struct
import sys


def main() -> None:
    raw = sys.stdin.readline()
    if not raw:
        sys.stderr.write("ERROR: empty stdin\n")
        sys.exit(1)

    try:
        req = json.loads(raw)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"ERROR: invalid JSON: {e}\n")
        sys.exit(1)

    try:
        from dots_tts.runtime import DotsTtsRuntime
    except ImportError as e:
        sys.stderr.write(f"ERROR: cannot import dots_tts: {e}\n")
        sys.exit(1)

    import torch
    import numpy as np

    model_path: str = req["model_path"]
    device_str: str = req.get("device", "cpu")
    precision: str = req.get("precision", "float32")

    sys.stderr.write(f"INFO: loading model from {model_path} device={device_str} precision={precision}\n")
    sys.stderr.flush()

    runtime = DotsTtsRuntime.from_pretrained(
        model_path,
        precision=precision,
    )

    if req.get("random_seed") is not None:
        torch.manual_seed(int(req["random_seed"]))

    gen_kwargs: dict = {
        "text": req["text"],
        "prompt_audio_path": req["prompt_audio_path"],
        "num_steps": int(req.get("num_steps", 10)),
        "guidance_scale": float(req.get("guidance_scale", 1.2)),
    }
    if req.get("prompt_text"):
        gen_kwargs["prompt_text"] = req["prompt_text"]
    if req.get("template_name"):
        gen_kwargs["template_name"] = req["template_name"]

    sys.stderr.write(f"INFO: generating text_len={len(req['text'])} steps={gen_kwargs['num_steps']}\n")
    sys.stderr.flush()

    result = runtime.generate(**gen_kwargs)

    audio_tensor = result["audio"].float().cpu().squeeze()
    sr = int(result["sample_rate"])
    wav_np = audio_tensor.numpy().astype(np.float32)
    wav_bytes = wav_np.tobytes()

    sys.stderr.write(f"INFO: done sr={sr} samples={len(wav_np)}\n")
    sys.stderr.flush()

    # 输出格式：sample_rate(4B) + wav_len(4B) + wav_bytes
    out = sys.stdout.buffer
    out.write(struct.pack(">I", sr))
    out.write(struct.pack(">I", len(wav_bytes)))
    out.write(wav_bytes)
    out.flush()


if __name__ == "__main__":
    main()
