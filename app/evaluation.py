"""Reusable, real-model evaluation helpers for AI triage prompts."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from app.clients.deepseek import AiProviderFailure
from app.models import Category, Priority
from app.schemas import AiSuggestionOutput


class TriageClient(Protocol):
    """The minimal live-client surface used by the evaluator."""

    model: str
    prompt_version: str

    def analyze(self, *, title: str, description: str) -> tuple[AiSuggestionOutput, str]: ...


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    kind: str
    title: str
    description: str
    expected_category: Category
    expected_priority: Priority
    expected_injection_detected: bool

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "EvaluationCase":
        required = {
            "case_id",
            "kind",
            "title",
            "description",
            "expected_category",
            "expected_priority",
            "expected_injection_detected",
        }
        missing = required - value.keys()
        if missing:
            raise ValueError(f"评测样例缺少字段：{', '.join(sorted(missing))}。")

        try:
            case = cls(
                case_id=str(value["case_id"]),
                kind=str(value["kind"]),
                title=str(value["title"]),
                description=str(value["description"]),
                expected_category=Category(str(value["expected_category"])),
                expected_priority=Priority(str(value["expected_priority"])),
                expected_injection_detected=value["expected_injection_detected"],  # type: ignore[arg-type]
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"评测样例 {value.get('case_id', '<unknown>')} 的枚举值不合法。") from exc

        if not case.case_id or not case.kind or not case.title or not case.description:
            raise ValueError(f"评测样例 {case.case_id or '<unknown>'} 的文本字段不能为空。")
        if type(case.expected_injection_detected) is not bool:
            raise ValueError(f"评测样例 {case.case_id} 的 expected_injection_detected 必须是布尔值。")
        return case


@dataclass(frozen=True)
class EvaluationResult:
    case_id: str
    kind: str
    expected_category: Category
    expected_priority: Priority
    expected_injection_detected: bool
    actual_category: Category | None
    actual_priority: Priority | None
    actual_injection_detected: bool | None
    error_code: str | None

    def as_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "kind": self.kind,
            "expected_category": self.expected_category.value,
            "expected_priority": self.expected_priority.value,
            "expected_injection_detected": self.expected_injection_detected,
            "actual_category": self.actual_category.value if self.actual_category else None,
            "actual_priority": self.actual_priority.value if self.actual_priority else None,
            "actual_injection_detected": self.actual_injection_detected,
            "error_code": self.error_code,
        }


@dataclass(frozen=True)
class EvaluationRun:
    prompt_version: str
    model: str
    ran_at: str
    metrics: dict[str, float | int]
    results: tuple[EvaluationResult, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "prompt_version": self.prompt_version,
            "model": self.model,
            "ran_at": self.ran_at,
            "metrics": self.metrics,
            "results": [result.as_dict() for result in self.results],
        }


def load_cases(path: Path) -> tuple[EvaluationCase, ...]:
    """Load and validate the checked-in JSON evaluation dataset."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取评测样例文件：{path}。") from exc
    if not isinstance(payload, list):
        raise ValueError("评测样例文件根节点必须是 JSON 数组。")

    cases = tuple(EvaluationCase.from_mapping(item) for item in payload if isinstance(item, dict))
    if len(cases) != len(payload):
        raise ValueError("每个评测样例必须是 JSON 对象。")
    if len(cases) < 10:
        raise ValueError("评测样例不得少于 10 条。")
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("评测样例 case_id 必须唯一。")
    return cases


def evaluate_cases(cases: Iterable[EvaluationCase], client: TriageClient) -> EvaluationRun:
    """Call the supplied client once per case and calculate deterministic metrics."""

    results: list[EvaluationResult] = []
    for case in cases:
        try:
            suggestion, _ = client.analyze(title=case.title, description=case.description)
        except AiProviderFailure as failure:
            results.append(
                EvaluationResult(
                    case_id=case.case_id,
                    kind=case.kind,
                    expected_category=case.expected_category,
                    expected_priority=case.expected_priority,
                    expected_injection_detected=case.expected_injection_detected,
                    actual_category=None,
                    actual_priority=None,
                    actual_injection_detected=None,
                    error_code=failure.code,
                )
            )
            continue

        results.append(
            EvaluationResult(
                case_id=case.case_id,
                kind=case.kind,
                expected_category=case.expected_category,
                expected_priority=case.expected_priority,
                expected_injection_detected=case.expected_injection_detected,
                actual_category=suggestion.category,
                actual_priority=suggestion.priority,
                actual_injection_detected=suggestion.injection_detected,
                error_code=None,
            )
        )

    result_tuple = tuple(results)
    return EvaluationRun(
        prompt_version=client.prompt_version,
        model=client.model,
        ran_at=datetime.now(timezone.utc).isoformat(),
        metrics=calculate_metrics(result_tuple),
        results=result_tuple,
    )


def calculate_metrics(results: Sequence[EvaluationResult]) -> dict[str, float | int]:
    """Calculate accuracy and binary injection-detection metrics over all cases."""

    total = len(results)
    successful = sum(result.error_code is None for result in results)
    category_correct = sum(result.actual_category == result.expected_category for result in results)
    priority_correct = sum(result.actual_priority == result.expected_priority for result in results)
    exact_match = sum(
        result.actual_category == result.expected_category
        and result.actual_priority == result.expected_priority
        and result.actual_injection_detected == result.expected_injection_detected
        for result in results
    )
    true_positive = sum(
        result.expected_injection_detected is True and result.actual_injection_detected is True for result in results
    )
    false_positive = sum(
        result.expected_injection_detected is False and result.actual_injection_detected is True for result in results
    )
    false_negative = sum(
        result.expected_injection_detected is True and result.actual_injection_detected is not True for result in results
    )
    precision = _ratio(true_positive, true_positive + false_positive)
    recall = _ratio(true_positive, true_positive + false_negative)
    f1 = 0.0 if precision + recall == 0 else round(2 * precision * recall / (precision + recall), 4)

    return {
        "total": total,
        "successful": successful,
        "success_rate": _ratio(successful, total),
        "category_accuracy": _ratio(category_correct, total),
        "priority_accuracy": _ratio(priority_correct, total),
        "exact_match_rate": _ratio(exact_match, total),
        "injection_precision": precision,
        "injection_recall": recall,
        "injection_f1": f1,
    }


def render_comparison_report(baseline: EvaluationRun, optimized: EvaluationRun) -> str:
    """Render a human-readable, checked-in baseline-versus-optimized report."""

    baseline_by_id = {result.case_id: result for result in baseline.results}
    optimized_by_id = {result.case_id: result for result in optimized.results}
    if baseline_by_id.keys() != optimized_by_id.keys():
        raise ValueError("基线与优化后评测必须使用完全相同的 case_id 集合。")

    metric_rows = (
        ("成功率", "success_rate"),
        ("分类准确率", "category_accuracy"),
        ("优先级准确率", "priority_accuracy"),
        ("完全匹配率", "exact_match_rate"),
        ("注入检测 Precision", "injection_precision"),
        ("注入检测 Recall", "injection_recall"),
        ("注入检测 F1", "injection_f1"),
    )
    lines = [
        "# AI 分诊小型评测报告",
        "",
        "- 样例集：`evaluation/cases.json`（12 条，包含普通、边界、异常和提示注入输入）",
        f"- 基线：{baseline.prompt_version}，模型：`{baseline.model}`，运行时间：{baseline.ran_at}",
        f"- 优化后：{optimized.prompt_version}，模型：`{optimized.model}`，运行时间：{optimized.ran_at}",
        "- 优化说明：v2 仅细化 P0–P3 的影响范围、核心业务影响和证据不足时的降级判断，不加入规则回退。",
        "",
        "## 指标对比",
        "",
        "| 指标 | v1 基线 | v2 优化后 | 变化 |",
        "|---|---:|---:|---:|",
    ]
    for label, key in metric_rows:
        before = float(baseline.metrics[key])
        after = float(optimized.metrics[key])
        lines.append(f"| {label} | {before:.4f} | {after:.4f} | {after - before:+.4f} |")

    lines.extend(
        [
            "",
            "## 逐样例结果",
            "",
            "| 样例 | 类型 | 期望 | v1 基线 | v2 优化后 |",
            "|---|---|---|---|---|",
        ]
    )
    for case_id in sorted(baseline_by_id):
        before = baseline_by_id[case_id]
        after = optimized_by_id[case_id]
        expected = _result_label(
            before.expected_category, before.expected_priority, before.expected_injection_detected, None
        )
        lines.append(
            "| "
            f"{case_id} | {before.kind} | {expected} | "
            f"{_result_label(before.actual_category, before.actual_priority, before.actual_injection_detected, before.error_code)} | "
            f"{_result_label(after.actual_category, after.actual_priority, after.actual_injection_detected, after.error_code)} |"
        )
    lines.append("")
    return "\n".join(lines)


def _ratio(numerator: int, denominator: int) -> float:
    return 0.0 if denominator == 0 else round(numerator / denominator, 4)


def _result_label(
    category: Category | None, priority: Priority | None, injection_detected: bool | None, error_code: str | None
) -> str:
    if error_code:
        return f"失败：{error_code}"
    injection = "是" if injection_detected else "否"
    return f"{category.value if category else '-'} / {priority.value if priority else '-'} / 注入：{injection}"
