#!/usr/bin/env python3
"""Local Xiaohongshu comment moderation helper.

This script does not log in to Xiaohongshu or call private platform APIs.
It classifies exported/copied comments and produces a review queue so you can
delete, report, or ignore comments in the official app with a clear reason.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


TEXT_COLUMNS = ("comment", "content", "text", "评论", "评论内容", "内容")
AUTHOR_COLUMNS = ("author", "user", "nickname", "用户名", "昵称", "用户")
URL_COLUMNS = ("url", "note_url", "link", "笔记链接", "链接")
TIME_COLUMNS = ("time", "created_at", "date", "时间", "评论时间", "日期")


RULES = [
    {
        "name": "personal_attack",
        "label": "人身攻击/辱骂",
        "severity": 4,
        "action": "建议删除；严重时举报",
        "patterns": [
            r"傻[逼b比]|煞笔|脑残|弱智|废物|垃圾|贱|滚|有病|死全家|去死|丑[逼b比]",
            r"你妈|尼玛|nmsl|sb|fuck|bitch|idiot|stupid",
        ],
    },
    {
        "name": "threat",
        "label": "威胁/恐吓",
        "severity": 5,
        "action": "建议立即举报并保留证据",
        "patterns": [
            r"弄死|打死|杀了|等着.*收拾|线下.*找你|知道你家|找上门|报复你",
            r"kill you|beat you|come after you",
        ],
    },
    {
        "name": "privacy",
        "label": "隐私泄露/人肉",
        "severity": 5,
        "action": "建议立即举报并保留证据",
        "patterns": [
            r"手机号|电话|身份证|住址|家庭住址|学校|公司地址|门牌号",
            r"\b1[3-9]\d{9}\b",
            r"\b\d{17}[\dXx]\b",
        ],
    },
    {
        "name": "spam",
        "label": "广告/引流",
        "severity": 3,
        "action": "建议删除；频繁出现可拉黑",
        "patterns": [
            r"加[微薇vV]|微信|vx|v信|私聊|私信.*优惠|代理|招商|兼职|刷单",
            r"低价|秒杀|返现|优惠券|薅羊毛|联系我|点主页",
            r"https?://|www\.|\.com|\.cn",
        ],
    },
    {
        "name": "harassment",
        "label": "骚扰/恶意纠缠",
        "severity": 4,
        "action": "建议删除；重复出现可拉黑",
        "patterns": [
            r"天天来骂|见一次骂一次|一直盯着你|别想好过|恶心你|烦死你",
            r"反复|刷屏|复制粘贴",
        ],
    },
    {
        "name": "rumor",
        "label": "造谣/不实指控",
        "severity": 4,
        "action": "建议人工复核；确认不实后举报",
        "patterns": [
            r"骗子|诈骗|黑心|假货|收钱洗白|恰烂钱|骗钱",
            r"听说.*(出事|翻车|违法)|有人说.*(假|骗|黑)",
        ],
    },
    {
        "name": "negative_feedback",
        "label": "普通负面反馈",
        "severity": 1,
        "action": "建议保留或回复，不建议删除",
        "patterns": [
            r"不好用|一般|失望|不推荐|太贵|踩雷|没效果|体验不好|不喜欢",
        ],
    },
]


SARCASM_POSITIVE_CUES = (
    "真棒",
    "真厉害",
    "太厉害",
    "好棒",
    "优秀",
    "高级",
    "专业",
    "懂了",
    "学到了",
    "谢谢",
    "笑死",
    "绝了",
    "可以的",
    "牛",
)

SARCASM_NEGATIVE_CUES = (
    "就这",
    "不会吧",
    "不是吧",
    "也配",
    "装",
    "翻车",
    "割韭菜",
    "智商税",
    "恰饭",
    "洗白",
    "演",
    "尴尬",
    "无语",
    "呵呵",
    "哈哈",
    "笑死",
)

RHETORICAL_PATTERNS = (
    r"不会.*吧",
    r"不是.*吧",
    r"这也.*\?",
    r"这也.*？",
    r"谁信.*[?？]",
    r"你自己信吗",
    r"懂的都懂",
    r"建议.*先.*(照照镜子|提升|学习|看看)",
    r"就这水平",
    r"就这还",
    r"别出来",
)

QUOTE_MARKERS = ("所谓", "号称", "自称", "‘", "’", "“", "”", '"')


def detect_sarcasm(text: str) -> tuple[int, list[str]]:
    """Detect indirect mockery without relying on direct insult keywords."""
    normalized = text.lower()
    evidence: list[str] = []
    score = 0

    if any(cue in text for cue in SARCASM_POSITIVE_CUES) and any(
        cue in text for cue in SARCASM_NEGATIVE_CUES
    ):
        score += 2
        evidence.append("正向词和负向暗示同时出现，疑似反讽")

    for pattern in RHETORICAL_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            score += 1
            evidence.append("出现反问/贬损句式")
            break

    if any(marker in text for marker in QUOTE_MARKERS) and any(
        cue in text for cue in ("专业", "高级", "真实", "良心", "原创", "专家")
    ):
        score += 1
        evidence.append("使用引号或限定词弱化正向称呼，疑似嘲讽")

    if re.search(r"(真|太|非常|特别).{0,4}(棒|厉害|优秀|高级).{0,8}(呢|啊|哦|哈|呵)", text):
        score += 1
        evidence.append("夸张赞美带语气词，疑似阴阳怪气")

    if re.search(r"(又|还).*?(开始|来).*?(演|装|洗|吹|卖惨)", text):
        score += 2
        evidence.append("出现恶意揣测动机的表达")

    if "..." in normalized or "。。。" in text or "？？" in text or "??" in normalized:
        if any(cue in text for cue in SARCASM_NEGATIVE_CUES):
            score += 1
            evidence.append("省略号/重复问号叠加负向暗示")

    return min(score, 4), evidence


@dataclass
class Comment:
    index: int
    text: str
    author: str = ""
    url: str = ""
    time: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Decision:
    risk_level: str
    score: int
    categories: list[str]
    action: str
    reasons: list[str]
    llm: dict[str, Any] | None = None


RISK_TO_SCORE = {
    "clean": 0,
    "feedback": 1,
    "low": 2,
    "medium": 3,
    "high": 4,
    "critical": 5,
}

SCORE_TO_RISK = {
    0: "clean",
    1: "feedback",
    2: "low",
    3: "medium",
    4: "high",
    5: "critical",
}


class LlmModerator:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.deepseek.com",
        timeout: int = 60,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def review(self, comment: Comment, rule_decision: Decision) -> dict[str, Any]:
        system_prompt = (
            "你是中文社区评论审核助手。请判断评论是否包含恶意、嘲讽、阴阳怪气、"
            "骚扰、威胁、隐私泄露、广告引流、造谣，或只是普通负面反馈。"
            "不要因为正常批评就判恶意。"
            "你必须只输出一个 JSON 对象，不要输出 Markdown，不要输出解释文本。"
            "JSON 格式示例："
            '{"risk_level":"medium","confidence":0.82,'
            '"categories":["嘲讽/阴阳怪气"],"action":"人工复核",'
            '"reason":"表面赞美但结合反问句式构成反讽。"}'
        )
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "comment": comment.text,
                            "author": comment.author,
                            "rule_risk_level": rule_decision.risk_level,
                            "rule_categories": rule_decision.categories,
                            "rule_reasons": rule_decision.reasons,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "response_format": {"type": "json_object"},
            "stream": False,
            "max_tokens": 800,
            "thinking": {"type": "disabled"},
        }

        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM API HTTP {exc.code}: {details}") from exc

        text = extract_chat_completion_text(data)
        if not text:
            raise RuntimeError(f"LLM API returned no output text: {data}")
        result = json.loads(text)
        result = validate_llm_result(result)
        result["provider"] = "deepseek_chat_completions"
        result["model"] = self.model
        return result


def extract_chat_completion_text(data: dict[str, Any]) -> str:
    choices = data.get("choices", [])
    if not choices:
        return ""
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()
    return ""


def validate_llm_result(result: dict[str, Any]) -> dict[str, Any]:
    valid_risks = set(RISK_TO_SCORE)
    valid_categories = {
        "人身攻击/辱骂",
        "威胁/恐吓",
        "隐私泄露/人肉",
        "广告/引流",
        "骚扰/恶意纠缠",
        "造谣/不实指控",
        "嘲讽/阴阳怪气",
        "普通负面反馈",
        "未命中",
    }
    valid_actions = {
        "无需处理",
        "建议保留或回复",
        "人工复核",
        "建议删除",
        "建议举报",
        "建议删除并举报",
        "建议留证后举报",
    }

    risk_level = str(result.get("risk_level", "clean"))
    if risk_level not in valid_risks:
        result["risk_level"] = "low"

    try:
        confidence = float(result.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0
    result["confidence"] = max(0, min(1, confidence))

    categories = result.get("categories", [])
    if not isinstance(categories, list):
        categories = []
    result["categories"] = [
        str(category) for category in categories if str(category) in valid_categories
    ] or ["未命中"]

    action = str(result.get("action", "人工复核"))
    if action not in valid_actions:
        action = "人工复核"
    result["action"] = action
    result["reason"] = str(result.get("reason", "")).strip()
    return result


def pick_value(row: dict[str, Any], candidates: Iterable[str]) -> str:
    normalized = {str(key).strip().lower(): value for key, value in row.items()}
    for name in candidates:
        value = normalized.get(name.lower())
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def load_comments(path: Path) -> list[Comment]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))
        return [
            Comment(
                index=i + 1,
                text=pick_value(row, TEXT_COLUMNS),
                author=pick_value(row, AUTHOR_COLUMNS),
                url=pick_value(row, URL_COLUMNS),
                time=pick_value(row, TIME_COLUMNS),
                raw=row,
            )
            for i, row in enumerate(rows)
            if pick_value(row, TEXT_COLUMNS)
        ]

    if suffix == ".json":
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        if isinstance(data, dict):
            data = data.get("comments", data.get("data", []))
        if not isinstance(data, list):
            raise ValueError("JSON input must be a list or contain a comments/data list.")
        comments = []
        for i, item in enumerate(data):
            if isinstance(item, str):
                comments.append(Comment(index=i + 1, text=item))
            elif isinstance(item, dict):
                text = pick_value(item, TEXT_COLUMNS)
                if text:
                    comments.append(
                        Comment(
                            index=i + 1,
                            text=text,
                            author=pick_value(item, AUTHOR_COLUMNS),
                            url=pick_value(item, URL_COLUMNS),
                            time=pick_value(item, TIME_COLUMNS),
                            raw=item,
                        )
                    )
        return comments

    with path.open("r", encoding="utf-8-sig") as file:
        return [
            Comment(index=i + 1, text=line.strip())
            for i, line in enumerate(file)
            if line.strip()
        ]


def classify(comment: Comment) -> Decision:
    text = comment.text.lower()
    categories: list[str] = []
    reasons: list[str] = []
    matched_actions: list[str] = []
    score = 0

    for rule in RULES:
        rule_matches = []
        for pattern in rule["patterns"]:
            if re.search(pattern, text, flags=re.IGNORECASE):
                rule_matches.append(pattern)
        if rule_matches:
            categories.append(str(rule["label"]))
            matched_actions.append(str(rule["action"]))
            score = max(score, int(rule["severity"]))
            reasons.append(f"{rule['label']}: 命中 {len(rule_matches)} 条规则")

    sarcasm_score, sarcasm_reasons = detect_sarcasm(comment.text)
    if sarcasm_score >= 3:
        categories.append("嘲讽/阴阳怪气")
        reasons.extend(f"嘲讽/阴阳怪气: {reason}" for reason in sarcasm_reasons)
        matched_actions.append("建议人工复核；确认恶意后删除或回复澄清")
        score = max(score, 3)
    elif sarcasm_score > 0 and score == 0:
        categories.append("疑似嘲讽")
        reasons.extend(f"疑似嘲讽: {reason}" for reason in sarcasm_reasons)
        matched_actions.append("建议人工复核")
        score = max(score, 2)

    repeated_chars = re.search(r"(.)\1{5,}", comment.text)
    if repeated_chars:
        categories.append("疑似刷屏")
        reasons.append("疑似刷屏: 出现连续重复字符")
        matched_actions.append("建议人工复核；确认刷屏后删除")
        score = max(score, 2)

    if len(comment.text) > 180 and score > 0:
        reasons.append("长文本且命中风险规则，建议人工复核上下文")

    if score >= 5:
        risk_level = "critical"
        action = "立即处理：举报/删除/留证"
    elif score == 4:
        risk_level = "high"
        action = "优先处理：删除或举报，必要时拉黑"
    elif score == 3:
        risk_level = "medium"
        action = "建议处理：删除广告或引流内容"
    elif score == 2:
        risk_level = "low"
        action = "人工复核"
    elif score == 1:
        risk_level = "feedback"
        action = "建议保留或回复"
    else:
        risk_level = "clean"
        action = "无需处理"

    if matched_actions and score not in (0, 1):
        action = "; ".join(dict.fromkeys(matched_actions))

    return Decision(
        risk_level=risk_level,
        score=score,
        categories=categories or ["未命中"],
        action=action,
        reasons=reasons or ["未命中风险规则"],
    )


def should_use_llm(decision: Decision, mode: str) -> bool:
    if mode == "all":
        return True
    if mode == "risky":
        return decision.score >= 3
    if mode == "uncertain":
        return decision.score <= 3
    return False


def merge_llm_decision(decision: Decision, llm_result: dict[str, Any]) -> Decision:
    llm_risk = str(llm_result.get("risk_level", "clean"))
    llm_score = RISK_TO_SCORE.get(llm_risk, 0)
    confidence = float(llm_result.get("confidence", 0))

    # Trust model escalation only when it is reasonably confident. This keeps
    # normal criticism from being over-moderated by a single ambiguous judgment.
    if llm_score > decision.score and confidence >= 0.55:
        decision.score = llm_score
        decision.risk_level = SCORE_TO_RISK[llm_score]
        if llm_result.get("action"):
            decision.action = str(llm_result["action"])

    for category in llm_result.get("categories", []):
        if category not in decision.categories and category != "未命中":
            decision.categories.append(str(category))

    if llm_result.get("reason"):
        decision.reasons.append(f"模型复核: {llm_result['reason']}")

    decision.llm = llm_result
    return decision


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "index",
        "risk_level",
        "score",
        "categories",
        "action",
        "reasons",
        "llm_risk_level",
        "llm_confidence",
        "llm_categories",
        "llm_action",
        "llm_reason",
        "author",
        "time",
        "url",
        "comment",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(rows, file, ensure_ascii=False, indent=2)


def build_rows(comments: list[Comment]) -> list[dict[str, Any]]:
    return build_rows_with_options(comments)


def build_rows_with_options(
    comments: list[Comment],
    llm_moderator: LlmModerator | None = None,
    llm_mode: str = "all",
    max_llm_comments: int | None = None,
) -> list[dict[str, Any]]:
    rows = []
    llm_calls = 0
    for comment in comments:
        decision = classify(comment)
        if llm_moderator and should_use_llm(decision, llm_mode):
            if max_llm_comments is None or llm_calls < max_llm_comments:
                llm_result = llm_moderator.review(comment, decision)
                decision = merge_llm_decision(decision, llm_result)
                llm_calls += 1

        llm_result = decision.llm or {}
        rows.append(
            {
                "index": comment.index,
                "risk_level": decision.risk_level,
                "score": decision.score,
                "categories": "、".join(decision.categories),
                "action": decision.action,
                "reasons": "；".join(decision.reasons),
                "llm_risk_level": llm_result.get("risk_level", ""),
                "llm_confidence": llm_result.get("confidence", ""),
                "llm_categories": "、".join(llm_result.get("categories", [])),
                "llm_action": llm_result.get("action", ""),
                "llm_reason": llm_result.get("reason", ""),
                "author": comment.author,
                "time": comment.time,
                "url": comment.url,
                "comment": comment.text,
            }
        )
    return rows


def print_summary(rows: list[dict[str, Any]]) -> None:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["risk_level"]] = counts.get(row["risk_level"], 0) + 1

    print("审核完成")
    for level in ("critical", "high", "medium", "low", "feedback", "clean"):
        if level in counts:
            print(f"- {level}: {counts[level]}")

    priority = {"critical": 0, "high": 1, "medium": 2}
    review_rows = sorted(
        [row for row in rows if row["risk_level"] in priority],
        key=lambda row: (priority[row["risk_level"]], int(row["index"])),
    )
    if review_rows:
        print("\n优先处理前 10 条：")
        for row in review_rows[:10]:
            text = row["comment"]
            preview = text[:60] + ("..." if len(text) > 60 else "")
            print(f"[{row['risk_level']}] #{row['index']} {row['categories']} - {preview}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify Xiaohongshu comments and produce a moderation queue."
    )
    parser.add_argument("input", type=Path, help="Input .csv, .json, or .txt file.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("xhs_moderation_report.csv"),
        help="Output report path. Use .json for JSON output; defaults to CSV.",
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Enable LLM semantic review. Requires DEEPSEEK_API_KEY by default.",
    )
    parser.add_argument(
        "--llm-model",
        default=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        help=(
            "DeepSeek model for semantic review. Defaults to DEEPSEEK_MODEL "
            "or deepseek-v4-flash."
        ),
    )
    parser.add_argument(
        "--llm-base-url",
        default=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        help=(
            "DeepSeek OpenAI-compatible base URL. Defaults to DEEPSEEK_BASE_URL "
            "or https://api.deepseek.com."
        ),
    )
    parser.add_argument(
        "--llm-mode",
        choices=["all", "uncertain", "risky"],
        default="all",
        help="Which comments should be sent to the LLM.",
    )
    parser.add_argument(
        "--max-llm-comments",
        type=int,
        default=None,
        help="Optional cap on the number of comments sent to the LLM.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    comments = load_comments(args.input)
    llm_moderator = None
    if args.llm:
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError("启用 --llm 需要先设置环境变量 DEEPSEEK_API_KEY。")
        llm_moderator = LlmModerator(
            api_key=api_key,
            model=args.llm_model,
            base_url=args.llm_base_url,
        )

    rows = build_rows_with_options(
        comments,
        llm_moderator=llm_moderator,
        llm_mode=args.llm_mode,
        max_llm_comments=args.max_llm_comments,
    )

    if args.output.suffix.lower() == ".json":
        write_json(args.output, rows)
    else:
        write_csv(args.output, rows)

    print_summary(rows)
    print(f"\n报告已生成: {args.output}")


if __name__ == "__main__":
    main()
