# NPC LLM TTS 使用文档

`NPC LLM TTS` 是一个批量 NPC 台词 TTS 桌面应用，支持 Excel 批处理、VoiceID 音色一致性缓存、中英双语导出、响度归一化与任务日志追踪。

版权：`© Yadon Wong, 2026`

---

## 1. 功能概览

- 批量读取 Excel 并生成语音（CN/EN）
- 支持单句生成，无需 Excel 也可快速测试台词
- 支持模型选择：`VoxCPM2` / `IndexTTS`
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
3. 克隆 `third_party/VoxCPM`
4. 安装 `voxcpm` 包

### 模型下载与存放位置

`models/` 目录不随 GitHub 仓库上传，请在首次运行前或运行过程中按需下载模型，并放到以下固定位置。

#### VoxCPM2

- 下载链接：
  - HuggingFace: [openbmb/VoxCPM2](https://huggingface.co/openbmb/VoxCPM2)
  - ModelScope: [OpenBMB/VoxCPM2](https://modelscope.cn/models/OpenBMB/VoxCPM2)
- 存放位置：

```text
NPC_LLM_TTS/
└── models/
    └── VoxCPM2/
        ├── model.safetensors
        ├── audiovae.pth
        └── ...
```

程序在使用 `VoxCPM2` 引擎时会优先检查 `models/VoxCPM2/`。如果模型未就绪，会尝试自动从 HuggingFace 下载，失败后尝试 ModelScope。

#### IndexTTS-2

- 下载链接：
  - HuggingFace: [IndexTeam/IndexTTS-2](https://huggingface.co/IndexTeam/IndexTTS-2)
- 存放位置：

```text
NPC_LLM_TTS/
└── models/
    └── IndexTTS-2/
        ├── config.yaml
        ├── gpt.pth
        ├── s2mel.pth
        └── qwen0.6bemo4-merge/
            └── model.safetensors
```

#### IndexTTS-2 依赖模型

`IndexTTS-2` 还需要以下依赖模型：

- MaskGCT semantic codec
  - 下载链接：[amphion/MaskGCT](https://huggingface.co/amphion/MaskGCT)
  - 存放位置：

```text
NPC_LLM_TTS/
└── models/
    └── MaskGCT/
        └── semantic_codec/
            └── model.safetensors
```

- BigVGAN vocoder
  - 下载链接：[nvidia/bigvgan_v2_22khz_80band_256x](https://huggingface.co/nvidia/bigvgan_v2_22khz_80band_256x)
  - 存放位置：

```text
NPC_LLM_TTS/
└── models/
    └── bigvgan_v2_22khz_80band_256x/
        ├── config.json
        ├── bigvgan_generator.pt
        └── ...
```

> 注意：`models/` 已加入 `.gitignore`，不会上传到 GitHub。换电脑或重新克隆项目后，需要重新下载并放回上述目录。

### 离线运行

程序支持在无网络环境下运行，但需要提前在有网络时完成以下准备：

1. 至少运行一次：

```bash
python bootstrap.py
```

这一步会创建 `.venv`、安装 Python 依赖，并克隆/安装 `third_party/VoxCPM` 与 `third_party/index-tts`。

2. 按“模型下载与存放位置”章节，把需要的模型完整放入 `models/`：
   - `models/VoxCPM2/`
   - `models/IndexTTS-2/`
   - `models/MaskGCT/semantic_codec/`
   - `models/bigvgan_v2_22khz_80band_256x/`

3. 无网络启动时，直接运行：

```bash
python run_dev.py
```

或双击：

- macOS: `start_mac.command`
- Windows: `start_windows.bat`

启动脚本在检测到 `.venv` 已存在时，会直接启动程序，不再重复执行联网安装。

4. 在界面左侧“生成设置”中勾选：

```text
离线模式（不联网下载模型）
```

勾选后：

- `VoxCPM2` 只检查本地 `models/VoxCPM2/`，不会尝试联网下载。
- `IndexTTS` 只检查本地模型和依赖缓存，缺文件时会弹窗提示具体路径。

> 如果是第一次在新电脑运行，且还没有 `.venv` 或 `third_party/`，仍然需要先联网执行 `bootstrap.py`，或从已配置好的电脑完整拷贝 `.venv/`、`third_party/` 和 `models/`。

---

## 4. Excel 格式要求

### 最小必需列

- `VoiceID`
- `区域`
- `台本ID`
- `TOTTS_CN`（兼容旧列 `TOTTS`）

### 可选列

- `TOTTS_EN`（没有则自动跳过 EN 导出）
- `细分区域`（没有则不创建该层目录）
- `Control Instruction`（或 `控制指令` 等别名）
- 其他业务列（Character/Age/Gender...）均非必需

### 预览界面显示列

- `VoiceID`
- `区域`
- `TOTTS_CN`
- `TOTTS_EN`
- `状态`
- `参考状态`

---

## 5. 生成流程

1. 选择 Excel
2. 程序自动识别可用 sheet（若多个会弹窗选择）
3. 点击 `Start`
4. UI 显示模型准备阶段：
   - 检查/下载模型
   - 加载模型
   - 进入批处理
5. 按行串行生成（避免显存冲突）
6. 每条生成后立刻写盘
7. 任务结束后弹出完成统计
8. 可按提示选择是否清除 VoiceID 参考音色缓存

---

## 6. 单句生成用法

当你不想走 Excel 批量流程时，可在界面中使用 `单句生成` 标签页。该页面采用左对齐表单布局，适合快速填写与核对台词参数。

### 操作步骤

1. 切换到 `单句生成`
2. 填写以下字段：
   - `VoiceID`
   - `台本ID`
   - `区域`
   - `细分区域`（可选）
   - `音色参考文件`（可选，可选择 wav/flac/mp3/m4a）
   - `控制指令`（可选）
   - `TOTTS_CN`（必填）
   - `TOTTS_EN`（可选）
   - `生成条数`
3. 点击右侧 `Start`

### 生成规则

- `TOTTS_CN` 必填；`TOTTS_EN` 为空时仅导出 CN
- 当 `生成条数 > 1` 时，系统会自动生成台本ID后缀：
  - 例如台本ID填 `A001`，数量为 3，则实际输出为：
    - `A001_001`
    - `A001_002`
    - `A001_003`
- 单句生成同样复用当前“生成设置/音频设置/覆盖策略/音色缓存”
- 如果选择了 `音色参考文件`，本次单句生成会优先使用该文件作为参考音色
- 如果未选择参考文件，则按当前 VoiceID 的缓存和复用设置自动处理

---

## 7. 输出目录规则（CN/EN）

输出根目录：`Output/`

### 当存在“细分区域”时

- `Output/CN/{区域}/{细分区域}/{VoiceID}/{台本ID}.wav`
- `Output/EN/{区域}/{细分区域}/{VoiceID}/{台本ID}.wav`

### 当“细分区域”为空或不存在时

- `Output/CN/{区域}/{VoiceID}/{台本ID}.wav`
- `Output/EN/{区域}/{VoiceID}/{台本ID}.wav`

> EN 仅在 `TOTTS_EN` 非空时生成。

---

## 8. VoiceID 音色一致性

### 自动缓存

- 首次成功生成某 `VoiceID` 后，保存参考到：
  - `VoiceCache/{VoiceID}/reference.wav`
  - `ref/{VoiceID}.wav`

### 手动参考导入

在 `参考音色管理` 页：

1. 选择 VoiceID
2. 点击“为选中VoiceID导入参考音频”
3. 文件会缓存到：`ref/{VoiceID}.wav`

也可以在 `单句生成` 页填写 VoiceID 后，点击“为单句 VoiceID 导入参考音频”，快速为当前 VoiceID 设置参考音色。

### 参考音色列表管理

`参考音色管理` 页的表格支持整行选择：

- 单击选择一行
- 按住 `Shift` 可连续多选
- 按住 `Ctrl` / `Command` 可追加选择多行
- 右键选中行可打开菜单并删除选中音色
- 顶部“删除选中音色”按钮也支持删除多选项

多选删除时会弹出确认框，删除后会自动刷新参考音色列表和 Excel 预览中的参考状态。

### 生成完成后的缓存清理

任务完成后，程序会显示完成统计，并询问是否清除 VoiceID 参考音色缓存：

- 选择“是”：清空 `VoiceCache/` 与 `ref/` 中的参考音色，并刷新界面状态
- 选择“否”：保留当前参考音色缓存，方便后续继续复用

### 生成时参考优先级

1. `VoiceCache/{VoiceID}/reference.wav`
2. `ref/{VoiceID}.wav`

---

## 9. 参数说明

### `cfg_value`

- 文本/风格约束强度
- 越高越“听话”，但可能更硬
- 推荐：`2.0`（常用范围 `1.5~3.0`）

### `inference_timesteps`

- 推理步数
- 越高音质通常更稳但更慢
- 推荐：`10`（常用范围 `8~20`）

### `random_seed`

- 随机种子
- 固定后更可复现
- 不填则每次可能略有差异

---

## 10. 响度归一化

- 开关：`启用响度归一化`
- 目标：`target_lufs`（默认 `-18`）
- 峰值上限：`true_peak_ceiling`（默认 `-1.0 dBTP`）

归一化失败时：

- 不中断批次
- 仍保留格式正确的 wav
- 在状态/日志中标记失败

---

## 11. 覆盖策略

- `skip`：文件存在则跳过（默认）
- `overwrite`：覆盖旧文件
- `version`：自动追加 `_v2`, `_v3`...

---

## 12. 日志与报告

### 运行日志

- `Logs/run_YYYYMMDD_HHMMSS.log`

### 结果报告

- `Output/generation_report_YYYYMMDD_HHMMSS.csv`

包含每条任务状态、错误信息、输出路径、LUFS 结果等。

---

## 13. 打包

```bash
python build_app.py
```

输出目录：`dist/`

---

## 14. 常见问题（FAQ）

### Q1: `No module named 'voxcpm'`
运行一次：

```bash
python bootstrap.py
```

### Q2: Python 版本不兼容
请使用 Python 3.10~3.12（推荐 3.11）。

### Q3: 点击 Start 后像卡死
正常。模型准备阶段会显示进度提示与日志（下载/加载）。

### Q4: 报错 `unexpected keyword argument 'control_instruction'`
该问题已修复：当前版本不再单独传 control 参数，使用整段文本生成。

### Q5: “未找到包含必需列的 sheet”
检查是否至少包含：

- `VoiceID`
- `区域`
- `台本ID`
- `TOTTS_CN`（或 `TOTTS`）

---

## 15. 项目结构（核心）

```text
NPC_LLM_TTS/
  app/
    main.py
    core/
    ui/
  models/VoxCPM2/
  third_party/VoxCPM/
  Output/
  VoiceCache/
  ref/
  Logs/
  config/settings.json
  bootstrap.py
  run_dev.py
  build_app.py
  start_mac.command
  start_windows.bat
```

---

## 16. 开源项目与许可证说明

本项目是一个桌面端工作流封装工具，调用和集成了若干第三方开源项目、模型与 Python 依赖。各第三方项目的版权、商标、模型权重和许可证归其原作者/权利方所有。使用、分发或商用本项目时，请同时遵守对应第三方项目和模型的许可证、模型卡与使用限制。

> 本节仅用于归属说明和合规提示，不构成法律意见。许可证版本和使用限制可能随上游项目更新而变化，请以官方仓库、模型卡和随包 `LICENSE` 文件为准。

### 16.1 主要 TTS 引擎 / 模型

#### VoxCPM / VoxCPM2

- 项目名称：`VoxCPM`
- 上游作者/组织：`OpenBMB`
- 官方代码仓库：[https://github.com/OpenBMB/VoxCPM](https://github.com/OpenBMB/VoxCPM)
- 模型页面：
  - HuggingFace: [openbmb/VoxCPM2](https://huggingface.co/openbmb/VoxCPM2)
  - ModelScope: [OpenBMB/VoxCPM2](https://modelscope.cn/models/OpenBMB/VoxCPM2)
- 本项目中的用途：作为 `voxcpm` TTS 引擎，用于文本转语音、参考音色生成与复用。
- 本项目中的位置：
  - 代码：`third_party/VoxCPM/`（由 `bootstrap.py` 克隆并以 editable 方式安装）
  - 模型：`models/VoxCPM2/`（不随 GitHub 仓库上传）
- 许可证：`Apache-2.0`。本地克隆后可查看：`third_party/VoxCPM/LICENSE`。

#### IndexTTS / IndexTTS2

- 项目名称：`IndexTTS2`
- 上游作者/组织：`Bilibili IndexTTS Team`
- 官方代码仓库：[https://github.com/index-tts/index-tts](https://github.com/index-tts/index-tts)
- 模型页面：
  - HuggingFace: [IndexTeam/IndexTTS-2](https://huggingface.co/IndexTeam/IndexTTS-2)
  - ModelScope: [IndexTeam/IndexTTS-2](https://modelscope.cn/models/IndexTeam/IndexTTS-2)
- 本项目中的用途：作为 `indextts` TTS 引擎，支持基于参考音频的零样本音色生成。
- 本项目中的位置：
  - 代码：`third_party/index-tts/`（由 `bootstrap.py` 克隆并以 editable 方式安装）
  - 模型：`models/IndexTTS-2/`（不随 GitHub 仓库上传）
- 许可证/使用协议：`LicenseRef-Bilibili-IndexTTS` / `bilibili Model Use License Agreement`。本地克隆后可查看：`third_party/index-tts/LICENSE`。
- 特别注意：IndexTTS2 的模型使用协议包含使用限制、合规义务、高风险场景限制、下游分发要求等条款；如需商用或对外分发，请务必阅读并遵守官方协议。

### 16.2 IndexTTS 相关依赖模型

#### MaskGCT semantic codec

- 项目/模型名称：`MaskGCT`
- 上游项目：`Amphion / MaskGCT`
- 模型页面：[https://huggingface.co/amphion/MaskGCT](https://huggingface.co/amphion/MaskGCT)
- 相关代码/说明：[https://github.com/open-mmlab/Amphion](https://github.com/open-mmlab/Amphion)
- 本项目中的用途：作为 `IndexTTS2` 推理所需的 semantic codec 依赖。
- 本项目中的位置：`models/MaskGCT/semantic_codec/model.safetensors`（不随 GitHub 仓库上传）
- 许可证：请以官方 HuggingFace 模型卡、Amphion 仓库和随模型文件提供的许可证说明为准。

#### BigVGAN vocoder

- 项目/模型名称：`BigVGAN`
- 上游作者/组织：`NVIDIA`
- 官方代码仓库：[https://github.com/NVIDIA/BigVGAN](https://github.com/NVIDIA/BigVGAN)
- 模型页面：[nvidia/bigvgan_v2_22khz_80band_256x](https://huggingface.co/nvidia/bigvgan_v2_22khz_80band_256x)
- 本项目中的用途：作为 `IndexTTS2` 推理所需的 vocoder 依赖。
- 本项目中的位置：`models/bigvgan_v2_22khz_80band_256x/`（不随 GitHub 仓库上传）
- 许可证：HuggingFace 模型卡标注为 `MIT`，请以官方模型卡和仓库许可证为准。

### 16.3 Python 开源依赖

本项目还依赖以下 Python 开源库，详见 `requirements.txt`：

- UI / 桌面端：`PySide6`
- 数据处理：`pandas`, `openpyxl`, `numpy`, `scipy`
- 音频处理：`soundfile`, `librosa`, `pyloudnorm`, `ffmpeg-python`
- 深度学习 / 推理：`torch`, `torchaudio`, `omegaconf`, `protobuf`
- 模型下载与托管：`huggingface_hub`, `modelscope`
- 打包与工具：`pyinstaller`, `gitpython`

这些依赖均归各自作者/组织所有，并适用其各自的开源许可证。打包、分发或商用时，请根据实际发布形式检查这些依赖的许可证兼容性和声明要求。

### 16.4 生成内容与参考音频责任

本项目支持导入参考音频并生成语音。用户应确保：

- 参考音频、Excel 文本、控制指令等输入内容拥有合法使用权；
- 不使用本项目生成或传播违法、侵权、欺诈、冒充他人或违反第三方模型协议的内容；
- 若对外发布生成音频，应根据适用法律和平台规则进行必要标识或取得授权。
