# Xiaohongshu Comment Moderator

一个本地优先的小红书评论采集、审核和监控工具。它可以把评论整理成 CSV，使用规则和 DeepSeek 语义复核识别辱骂、威胁、广告引流、造谣、嘲讽/阴阳怪气等风险，并输出可复核的处理报告。

这个项目默认不调用小红书私有接口，不绕验证码，不自动删除评论。它更适合作为评论风控助手：自动采集/识别/留痕，最终处置由人确认。

## 功能

- 从 CSV、JSON、TXT 读取评论并生成风险审核报告
- 浏览器自动化打开帖子链接，尝试提取网页端可见评论
- 保存浏览器滚动截图，作为 OCR 兜底输入
- 对评论截图做 OCR，转换成评论 CSV
- 定时监控评论来源，只报告新增评论
- 本地规则识别明显辱骂、威胁、隐私泄露、广告引流等
- 本地弱语义规则识别反讽、阴阳怪气、恶意揣测
- 可选 DeepSeek 大模型语义复核

## 项目结构

```text
xhs_comment_moderator.py        # 评论审核主脚本
xhs_browser_collect.py          # 浏览器自动化采集网页可见评论
xhs_ocr_to_comments.py          # 评论截图 OCR 转 CSV
xhs_monitor.py                  # 定时监控本地评论来源
xhs_monitor_config.example.json # 监控配置示例
sample_xhs_comments.csv         # 示例评论数据
.env.example                    # DeepSeek 配置模板
requirements.txt                # Python 依赖
```

## 安装

建议使用 Python 3.10 或更高版本。

```powershell
pip install -r .\requirements.txt
```

如果要使用浏览器自动化：

```powershell
python -m playwright install chromium
```

如果要使用 OCR，需要额外安装 Tesseract OCR 主程序和中文简体语言包 `chi_sim`。Python 包 `pillow` 和 `pytesseract` 已在 `requirements.txt` 中。

## 快速开始

用示例评论跑一次本地审核：

```powershell
python .\xhs_comment_moderator.py .\sample_xhs_comments.csv -o .\xhs_moderation_report.csv
```

输出报告会包含：

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

## 配置 DeepSeek

复制模板：

```powershell
Copy-Item .\.env.example .\.env
```

编辑 `.env`：

```env
DEEPSEEK_API_KEY=你的 DeepSeek API Key
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

`.env` 已在 `.gitignore` 中，不会提交到 GitHub。

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

- `all`：全部评论交给 DeepSeek 复核
- `uncertain`：复核本地规则认为低到中风险的评论
- `risky`：复核本地规则已判定为中高风险的评论

## 浏览器采集评论

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
python .\xhs_comment_moderator.py .\xhs_browser_comments.csv -o .\xhs_browser_moderation_report.csv --llm
```

浏览器脚本会保存截图到 `xhs_browser_screenshots`，网页端提取失败时可以走 OCR。

## OCR 截图转评论

对单张截图或截图文件夹运行：

```powershell
python .\xhs_ocr_to_comments.py .\xhs_browser_screenshots -o .\xhs_ocr_comments.csv
```

再审核 OCR 结果：

```powershell
python .\xhs_comment_moderator.py .\xhs_ocr_comments.csv -o .\xhs_moderation_report.csv --llm
```

OCR 会同时输出原始文本文件，方便检查识别错误：

```text
xhs_ocr_raw.txt
```

## 监控评论来源

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
  -> 可选 DeepSeek 语义复核
  -> 合并最终风险等级
```

本地弱语义规则会识别：

- 正向词和负向暗示同时出现：`真专业啊，就这水平也出来教人？`
- 反问或贬损句式：`不会真有人信吧？`
- 引号嘲讽：`所谓“专家”`
- 恶意揣测动机：`又开始恰饭洗白了`

DeepSeek 复核会返回结构化判断，包括风险等级、置信度、分类、建议动作和理由。脚本只在模型置信度足够时提升风险等级，避免把正常批评误判为恶意。

## 安全边界

这个项目不做：

- 小红书私有接口抓取
- 复用 cookie/token 调接口
- 绕验证码或绕风控
- 自动删除、举报、拉黑评论

建议把它用于：

- 评论采集
- 风险识别
- 新增评论监控
- 高风险评论留痕
- 人工复核前的预筛选

如果评论里包含手机号、地址、身份证等隐私信息，开启大模型复核前建议先脱敏。
