# 小红书评论审核助手

这是一个本地脚本，用来把复制/导出的评论分成风险等级，并生成待处理清单。它不会登录小红书，也不会调用私有接口或绕过平台风控。

## 使用方法

```powershell
python .\xhs_comment_moderator.py .\sample_xhs_comments.csv -o .\xhs_moderation_report.csv
```

也支持 JSON 或 TXT：

```powershell
python .\xhs_comment_moderator.py .\comments.json -o .\report.json
python .\xhs_comment_moderator.py .\comments.txt -o .\report.csv
```

## 从截图 OCR 到审核报告

如果你有评论区截图，可以先运行 OCR 脚本：

```powershell
python .\xhs_ocr_to_comments.py .\screenshots -o .\xhs_ocr_comments.csv
```

然后把 OCR 结果交给审核脚本：

```powershell
python .\xhs_comment_moderator.py .\xhs_ocr_comments.csv -o .\xhs_moderation_report.csv
```

OCR 脚本支持单张图片或图片文件夹，格式包括 `.png`、`.jpg`、`.jpeg`、`.webp`、`.bmp`、`.tif`、`.tiff`。

本地 OCR 依赖 Tesseract。需要安装：

- Tesseract OCR 主程序
- 中文简体语言包 `chi_sim`
- 可选 Python 包：`pillow`、`pytesseract`

如果没有安装 Python 包，脚本会尝试调用系统里的 `tesseract` 命令行程序。

## 监控某个帖子

监控脚本使用配置文件，把每个帖子绑定到一个本地评论来源。来源可以是评论 CSV/TXT/JSON，也可以是评论区截图文件夹。

先复制示例配置：

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
      "url": "你的帖子链接",
      "source": "screenshots/my_post_1"
    }
  ]
}
```

只扫一次：

```powershell
python .\xhs_monitor.py -c .\xhs_monitor_config.json --once
```

持续监控：

```powershell
python .\xhs_monitor.py -c .\xhs_monitor_config.json
```

脚本会记录已见过的评论，只输出新增评论报告。报告会放在 `xhs_monitor_reports` 目录里。

## 浏览器自动获取评论

也可以尝试用浏览器自动化打开帖子链接，读取网页端可见评论：

```powershell
python .\xhs_browser_collect.py "你的小红书帖子链接" -o .\xhs_browser_comments.csv
python .\xhs_comment_moderator.py .\xhs_browser_comments.csv -o .\xhs_moderation_report.csv
```

如果登录或找评论区需要更久，推荐用按回车继续的模式：

```powershell
python .\xhs_browser_collect.py "你的小红书帖子链接" -o .\xhs_browser_comments.csv --wait-for-enter
```

浏览器打开后，你先在浏览器里登录、确认页面、打开到评论区；准备好后回到终端按 `Enter`，脚本才会开始滚动和采集。

首次使用需要安装 Playwright：

```powershell
pip install -r .\requirements.txt
python -m playwright install chromium
```

脚本会打开一个可见浏览器，并等待你手动登录或确认页面。登录状态会保存在 `.xhs_browser_profile` 目录里，下次可以复用。

如果网页端拿不到评论，脚本仍会把滚动过程截图保存到 `xhs_browser_screenshots`，然后可以走 OCR：

```powershell
python .\xhs_ocr_to_comments.py .\xhs_browser_screenshots -o .\xhs_ocr_comments.csv
python .\xhs_comment_moderator.py .\xhs_ocr_comments.csv -o .\xhs_moderation_report.csv
```

注意：这个脚本只读取页面上已经展示出来的文本，不调用小红书私有接口，不绕验证码，也不处理风控弹窗。

## 输入格式

CSV 支持这些列名：

- 评论内容：`comment`、`content`、`text`、`评论`、`评论内容`、`内容`
- 用户名：`author`、`user`、`nickname`、`用户名`、`昵称`、`用户`
- 链接：`url`、`note_url`、`link`、`笔记链接`、`链接`
- 时间：`time`、`created_at`、`date`、`时间`、`评论时间`、`日期`

TXT 文件按“一行一条评论”读取。

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

- `critical`：威胁、隐私泄露等，建议立即举报并留证。
- `high`：明显辱骂、骚扰、造谣等，建议优先处理。
- `medium`：广告、引流等，建议删除或拉黑。
- `low`：疑似刷屏等，需要人工复核。
- `feedback`：普通负面反馈，建议保留或回复。
- `clean`：未命中风险规则。

## 语义检测

脚本除了关键词，还内置了本地语义弱规则，用来识别不带明显脏词的嘲讽/阴阳怪气，例如：

- 正向词和负向暗示同时出现：`真专业啊，就这水平也出来教人？`
- 反问或贬损句式：`不会真有人信吧？`
- 引号嘲讽：`所谓“专家”`
- 恶意揣测动机：`又开始恰饭洗白了`

这类检测会标成 `疑似嘲讽` 或 `嘲讽/阴阳怪气`，默认建议人工复核，避免把正常玩笑或真实反馈误删。

## 大模型语义复核

如果你希望识别更隐晦的嘲讽、反讽、带节奏、恶意揣测，可以开启大模型复核。默认使用 DeepSeek 的 OpenAI-compatible Chat Completions 接口和 JSON Output。

先设置 API Key：

```powershell
$env:DEEPSEEK_API_KEY="你的 DeepSeek API Key"
```

然后运行：

```powershell
python .\xhs_comment_moderator.py .\sample_xhs_comments.csv -o .\xhs_moderation_report.csv --llm
```

可选参数：

```powershell
python .\xhs_comment_moderator.py .\sample_xhs_comments.csv -o .\xhs_moderation_report.csv --llm --llm-model deepseek-v4-flash --llm-mode all
```

`--llm-mode` 支持：

- `all`：所有评论都交给大模型复核，效果最好，成本最高。
- `uncertain`：只复核本地规则认为低风险或中风险的评论，适合找隐晦嘲讽。
- `risky`：只复核本地规则已经认为中高风险的评论，适合确认是否误杀。

也可以限制调用数量：

```powershell
python .\xhs_comment_moderator.py .\sample_xhs_comments.csv -o .\xhs_moderation_report.csv --llm --max-llm-comments 20
```

报告里会新增：

- `llm_risk_level`
- `llm_confidence`
- `llm_categories`
- `llm_action`
- `llm_reason`

注意：开启大模型后，评论文本会发送到模型服务商。评论里如果有手机号、地址、身份证等隐私信息，建议先脱敏再调用。

默认配置：

- `DEEPSEEK_API_KEY`：DeepSeek API Key
- `DEEPSEEK_MODEL`：默认 `deepseek-v4-flash`
- `DEEPSEEK_BASE_URL`：默认 `https://api.deepseek.com`

## 后续可以加的能力

- 接入截图 OCR，把评论区截图转成可审核文本。
- 加一个本地网页界面，逐条点“保留/删除/举报建议”。
- 接入大模型复核，减少误判。
- 对接 Appium 做“定位评论 + 人工确认后点击”，但不建议做绕风控式全自动删除。
