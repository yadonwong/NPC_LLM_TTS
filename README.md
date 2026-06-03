# NPC LLM TTS 使用文档

`NPC LLM TTS` 是一个批量 NPC 台词 TTS 桌面应用，支持 Excel 批处理、VoiceID 音色一致性缓存、中英双语导出、响度归一化与任务日志追踪。

版权：`© Yadon Wong, 2026`

---

## 1. 功能概览

- 批量读取 Excel 并生成语音（CN/EN）
- 支持模型选择：`VoxCPM2` / `IndexTTS`
- 同 `VoiceID` 复用参考音色，保持一致音色
- 支持手动导入参考音频（`ref/`）
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

---

## 6. 单句生成用法

当你不想走 Excel 批量流程时，可在界面中使用 `单句生成` 标签页。

### 操作步骤

1. 切换到 `单句生成`
2. 填写以下字段：
   - `VoiceID`
   - `台本ID`
   - `区域`
   - `细分区域`（可选）
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

