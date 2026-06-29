# NPC LLM TTS 使用文档

`NPC LLM TTS` 是一个批量 NPC 台词 TTS 桌面应用，支持 Excel 批处理、VoiceID 音色一致性缓存、中英双语导出、响度归一化与任务日志追踪。

版权：`© Yadon Wong, 2026`

---

## 1. 功能概览

- 批量读取 Excel 并生成语音（CN/EN）
- 支持单句生成，无需 Excel 也可快速测试台词，生成后自动弹出音频预览窗口
- 支持四种 TTS 引擎：`VoxCPM2` / `IndexTTS-2` / `Seed TTS 2.0（火山引擎云端）` / `dots.tts（小红书）`
- 同 `VoiceID` 复用参考音色，保持一致音色
- 支持手动导入参考音频（`ref/`）
- 参考音色列表支持右键删除、整行选择与 Shift 多选
- 任务完成后可选择是否立即清除 VoiceID 参考音色缓存
- 输出固定规格：`48kHz / 24-bit PCM / Mono / WAV`
- 可选响度归一化（LUFS）
- 支持 `Start / Pause / Resume / Stop`
- 每次运行生成日志与 CSV 报告

---

## 2. 运行环境要求

- Python: `>=3.10, <3.13`（推荐 3.11）
- macOS / Windows
- 网络可访问 HuggingFace（失败时自动尝试 ModelScope）
- macOS 使用 dots.tts 引擎时需要 Homebrew 安装 `openfst`：`brew install openfst`

> 注意：Python 3.13 目前不兼容本项目依赖组合。

---

## 3. 快速启动

### macOS

双击：

- `start_mac.command`

脚本会自动查找 `python3.12 / python3.11 / python3.10` 并启动。

### Windows

双击：

- `start_windows.bat`

### 命令行方式

```bash
python bootstrap.py
python run_dev.py
```

`bootstrap.py` 会自动：

1. 创建 `.venv`
2. 安装依赖
3. 克隆并安装 `third_party/VoxCPM`
4. 克隆并安装 `third_party/index-tts`
5. 安装 `dots.tts` 包（从 GitHub，macOS 需要 Homebrew `openfst`）

---

## 4. TTS 引擎说明

本项目支持四种引擎，在左侧「生成设置」的「TTS引擎」下拉里切换。

| 引擎 key | 名称 | 类型 | 需要参考音频 | 凭据 |
|---|---|---|---|---|
| `voxcpm` | VoxCPM2 | 本地 | 可选（自动缓存首帧） | 无 |
| `indextts` | IndexTTS-2 | 本地 | **必须** | 无 |
| `seed-tts` | Seed TTS 2.0 | 云端 API | 可选 | 火山引擎 API Key |
| `dots-tts` | dots.tts | 本地 | **必须** | 无 |

### VoxCPM2

无需参考音频即可生成，第一次生成会自动将输出保存为该 VoiceID 的参考音色供后续复用。

### IndexTTS-2 / dots.tts

纯零样本音色克隆模型，**必须提供参考音频**才能推理。批处理时请先通过「参考音色管理」页为每个 VoiceID 导入参考音频，或在 Excel 中增加 `REFERENCE_WAV_PATH` 列。

### Seed TTS 2.0（火山引擎）

云端 API，需要在左侧「Seed TTS 2.0 设置」面板填写凭据：

- **API Key Secret**（新版控制台推荐）
- 或旧版 **API Key ID** + **Access Key ID**

音色由 `默认音色 ID` 字段控制（默认 `zh_female_shuangkuaisisi_moon_bigtts`），完整音色列表见[豆包音色文档](https://www.volcengine.com/docs/6561/1257544)。

### dots.tts（小红书）

提供三个变体，在「dots.tts 设置」面板的「模型变体」里选择：

| 变体 | 特点 |
|---|---|
| `dots.tts-soar` | 音色相似度最高，推荐默认 |
| `dots.tts-base` | 基础预训练版 |
| `dots.tts-mf` | MeanFlow 蒸馏版，NFE=4，速度最快 |

---

## 5. 模型下载与存放位置

`models/` 目录不随 GitHub 仓库上传，按需下载后放到以下固定位置。

### VoxCPM2

- HuggingFace: [openbmb/VoxCPM2](https://huggingface.co/openbmb/VoxCPM2)
- ModelScope: [OpenBMB/VoxCPM2](https://modelscope.cn/models/OpenBMB/VoxCPM2)

```text
models/
└── VoxCPM2/
    ├── model.safetensors
    ├── audiovae.pth
    └── ...
```

### IndexTTS-2

- HuggingFace: [IndexTeam/IndexTTS-2](https://huggingface.co/IndexTeam/IndexTTS-2)
- ModelScope: [IndexTeam/IndexTTS-2](https://modelscope.cn/models/IndexTeam/IndexTTS-2)

```text
models/
└── IndexTTS-2/
    ├── config.yaml
    ├── gpt.pth
    ├── s2mel.pth
    └── qwen0.6bemo4-merge/
        └── model.safetensors
```

IndexTTS-2 还需要两个依赖模型：

**MaskGCT semantic codec**
- HuggingFace: [amphion/MaskGCT](https://huggingface.co/amphion/MaskGCT)

```text
models/
└── MaskGCT/
    └── semantic_codec/
        └── model.safetensors
```

**BigVGAN vocoder**
- HuggingFace: [nvidia/bigvgan_v2_22khz_80band_256x](https://huggingface.co/nvidia/bigvgan_v2_22khz_80band_256x)

```text
models/
└── bigvgan_v2_22khz_80band_256x/
    ├── config.json
    ├── bigvgan_generator.pt
    └── ...
```

### dots.tts

- HuggingFace: [rednote-hilab/dots.tts-soar](https://huggingface.co/rednote-hilab/dots.tts-soar)
- ModelScope: [rednote-hilab/dots.tts-soar](https://modelscope.cn/models/rednote-hilab/dots.tts-soar)

命令行下载（推荐）：

```bash
# HuggingFace
huggingface-cli download rednote-hilab/dots.tts-soar --local-dir models/dots.tts-soar

# ModelScope（国内网络推荐）
.venv/bin/modelscope download --model rednote-hilab/dots.tts-soar --local_dir models/dots.tts-soar
```

```text
models/
└── dots.tts-soar/      ← 文件夹名须与变体名一致
    ├── config.json
    ├── model.safetensors
    ├── tokenizer.json
    └── ...
```

UI 里「模型路径」留空，程序自动检测 `models/<变体名>/`；若首次运行且目录不存在，会从 HuggingFace 自动下载（约 4GB）。

> `models/` 已加入 `.gitignore`，不会上传到 GitHub。

---

## 6. Excel 格式要求

### 最小必需列

- `VoiceID`
- `区域`
- `台本ID`
- `TOTTS_CN`（兼容旧列 `TOTTS`）

### 可选列

| 列名 | 说明 |
|---|---|
| `TOTTS_EN` | 英文台词，无则跳过 EN 导出 |
| `细分区域` | 额外目录层级，无则省略 |
| `Control Instruction` | 控制指令（见下方说明），也支持 `控制指令` 等别名 |
| `REFERENCE_WAV_PATH` | 指定本行使用的参考音频绝对路径 |

---

## 7. 控制指令（Control Instruction）

在 Excel 的 `Control Instruction` 列，或 TOTTS 文本开头用 `(指令)` 括号格式传入。

支持的指令 key（不区分大小写）：

| Key | 含义 |
|---|---|
| `happy` | 开心愉快 |
| `sad` | 悲伤难过 |
| `angry` | 生气愤怒 |
| `fearful` | 恐惧害怕 |
| `surprised` | 惊讶惊喜 |
| `disgusted` | 厌恶嫌弃 |
| `calm` | 平静淡然 |
| `excited` | 兴奋激动 |
| `tender` | 温柔体贴 |
| `serious` | 严肃认真 |
| `confident` | 自信骄傲 |
| `depressed` | 沮丧低落 |
| `slow` | 慢语速 |
| `fast` | 快语速 |
| `very_slow` | 非常慢 |
| `very_fast` | 非常快 |
| `quiet` | 小音量 |
| `loud` | 大音量 |
| `whisper` | 耳语 |
| `storytelling` | 讲故事语气 |

各引擎的翻译方式：

| 引擎 | 处理方式 |
|---|---|
| VoxCPM / IndexTTS | 括号前缀直接拼入文本：`(happy)你好` |
| Seed TTS 2.0 | 翻译为自然语言，放入 `context_texts` 字段 |
| dots.tts | 翻译为自然语言前缀，切换 `instruction_tts` 模板：`请用开心愉快的语气说：你好` |

不在字典中的 key 会直接透传为自然语言指令。

---

## 8. 生成流程

1. 选择 Excel
2. 程序自动识别可用 sheet（若多个会弹窗选择）
3. 点击 `Start`
4. UI 显示模型准备阶段（下载/加载/验证凭据）
5. 按行串行生成（避免显存冲突）
6. 每条生成后立刻写盘
7. 任务结束后弹出完成统计
8. 可按提示选择是否清除 VoiceID 参考音色缓存

---

## 9. 单句生成

切换到「单句生成」标签页，填写字段后点击 `Start`。

- `TOTTS_CN` 必填，`TOTTS_EN` 为空时仅导出 CN
- `生成条数 > 1` 时自动追加 `_001 / _002 / ...` 后缀
- 可在「音色参考文件」直接选取本次使用的参考音频
- 完成后自动弹出音频预览窗口，支持播放、多选、批量导出

---

## 10. 输出目录规则

输出根目录：`Output/`

有「细分区域」时：
```
Output/CN/{区域}/{细分区域}/{VoiceID}/{台本ID}.wav
Output/EN/{区域}/{细分区域}/{VoiceID}/{台本ID}.wav
```

无「细分区域」时：
```
Output/CN/{区域}/{VoiceID}/{台本ID}.wav
Output/EN/{区域}/{VoiceID}/{台本ID}.wav
```

---

## 11. VoiceID 音色一致性

### 自动缓存

首次成功生成某 VoiceID 后，自动保存到：
- `VoiceCache/{VoiceID}/reference.wav`
- `ref/{VoiceID}.wav`

### 手动导入

在「参考音色管理」页选择 VoiceID 后点击「为选中VoiceID导入参考音频」，支持 wav / flac / mp3 / m4a。

### 参考优先级

1. `REFERENCE_WAV_PATH` 列指定的文件（Excel 模式）
2. 单句生成页选择的「音色参考文件」
3. `VoiceCache/{VoiceID}/reference.wav`
4. `ref/{VoiceID}.wav`

---

## 12. 音频与生成参数

| 参数 | 说明 | 默认值 |
|---|---|---|
| `cfg_value` | 文本/风格约束强度（VoxCPM） | `2.0` |
| `inference_timesteps` | 推理步数（VoxCPM / IndexTTS / dots.tts） | `10` |
| `random_seed` | 随机种子，留空则每次不同 | 空 |
| `num_steps`（dots.tts） | Flow-matching 采样步数，10~32 | `10` |
| `guidance_scale`（dots.tts） | CFG 系数 | `1.2` |
| `speech_rate`（Seed TTS） | 语速，-50~100，0 为标准 | `0` |

### 响度归一化

- 开关：`启用响度归一化`
- 目标：`target_lufs`（默认 `-18 LUFS`）
- 峰值上限：`true_peak_ceiling`（默认 `-1.0 dBTP`）

### 覆盖策略

- `skip`：文件存在则跳过（默认）
- `overwrite`：覆盖旧文件
- `version`：自动追加 `_v2`, `_v3`...

---

## 13. 日志与报告

- 运行日志：`Logs/run_YYYYMMDD_HHMMSS.log`
- 结果报告：`Output/generation_report_YYYYMMDD_HHMMSS.csv`

报告包含每条任务状态、错误信息、输出路径、LUFS 结果等。

---

## 14. 离线运行

1. 先联网运行一次 `python bootstrap.py`，完成依赖和代码安装
2. 将所需模型放入 `models/`
3. 断网启动时勾选「离线模式（不联网下载模型）」
4. 直接运行 `python run_dev.py` 或双击启动脚本

---

## 15. 打包

```bash
python build_app.py
```

输出目录：`dist/`

---

## 16. 常见问题（FAQ）

**Q: `No module named 'voxcpm'`**
运行 `python bootstrap.py` 重新安装依赖。

**Q: `No module named 'indextts'`**
运行 `python bootstrap.py`，会自动克隆并安装 `third_party/index-tts`。

**Q: `Descriptors cannot be created directly` / protobuf 报错**
已固定 `protobuf==3.19.6`。若仍报错，手动执行：
```bash
.venv/bin/pip install "protobuf==3.19.6"
```

**Q: dots.tts 安装时 `pynini` 编译失败（macOS）**
需要先安装 OpenFst：
```bash
brew install openfst
```
然后重新运行 `python bootstrap.py`。

**Q: `IndexTTS 需要参考音频` / `dots.tts 需要参考音频`**
IndexTTS 和 dots.tts 是零样本克隆模型，必须提供参考音频。通过「参考音色管理」页为 VoiceID 导入参考音频，或在 Excel 里加 `REFERENCE_WAV_PATH` 列。

**Q: Seed TTS 2.0 报 HTTP 400**
检查「Seed TTS 2.0 设置」面板中的凭据是否正确填写。

**Q: Python 版本不兼容**
请使用 Python 3.10~3.12（推荐 3.11）。`bootstrap.py` 需要用项目 venv 对应的 Python 版本运行，不能用系统 3.13。

**Q: 点击 Start 后界面像卡死**
正常现象。模型准备阶段（下载/加载）耗时较长，日志区会持续输出进度。

**Q: "未找到包含必需列的 sheet"**
Excel 至少需要包含：`VoiceID`、`区域`、`台本ID`、`TOTTS_CN`（或 `TOTTS`）。

---

## 17. 项目结构（核心）

```text
NPC_LLM_TTS/
  app/
    main.py
    core/
      config.py
      tts_batch_runner.py
      voxcpm_manager.py
      index_tts_manager.py
      seed_tts_manager.py
      dots_tts_manager.py
      voice_cache.py
      audio_processor.py
      ...
    ui/
      main_window.py
      ...
  models/
    VoxCPM2/
    IndexTTS-2/
    MaskGCT/
    bigvgan_v2_22khz_80band_256x/
    dots.tts-soar/
  third_party/
    VoxCPM/
    index-tts/
  Output/
  VoiceCache/
  ref/
  Logs/
  config/settings.json
  bootstrap.py
  run_dev.py
  build_app.py
  requirements.txt
  start_mac.command
  start_windows.bat
```

---

## 18. 开源项目与许可证说明

本项目是一个桌面端工作流封装工具，调用和集成了若干第三方开源项目、模型与 Python 依赖。各第三方项目的版权、商标、模型权重和许可证归其原作者/权利方所有。使用、分发或商用本项目时，请同时遵守对应第三方项目和模型的许可证、模型卡与使用限制。

> 本节仅用于归属说明和合规提示，不构成法律意见。许可证版本和使用限制可能随上游项目更新而变化，请以官方仓库、模型卡和随包 `LICENSE` 文件为准。

### 18.1 TTS 引擎 / 模型

#### VoxCPM / VoxCPM2
- 上游作者：`OpenBMB`
- 代码仓库：[github.com/OpenBMB/VoxCPM](https://github.com/OpenBMB/VoxCPM)
- 许可证：`Apache-2.0`

#### IndexTTS / IndexTTS-2
- 上游作者：`Bilibili IndexTTS Team`
- 代码仓库：[github.com/index-tts/index-tts](https://github.com/index-tts/index-tts)
- 许可证：`bilibili Model Use License Agreement`（含商用限制，详见官方协议）

#### dots.tts
- 上游作者：`rednote-hilab`（小红书）
- 代码仓库：[github.com/rednote-hilab/dots.tts](https://github.com/rednote-hilab/dots.tts)
- 模型页面：[huggingface.co/rednote-hilab/dots.tts-soar](https://huggingface.co/rednote-hilab/dots.tts-soar)
- 许可证：`Apache-2.0`

#### Seed TTS 2.0
- 上游作者：`ByteDance / 火山引擎`
- API 文档：[volcengine.com/docs/6561](https://www.volcengine.com/docs/6561)
- 使用须遵守火山引擎服务协议与内容政策

### 18.2 IndexTTS 依赖模型

#### MaskGCT semantic codec
- 上游项目：`Amphion / open-mmlab`
- 模型页面：[huggingface.co/amphion/MaskGCT](https://huggingface.co/amphion/MaskGCT)

#### BigVGAN vocoder
- 上游作者：`NVIDIA`
- 代码仓库：[github.com/NVIDIA/BigVGAN](https://github.com/NVIDIA/BigVGAN)
- 许可证：`MIT`

### 18.3 Python 依赖

详见 `requirements.txt`。主要包括：`PySide6`、`torch`、`torchaudio`、`transformers`、`pandas`、`soundfile`、`librosa`、`pyloudnorm` 等，均归各自作者所有并适用其各自许可证。

### 18.4 生成内容责任

使用本项目时，用户应确保：

- 参考音频、Excel 文本、控制指令等输入内容拥有合法使用权
- 不使用本项目生成或传播违法、侵权、欺诈、冒充他人或违反第三方模型协议的内容
- 若对外发布生成音频，应根据适用法律和平台规则进行必要标识或取得授权
