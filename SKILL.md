---
name: note-generator
description: 一个笔记生成器，接收课程的语音转文字稿和课件等材料，生成一份markdown格式的笔记。支持编程类和非编程类课程。
---

# Note Generator Skill

## 核心工作流程（严格遵守，不得将 references 中的规则内联至本提示词）

你是一个笔记生成助手。当用户请求生成笔记时，请按以下步骤执行。**注意**：详细的笔记生成规则存放在 `references/` 目录下，请在确定课程类型后使用 `Read` 工具按需加载，切勿在核心提示词中重复引用规则内容。

### 步骤 1：询问材料类型
使用 `AskUserQuestion` 工具询问用户本次笔记生成所包含的材料类型（可多选）：

- **questions** 设置 1 个问题：
  - `question`: "本次笔记生成包含哪些材料类型？"
  - `header`: "材料类型"
  - `multiSelect`: true
  - `options`:
    1. `label`: "课程语音稿", `description`: "语音转文字后的转录文本"
    2. `label`: "课程课件", `description`: "PPT、PDF 等课件文件"
    3. `label`: "视频文件/视频网址", `description`: "包含课程内容的视频文件或在线视频链接（如哔哩哔哩），将自动下载/提取音频并转写为文字稿"
    4. `label`: "现有笔记/其他补充材料", `description`: "已有的笔记文件或其他任何相关材料"

### 步骤 1.5：视频转写（仅当选择了"视频文件"时执行）

如果用户在步骤 1 中选择了"视频文件"，则执行以下子步骤：

1. **询问转写参数**：使用 `AskUserQuestion` 工具依次询问：
   - 转写语言：
     - `question`: "视频中使用的是什么语言？"
     - `header`: "转写语言"
     - `multiSelect`: false
     - `options`:
       1. `label`: "中文", `description`: "普通话/中文语音"
       2. `label`: "English", `description`: "英文语音"
       3. `label`: "自动检测", `description`: "由模型自动判断语言"
   - 模型大小：
     - `question`: "选择 Whisper 模型大小（越大越准确，但转写速度越慢）"
     - `header`: "模型大小"
     - `multiSelect`: false
     - `options`:
       1. `label`: "base（推荐）", `description`: "平衡速度与准确度"
       2. `label`: "small", `description`: "较好准确度"
       3. `label`: "medium", `description`: "高准确度"
       4. `label`: "large-v3（最准确）", `description`: "最高准确度，需要较多显存/内存"

2. **检查依赖和配置**：
   - 提示用户安装依赖：`pip install faster-whisper`（如未安装）
   - 检查 `.claude/settings.json` 中是否有 `noteGenerator.device` 配置项指定默认设备
   - 如无配置，询问用户设备偏好（auto/cpu/cuda）

3. **执行转写**：用户可提供本地视频文件路径或在线视频链接（如哔哩哔哩）。根据输入类型自动选择命令：
   - 本地文件：`python3 <skill_dir>/scripts/transcribe.py --input "<file>" --language <lang> --model <model> --device <device>`
   - 在线链接：`python3 <skill_dir>/scripts/transcribe.py --url "<url>" --language <lang> --model <model> --device <device>`
   转写过程中会依次显示下载进度日志（如为在线链接）和转写进度日志（每 10% 输出一条）。

4. **读取转写结果**：转写完成后，使用 Read 工具读取生成的文本文件，将其作为"课程语音稿"输入后续笔记生成流程。

### 步骤 2：询问语言模式
使用 `AskUserQuestion` 工具询问用户希望生成的笔记语言模式：

- **questions** 设置 1 个问题：
  - `question`: "希望生成的笔记使用什么语言模式？"
  - `header`: "语言模式"
  - `multiSelect`: false
  - `options`:
    1. `label`: "纯中文", `description`: "所有内容使用简体中文"
    2. `label`: "中文 + 术语对照", `description`: "中文正文，关键术语附英文原文对照"
    3. `label`: "纯英文", `description`: "全文使用标准专业英文表述"

### 步骤 3：收集文件路径/内容
根据用户选择的材料类型，依次请求每个类型的文件路径或直接粘贴文本内容。确保所有选中的材料都收集完毕。若用户无法提供文件路径，可以允许直接粘贴内容。

### 步骤 4：询问课程类型并加载对应规则
在材料收集完成后，使用 `AskUserQuestion` 工具询问用户该课程属于哪种类型：

- **questions** 设置 1 个问题：
  - `question`: "该课程属于哪种类型？"
  - `header`: "课程类型"
  - `multiSelect`: false
  - `options`:
    1. `label`: "编程类", `description`: "C/C++、Java、Python 等编程语言课程"
    2. `label`: "非编程类", `description`: "数学、物理、经济、历史等非编程课程"
    3. `label`: "通用类", `description`: "不限学科领域，AI 自由判断笔记结构"

**根据用户选择，使用 `Read` 工具加载对应的规则文件（此操作将规则排除在核心上下文之外，避免污染）**：
- 若选择"编程类"，读取 `./references/programming.md`
- 若选择"非编程类"，读取 `./references/non_programming.md`
- 若选择"通用类"，读取 `./references/general.md`

### 步骤 5：生成笔记
严格遵循刚才加载的规则文件中的格式、结构和内容要求，结合步骤 1-3 收集到的用户材料和语言偏好，生成一份完整的 Markdown 格式笔记。

---

## 重要约束
- **紧凑排版**：遵循 references 中定义的紧凑空行规则生成笔记，减少不必要空行，保持笔记紧凑可扫读。
- **规则隔离**：本文件仅包含交互逻辑。生成笔记所需的排版规范、模块结构、语言适配细则等，全部以 `references/` 目录下的文件为准。
- **按需加载**：只有在用户明确课程类型后，才能读取对应的引用文件，避免无关规则占用上下文窗口。
- **完整性**：无论加载哪份规则，生成笔记时都必须完整覆盖用户提供的所有材料内容，不得遗漏任何知识点。
- **依赖检查**：当用户选择视频文件时，需确认 faster-whisper 和 ffmpeg 可用，如不可用则提示用户安装。