"""
Volcengine Seed TTS 2.0  —  WebSocket 单向流式接口封装
协议参考: https://www.volcengine.com/docs/6561/1719100
"""

import gzip
import inspect
import io
import json
import struct
import uuid
from pathlib import Path
from typing import Optional

import numpy as np

# ---------------------------------------------------------------------------
# 协议常量
# ---------------------------------------------------------------------------
_PROTOCOL_VERSION = 0x1
_HEADER_SIZE_UNIT = 0x1          # 表示 4 字节 header
_MSG_TYPE_FULL_CLIENT = 0b0001
_MSG_TYPE_FULL_SERVER = 0b1001
_MSG_TYPE_AUDIO_ONLY  = 0b1011
_MSG_TYPE_ERROR       = 0b1111
_MSG_FLAG_NONE          = 0b0000
_MSG_FLAG_FINISH_CONN   = 0b0100  # FinishConnection
_SERIAL_JSON = 0b0001
_SERIAL_RAW  = 0b0000
_COMPRESS_NONE = 0b0000
_COMPRESS_GZIP = 0b0001

EVENT_SESSION_FINISHED   = 152
EVENT_TTS_SENTENCE_START = 350
EVENT_TTS_SENTENCE_END   = 351
EVENT_TTS_RESPONSE       = 352
EVENT_FINISH_CONNECTION  = 2
EVENT_CONNECTION_FINISHED = 52

WSS_URL = "wss://openspeech.bytedance.com/api/v3/tts/unidirectional/stream"


# ---------------------------------------------------------------------------
# 控制指令翻译字典
# ---------------------------------------------------------------------------
CONTROL_INSTRUCTION_MAP: dict[str, str] = {
    "happy":        "你可以用开心愉快的语气说话吗？",
    "sad":          "你可以用悲伤难过的语气说话吗？",
    "angry":        "你可以用生气愤怒的语气说话吗？",
    "fearful":      "你可以用恐惧害怕的语气说话吗？",
    "surprised":    "你可以用惊讶惊喜的语气说话吗？",
    "disgusted":    "你可以用厌恶嫌弃的语气说话吗？",
    "calm":         "你可以用平静淡然的语气说话吗？",
    "excited":      "你可以用兴奋激动的语气说话吗？",
    "tender":       "你可以用温柔体贴的语气说话吗？",
    "serious":      "你可以用严肃认真的语气说话吗？",
    "confident":    "你可以用自信骄傲的语气说话吗？",
    "depressed":    "你可以用沮丧低落的语气说话吗？",
    "slow":         "你可以说慢一点吗？",
    "fast":         "你可以说快一点吗？",
    "very_slow":    "你可以说非常慢吗？",
    "very_fast":    "你可以说非常快吗？",
    "quiet":        "你嗓门再小点。",
    "loud":         "你嗓门大一点。",
    "whisper":      "你可以用耳语般轻声说话吗？",
    "storytelling": "你可以用讲故事的语气说话吗？",
}


def translate_control_instruction(raw: str) -> Optional[str]:
    key = raw.strip().lower()
    if not key:
        return None
    return CONTROL_INSTRUCTION_MAP.get(key, raw.strip())


# ---------------------------------------------------------------------------
# 二进制帧构造 / 解析
# ---------------------------------------------------------------------------

def _build_header(msg_type: int, msg_flags: int, serial: int, compress: int) -> bytes:
    b0 = (_PROTOCOL_VERSION << 4) | _HEADER_SIZE_UNIT
    b1 = (msg_type << 4) | msg_flags
    b2 = (serial << 4) | compress
    return bytes([b0, b1, b2, 0x00])


def _compress_payload(data: bytes, compress: int) -> bytes:
    if compress == _COMPRESS_GZIP:
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb") as f:
            f.write(data)
        return buf.getvalue()
    return data


def build_send_text_frame(payload_dict: dict, use_gzip: bool = False) -> bytes:
    compress = _COMPRESS_GZIP if use_gzip else _COMPRESS_NONE
    raw = json.dumps(payload_dict, ensure_ascii=False).encode("utf-8")
    payload = _compress_payload(raw, compress)
    header = _build_header(_MSG_TYPE_FULL_CLIENT, _MSG_FLAG_NONE, _SERIAL_JSON, compress)
    return header + struct.pack(">I", len(payload)) + payload


def build_finish_connection_frame() -> bytes:
    """FinishConnection 帧：header(4B) + event(4B) + payload_size(4B) + payload"""
    raw = json.dumps({}).encode("utf-8")
    header = _build_header(_MSG_TYPE_FULL_CLIENT, _MSG_FLAG_FINISH_CONN, _SERIAL_JSON, _COMPRESS_NONE)
    event = struct.pack(">I", EVENT_FINISH_CONNECTION)
    size = struct.pack(">I", len(raw))
    return header + event + size + raw

def _parse_response_frame(data: bytes) -> dict:
    if len(data) < 4:
        return {"type": "unknown", "raw": data}

    b1 = data[1]
    b2 = data[2]
    msg_type = (b1 >> 4) & 0xF
    msg_flags = b1 & 0xF
    compress  = b2 & 0xF
    pos = 4

    # Error 帧：header(4B) + error_code(4B) + payload_len(4B) + payload
    if msg_type == _MSG_TYPE_ERROR:
        if len(data) < pos + 8:
            return {"type": "incomplete"}
        error_code = struct.unpack(">I", data[pos: pos + 4])[0]
        pos += 4
        payload_len = struct.unpack(">I", data[pos: pos + 4])[0]
        pos += 4
        payload_bytes = data[pos: pos + payload_len]
        if compress == _COMPRESS_GZIP:
            try:
                payload_bytes = gzip.decompress(payload_bytes)
            except Exception:
                pass
        try:
            msg = json.loads(payload_bytes)
        except Exception:
            msg = payload_bytes.decode("utf-8", errors="replace")
        return {"type": "error", "error_code": error_code, "message": msg}

    # 非 error 帧：event(4B，flags bit-2) + session_id(len+data) + payload_len(4B) + payload
    event = None
    session_id = None
    if msg_flags & 0x4:
        if len(data) < pos + 4:
            return {"type": "incomplete"}
        event = struct.unpack(">I", data[pos: pos + 4])[0]
        pos += 4
        if msg_type in (_MSG_TYPE_FULL_SERVER, _MSG_TYPE_AUDIO_ONLY):
            if len(data) < pos + 4:
                return {"type": "incomplete", "event": event}
            session_id_len = struct.unpack(">I", data[pos: pos + 4])[0]
            pos += 4
            if len(data) < pos + session_id_len:
                return {"type": "incomplete", "event": event}
            session_id = data[pos: pos + session_id_len].decode("utf-8", errors="replace")
            pos += session_id_len

    if len(data) < pos + 4:
        return {"type": "meta", "event": event, "session_id": session_id}

    payload_len = struct.unpack(">I", data[pos: pos + 4])[0]
    pos += 4
    if len(data) < pos + payload_len:
        return {"type": "incomplete", "event": event, "session_id": session_id}
    payload_bytes = data[pos: pos + payload_len]

    if compress == _COMPRESS_GZIP:
        try:
            payload_bytes = gzip.decompress(payload_bytes)
        except Exception:
            pass

    if msg_type == _MSG_TYPE_AUDIO_ONLY:
        return {"type": "audio", "event": event, "session_id": session_id, "audio": payload_bytes}

    try:
        body = json.loads(payload_bytes)
    except Exception:
        body = {}
    return {"type": "json", "event": event, "session_id": session_id, "body": body}


# ---------------------------------------------------------------------------
# SeedTTSManager
# ---------------------------------------------------------------------------

class SeedTTSManager:
    """
    Volcengine Seed TTS 2.0 接入管理器。
    兼容 VoxCPMManager / IndexTTSManager 的 generate() 接口。
    """

    RESOURCE_SEED_TTS_2 = "seed-tts-2.0"
    RESOURCE_SEED_ICL_2 = "seed-icl-2.0"

    def __init__(
        self,
        logger,
        api_key: str = "",
        app_id: str = "",
        access_key: str = "",
        resource_id: str = "seed-tts-2.0",
        default_speaker: str = "zh_female_shuangkuaisisi_uranus_bigtts",
        sample_rate: int = 48000,
    ):
        self.logger = logger
        self.api_key = api_key
        self.app_id = app_id
        self.access_key = access_key
        self.resource_id = resource_id
        self.default_speaker = default_speaker
        self.sample_rate = sample_rate
        self.device = "cloud"
        self._ready = False

    def load_model(self, device: str = "auto", load_denoiser: bool = False) -> str:
        has_new_auth = bool(self.api_key.strip())
        has_old_auth = bool(self.app_id.strip()) and bool(self.access_key.strip())
        if not has_new_auth and not has_old_auth:
            raise RuntimeError(
                "Seed TTS 2.0 需要 API Key 或 (App ID + Access Key)。\n"
                "请在设置面板中填写凭据后重试。"
            )
        self._ready = True
        self.logger.info(
            "Seed TTS 2.0 凭据已就绪，resource_id=%s，鉴权方式=%s",
            self.resource_id,
            "新版(api_key)" if has_new_auth else "旧版(app_id+access_key)",
        )
        return "cloud"

    def _build_headers(self) -> dict:
        headers: dict[str, str] = {}
        if self.api_key.strip():
            headers["X-Api-Key"] = self.api_key.strip()
        else:
            headers["X-Api-App-Id"] = self.app_id.strip()
            headers["X-Api-Access-Key"] = self.access_key.strip()
        headers["X-Api-Resource-Id"] = self.resource_id
        headers["X-Api-Request-Id"] = str(uuid.uuid4())
        return headers

    def _build_payload(
        self,
        text: str,
        speaker: str,
        reference_wav_path: Optional[str],
        context_text: Optional[str],
        speech_rate: int = 0,
    ) -> dict:
        payload: dict = {
            "user": {"uid": "npc_llm_tts"},
            "req_params": {
                "text": text,
                "speaker": speaker,
                "audio_params": {
                    "format": "pcm",
                    "sample_rate": self.sample_rate,
                },
            },
        }
        additions: dict = {}
        if context_text:
            additions["context_texts"] = [context_text]
        if speech_rate != 0:
            payload["req_params"]["audio_params"]["speech_rate"] = speech_rate
        if self.resource_id == self.RESOURCE_SEED_ICL_2 and reference_wav_path:
            import base64
            ref_bytes = Path(reference_wav_path).read_bytes()
            additions["prompt_audio"] = base64.b64encode(ref_bytes).decode("ascii")
            additions["prompt_audio_format"] = "wav"
        if additions:
            payload["req_params"]["additions"] = json.dumps(additions, ensure_ascii=False)
        return payload

    def generate(
        self,
        text: str,
        cfg_value: float = 2.0,
        inference_timesteps: int = 10,
        reference_wav_path: Optional[str] = None,
        random_seed: Optional[int] = None,
        speaker: Optional[str] = None,
        control_instruction: str = "",
        speech_rate: int = 0,
    ):
        if not self._ready:
            self.load_model()

        effective_speaker = speaker or self.default_speaker
        context_text = translate_control_instruction(control_instruction) if control_instruction else None
        payload = self._build_payload(
            text=text,
            speaker=effective_speaker,
            reference_wav_path=reference_wav_path,
            context_text=context_text,
            speech_rate=speech_rate,
        )
        headers = self._build_headers()
        request_id = headers.get("X-Api-Request-Id", "")
        self.logger.info(
            "Seed TTS 2.0 合成: speaker=%s, resource=%s, len=%d, request_id=%s",
            effective_speaker, self.resource_id, len(text), request_id,
        )
        audio_bytes = self._ws_synthesize(payload, headers, request_id=request_id)
        wav = self._pcm_to_float32(audio_bytes, self.sample_rate)
        return wav, self.sample_rate

    def _ws_synthesize(self, payload: dict, headers: dict, request_id: str = "") -> bytes:
        import asyncio
        return asyncio.run(self._async_ws_synthesize(payload, headers, request_id=request_id))

    async def _async_ws_synthesize(self, payload: dict, headers: dict, request_id: str = "") -> bytes:
        try:
            import websockets
        except ImportError as e:
            raise RuntimeError("缺少 websockets 依赖，请运行: pip install websockets") from e

        audio_chunks: list[bytes] = []
        send_frame = build_send_text_frame(payload)
        finish_frame = build_finish_connection_frame()

        # 兼容不同版本 websockets 的参数名
        header_arg = (
            "additional_headers"
            if "additional_headers" in inspect.signature(websockets.connect).parameters
            else "extra_headers"
        )

        try:
            async with websockets.connect(WSS_URL, **{header_arg: headers}) as ws:
                await ws.send(send_frame)

                async for raw in ws:
                    if isinstance(raw, str):
                        continue
                    frame = _parse_response_frame(raw)
                    ftype = frame.get("type")

                    if ftype == "audio":
                        audio_chunks.append(frame["audio"])

                    elif ftype == "error":
                        code = frame.get("error_code")
                        msg = frame.get("message", "")
                        raise RuntimeError(
                            f"Seed TTS API 错误 [{code}]: {msg}  (request_id={request_id})"
                        )

                    elif ftype == "json":
                        event = frame.get("event")
                        if event == EVENT_SESSION_FINISHED:
                            body = frame.get("body", {})
                            status = body.get("status_code", body.get("code", 0))
                            if status != 20000000 and status != 0:
                                raise RuntimeError(
                                    f"Seed TTS 会话结束，状态码={status}，"
                                    f"消息={body.get('message', '')}  (request_id={request_id})"
                                )
                            await ws.send(finish_frame)
                        elif event == EVENT_CONNECTION_FINISHED:
                            break

        except Exception as e:
            if f"request_id={request_id}" in str(e):
                raise
            raise RuntimeError(f"{e}  (request_id={request_id})") from e

        if not audio_chunks:
            raise RuntimeError(
                f"Seed TTS 2.0 未返回任何音频数据，请检查 speaker/凭据是否正确  (request_id={request_id})"
            )
        return b"".join(audio_chunks)

    @staticmethod
    def _pcm_to_float32(pcm_bytes: bytes, sample_rate: int) -> np.ndarray:
        arr = np.frombuffer(pcm_bytes, dtype=np.int16)
        return arr.astype(np.float32) / 32768.0
