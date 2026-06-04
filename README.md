# 小红书评论检测助手

一个本地运行的小红书评论采集和风险审核工具。给同事使用时，可以直接打开本地网页，粘贴小红书帖子链接，按提示登录或打开评论区，然后查看恶意评论检测结果。

它默认不调用小红书私有接口，不绕验证码，不自动删除评论。它的定位是评论风控助手：自动采集、自动识别、生成留痕报告，最终处理仍由人确认。

## 适合做什么

- 通过小红书帖子链接采集网页端可见评论
- 自动识别辱骂、威胁、广告引流、隐私泄露、造谣、嘲讽/阴阳怪气等风险
- 在本地网页里查看需要优先处理的评论
- 导出 CSV 报告，方便留痕和复核
- 可接入任意 OpenAI-compatible 模型做语义复核
- 保留命令行、OCR、定时监控等高级用法

## 给同事使用：本地网页

### 1. 安装依赖

建议使用 Python 3.10 或更高版本。

```powershell
pip install -r .\requirements.txt
python -m playwright install chromium
```

### 2. 启动网页

```powershell
python .\xhs_ui_app.py
```

然后在浏览器打开：

```text
http://127.0.0.1:5000
```

### 3. 检测一个帖子

1. 在网页里粘贴小红书帖子链接。
2. 点击“开始检测”。
3. 系统会弹出一个浏览器窗口。
4. 如果需要登录、验证或手动打开评论区，请先在弹出的浏览器里处理好。
5. 回到网页，点击“我已打开评论区，继续检测”。
6. 等待系统自动滚动、采集评论、识别风险。
7. 在结果页查看需要优先处理的评论，也可以导出 CSV 报告。

检测历史、滚动截图和报告会保存在本地 `xhs_ui_data/` 目录。这个目录已加入 `.gitignore`，不会提交到仓库。

### 4. 配置强制模型复核

网页审核默认使用强制模型复核。你需要先在顶部点击“模型配置”，填好 API Key 后才能开始检测。

可配置内容：

- 是否启用强制模型复核
- API Key
- 模型名，默认 `gpt-4o-mini`
- Base URL，默认 `https://api.openai.com/v1`
- 复核范围，默认全部评论
- 最大复核条数，填 `0` 表示不限制
- 采集强度：标准 / 深度

保存后，后续检测会自动使用这个配置。API Key 保存在本机 `xhs_ui_data/settings.json`，页面只显示脱敏后的 Key。也可以点击“测试连接”确认配置是否可用。

常见 Base URL 示例：

- OpenAI：`https://api.openai.com/v1`
- DeepSeek：`https://api.deepseek.com`
- 中转网关：填写网关提供的 OpenAI-compatible 地址
- 公司内部服务：填写内部兼容 `/chat/completions` 的服务地址

强制模型复核只覆盖已经采集到的评论。如果网页没有展示某条评论，模型不会看到它。担心漏采时，可以把采集强度调成“深度”。

## 页面说明

- **新检测**：粘贴帖子链接并开始检测。
- **检测中**：显示当前步骤。需要人工登录或打开评论区时，页面会提示你继续。
- **检测结果**：优先展示风险评论，普通反馈和未命中评论放在折叠区。
- **历史记录**：查看最近检测过的帖子和结果。
- **模型配置**：配置强制模型复核、模型名、Base URL、复核范围、调用上限和采集强度。

风险评论会按严重程度排序：`critical`、`high`、`medium`、`low`。

## 常见问题

### 没有弹出浏览器

先确认安装了 Playwright 浏览器：

```powershell
python -m playwright install chromium
```

### 页面一直停在等待确认

这是正常流程。请在弹出的浏览器里登录小红书、处理验证，并把页面打开到评论区，然后回到本地网页点击“我已打开评论区，继续检测”。

### 没有采集到评论

可能原因：

- 没有登录小红书
- 页面没有打开到评论区
- 网页端没有展示评论
- 页面结构变化导致采集规则没有命中

可以重新检测一次，并确保评论区在弹出的浏览器里可见。

### 会不会自动删除评论

不会。这个工具只做采集、识别和报告，不会自动删除、举报或拉黑。

### 模型复核失败怎么办

强制模型复核模式下，检测会停止并提示错误，不会把仅本地规则的结果当成完整审核结论。请检查 API Key、模型名、Base URL 或网络状态后重新检测。

如果你临时只想用本地规则，可以到“模型配置”里关闭强制模型复核。

## 项目结构

```text
xhs_ui_app.py                   # 本地网页 UI，适合同事使用
xhs_browser_collect.py          # 浏览器自动化采集网页可见评论
xhs_comment_moderator.py        # 评论审核核心逻辑
xhs_ocr_to_comments.py          # 评论截图 OCR 转 CSV
xhs_monitor.py                  # 定时监控本地评论来源
xhs_monitor_config.example.json # 监控配置示例
sample_xhs_comments.csv         # 示例评论数据
.env.example                    # 模型配置模板
requirements.txt                # Python 依赖
templates/                      # 网页模板
static/                         # 网页样式和脚本
tests/                          # 自动化测试
```

## 高级用法：命令行审核

用示例评论跑一次本地审核：

```powershell
python .\xhs_comment_moderator.py .\sample_xhs_comments.csv -o .\xhs_moderation_report.csv
```

报告字段包括：

```text
risk_level
score
categories
action
reasons
llm_risk_level
llm_confidence
llm_categories
llm_action
llm_reason
```

不开 `--llm` 时，`llm_*` 字段为空。

## 配置 OpenAI-compatible 模型复核

日常使用推荐在网页顶部的“模型配置”里填写。下面是命令行方式，适合高级用户或批处理脚本。

复制模板：

```powershell
Copy-Item .\.env.example .\.env
```

编辑 `.env`：

```env
MODEL_API_KEY=你的模型 API Key
MODEL_NAME=gpt-4o-mini
MODEL_BASE_URL=https://api.openai.com/v1
```

如果使用 DeepSeek 或其他 OpenAI-compatible 服务，只需要把 `MODEL_NAME` 和 `MODEL_BASE_URL` 换成对应服务提供的值。

开启大模型复核：

```powershell
python .\xhs_comment_moderator.py .\sample_xhs_comments.csv -o .\xhs_moderation_report.csv --llm
```

只复核更容易误判的评论：

```powershell
python .\xhs_comment_moderator.py .\sample_xhs_comments.csv -o .\xhs_moderation_report.csv --llm --llm-mode uncertain
```

限制调用数量：

```powershell
python .\xhs_comment_moderator.py .\sample_xhs_comments.csv -o .\xhs_moderation_report.csv --llm --max-llm-comments 20
```

`--llm-mode` 支持：

- `all`：全部评论交给模型复核
- `uncertain`：复核本地规则认为低到中风险的评论
- `risky`：复核本地规则已判定为中高风险的评论

注意：开启大模型后，评论文本会发送到模型服务商。评论里如果有手机号、地址、身份证等隐私信息，建议先脱敏再调用。

## 高级用法：浏览器采集评论

直接给帖子链接，脚本会打开浏览器、等待你登录或确认页面，然后滚动并尝试读取网页端可见评论：

```powershell
python .\xhs_browser_collect.py "你的小红书帖子链接" -o .\xhs_browser_comments.csv --wait-for-enter
```

浏览器打开后：

1. 在浏览器里登录小红书或确认页面。
2. 打开到评论区。
3. 回到 PowerShell 按 `Enter`。
4. 等待脚本滚动和提取评论。

然后审核采集结果：

```powershell
python .\xhs_comment_moderator.py .\xhs_browser_comments.csv -o .\xhs_browser_moderation_report.csv
```

## 高级用法：OCR 截图转评论

如果网页端采集失败，但你有评论区截图，可以对单张截图或截图文件夹运行：

```powershell
python .\xhs_ocr_to_comments.py .\xhs_browser_screenshots -o .\xhs_ocr_comments.csv
```

再审核 OCR 结果：

```powershell
python .\xhs_comment_moderator.py .\xhs_ocr_comments.csv -o .\xhs_moderation_report.csv
```

OCR 需要额外安装 Tesseract OCR 主程序和中文简体语言包 `chi_sim`。OCR 会同时输出原始文本文件，方便检查识别错误：

```text
xhs_ocr_raw.txt
```

## 高级用法：监控评论来源

复制配置：

```powershell
Copy-Item .\xhs_monitor_config.example.json .\xhs_monitor_config.json
```

编辑 `xhs_monitor_config.json`：

```json
{
  "interval_seconds": 300,
  "state_file": "xhs_monitor_state.json",
  "output_dir": "xhs_monitor_reports",
  "posts": [
    {
      "name": "my_post_1",
      "url": "你的小红书帖子链接",
      "source": "xhs_browser_comments.csv"
    }
  ]
}
```

只扫描一次：

```powershell
python .\xhs_monitor.py -c .\xhs_monitor_config.json --once
```

持续监控：

```powershell
python .\xhs_monitor.py -c .\xhs_monitor_config.json
```

监控脚本会记录已见过的评论，只输出新增评论报告。

## 输入格式

CSV 支持这些列名：

- 评论内容：`comment`、`content`、`text`、`评论`、`评论内容`、`内容`
- 用户名：`author`、`user`、`nickname`、`用户名`、`昵称`、`用户`
- 链接：`url`、`note_url`、`link`、`笔记链接`、`链接`
- 时间：`time`、`created_at`、`date`、`时间`、`评论时间`、`日期`

TXT 文件按一行一条评论读取。

JSON 可以是数组：

```json
[
  {"author": "用户A", "comment": "评论内容"},
  {"author": "用户B", "comment": "另一条评论"}
]
```

也可以是：

```json
{"comments": [{"author": "用户A", "comment": "评论内容"}]}
```

## 风险等级

- `critical`：威胁、隐私泄露等，建议立即举报并留证
- `high`：明显辱骂、骚扰、造谣等，建议优先处理
- `medium`：广告、引流、明显嘲讽等，建议处理或复核
- `low`：疑似刷屏、轻度嘲讽等，需要人工复核
- `feedback`：普通负面反馈，建议保留或回复
- `clean`：未命中风险规则

## 语义审核逻辑

审核分两层：

```text
本地规则初筛
  -> 本地嘲讽/阴阳怪气弱语义规则
  -> OpenAI-compatible 模型语义复核
  -> 合并最终风险等级
```

本地弱语义规则会识别：

- 正向词和负向暗示同时出现：`真专业啊，就这水平也出来教人？`
- 反问或贬损句式：`不会真有人信吧？`
- 引号嘲讽：`所谓“专家”`
- 恶意揣测动机：`又开始恰饭洗白了`

Web UI 默认要求模型完成复核后才生成完整审核结果。命令行模式仍然可以通过 `--llm` 自行决定是否启用模型。模型复核会返回结构化判断，包括风险等级、置信度、分类、建议动作和理由。脚本只在模型置信度足够时提升风险等级，避免把正常批评误判为恶意。

## 安全边界

这个项目不做：

- 小红书私有接口抓取
- 复用 cookie/token 调接口
- 绕验证码或绕风控
- 自动删除、举报、拉黑评论

建议把它用于：

- 评论采集
- 风险识别
- 高风险评论留痕
- 人工复核前的预筛选
