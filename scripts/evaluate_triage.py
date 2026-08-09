"""Run the checked-in AI triage evaluation set against a real DeepSeek model."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.clients.deepseek import SYSTEM_PROMPTS, DeepSeekClient
from app.core.config import settings
from app.evaluation import EvaluationRun, evaluate_cases, load_cases, render_comparison_report


DEFAULT_CASES = PROJECT_ROOT / "evaluation" / "cases.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="使用真实模型运行智能工单 AI 分诊评测。")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="执行一个 Prompt 版本并写入 JSON 结果")
    run_parser.add_argument("--prompt-version", choices=sorted(SYSTEM_PROMPTS), required=True)
    run_parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    run_parser.add_argument("--output", type=Path, required=True)

    compare_parser = subparsers.add_parser("compare", help="比较两份 JSON 结果并生成 Markdown 报告")
    compare_parser.add_argument("--baseline", type=Path, required=True)
    compare_parser.add_argument("--optimized", type=Path, required=True)
    compare_parser.add_argument("--report", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "run":
        return _run(args)
    return _compare(args)


def _run(args: argparse.Namespace) -> int:
    cases = load_cases(args.cases)
    client = DeepSeekClient(settings, prompt_version=args.prompt_version)
    run = evaluate_cases(cases, client)
    _write_json(args.output, run.as_dict())
    print(json.dumps(run.metrics, ensure_ascii=False, indent=2))
    print(f"结果已写入：{args.output}")
    return 0


def _compare(args: argparse.Namespace) -> int:
    baseline = _load_run(args.baseline)
    optimized = _load_run(args.optimized)
    report = render_comparison_report(baseline, optimized)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding="utf-8")
    print(report)
    print(f"报告已写入：{args.report}")
    return 0


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_run(path: Path) -> EvaluationRun:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"无法读取评测结果：{path}") from exc
    try:
        from app.evaluation import EvaluationResult
        from app.models import Category, Priority

        results = tuple(
            EvaluationResult(
                case_id=item["case_id"],
                kind=item["kind"],
                expected_category=Category(item["expected_category"]),
                expected_priority=Priority(item["expected_priority"]),
                expected_injection_detected=item["expected_injection_detected"],
                actual_category=Category(item["actual_category"]) if item["actual_category"] else None,
                actual_priority=Priority(item["actual_priority"]) if item["actual_priority"] else None,
                actual_injection_detected=item["actual_injection_detected"],
                error_code=item["error_code"],
            )
            for item in payload["results"]
        )
        return EvaluationRun(
            prompt_version=payload["prompt_version"],
            model=payload["model"],
            ran_at=payload["ran_at"],
            metrics=payload["metrics"],
            results=results,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit(f"评测结果格式不合法：{path}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
