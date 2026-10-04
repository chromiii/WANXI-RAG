#!/usr/bin/env python3
"""Project 1 RAG acceptance evaluator.

Examples:
    py scripts/eval_project1.py --mode offline
    py scripts/eval_project1.py --mode live
    py scripts/eval_project1.py --mode live --category hallucination
    py scripts/eval_project1.py --case official_blog --require-pdf-artifacts

This runner is intentionally deterministic about what it scores. It checks
routing, structure, citation closure, safety contracts and runtime PDF artifact
integrity. It does not pretend to automatically score subjective writing style.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trendee.config import runtime_data_dir
from trendee.grounding import claims
from trendee.service import Workbench


DEFAULT_CASES = ROOT / "eval" / "project1_cases.json"
COMMON_FORBIDDEN_CLAIM_PHRASES = (
    "资料显示",
    "资料中列出",
    "资料中提到",
    "资料提到",
    "资料指出",
    "根据资料",
    "品宣资料自述",
    "资料自述",
)


def _normalize_question(value: str) -> str:
    return re.sub(r"[？?！!。．.\s]+$", "", str(value).strip())


def _load_cases(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("case file must contain a JSON array")
    ids = [str(case.get("id", "")) for case in value]
    if any(not item for item in ids) or len(ids) != len(set(ids)):
        raise ValueError("every case needs a unique non-empty id")
    return value


def _citation_closure(result: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    document = result.get("document") or result.get("article")
    if not isinstance(document, dict):
        return ["generated document is missing"]

    claim_items = list(claims(document))
    if not claim_items:
        return ["generated document contains no grounded claims"]

    cited = {
        citation
        for claim in claim_items
        for citation in claim.get("citations", [])
        if isinstance(citation, str)
    }
    references = {
        str(item.get("id"))
        for item in result.get("references", [])
        if item.get("id")
    }
    retrieved = {
        str(item.get("id"))
        for item in result.get("retrieval_hits", [])
        if item.get("id")
    }

    missing_ref = sorted(cited - references)
    missing_retrieval = sorted(references - retrieved)
    if missing_ref:
        failures.append("citations missing from references: " + ", ".join(missing_ref))
    if missing_retrieval:
        failures.append("references missing from retrieval_hits: " + ", ".join(missing_retrieval))

    visuals = result.get("source_visuals", [])
    visual_ids = {str(item.get("id")) for item in visuals if item.get("id")}
    if not visual_ids <= references:
        failures.append(
            "source_visuals contain ids not used by generated references: "
            + ", ".join(sorted(visual_ids - references))
        )
    if len(visuals) > 3:
        failures.append(f"source_visuals exceeds max 3: {len(visuals)}")
    return failures


def _check_case(case: dict[str, Any], result: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    case_id = case["id"]
    status = result.get("status")

    expected_status = case.get("expected_status")
    if expected_status and status != expected_status:
        failures.append(f"status expected {expected_status!r}, got {status!r}")

    intent = result.get("task_intent") or {}
    if case.get("expected_intent") and intent.get("content_type") != case["expected_intent"]:
        failures.append(
            f"intent expected {case['expected_intent']!r}, got {intent.get('content_type')!r}"
        )
    if case.get("require_semantic_focus"):
        focus = str(intent.get("semantic_focus") or "").strip()
        if not focus:
            failures.append("semantic_focus is missing")
        elif result.get("mode") == "live" and focus == "generic":
            failures.append("live intent classifier returned generic semantic_focus")

    if case.get("require_user_goal"):
        goal = str(intent.get("user_goal") or intent.get("goal") or "").strip()
        if not goal:
            failures.append("user_goal is missing")

    document = result.get("document") or result.get("article")
    if case.get("document_must_be_absent") and document:
        failures.append("document should be absent for this early-stop case")

    max_calls = case.get("max_model_calls")
    if max_calls is not None and len(result.get("model_calls", [])) > int(max_calls):
        failures.append(
            f"model_calls expected <= {max_calls}, got {len(result.get('model_calls', []))}"
        )

    if status == "ok":
        if not isinstance(document, dict):
            failures.append("status=ok but generated document is missing")
            return failures

        if case.get("require_citations"):
            failures.extend(_citation_closure(result))

        faq_count = case.get("extension_faq_count")
        if faq_count is not None:
            actual = len(document.get("faq", []))
            if actual != int(faq_count):
                failures.append(f"extension FAQ expected {faq_count}, got {actual}")

        if case.get("first_faq_equals_topic"):
            faq = document.get("faq", [])
            if not faq:
                failures.append("FAQ list is empty")
            else:
                actual = _normalize_question(faq[0].get("question", ""))
                expected = _normalize_question(case["topic"])
                if actual != expected:
                    failures.append(
                        f"first FAQ must preserve original question: {actual!r} != {expected!r}"
                    )

        claim_text = "\n".join(str(item.get("text", "")) for item in claims(document))
        for phrase in COMMON_FORBIDDEN_CLAIM_PHRASES:
            if phrase in claim_text:
                failures.append(f"publishable claim contains forbidden source-meta wording: {phrase}")

        serialized = json.dumps(document, ensure_ascii=False)
        for phrase in case.get("must_not_contain", []):
            if phrase in serialized:
                failures.append(f"generated document contains forbidden phrase: {phrase}")

        if case.get("require_source_visuals"):
            visuals = result.get("source_visuals", [])
            if not visuals:
                failures.append("expected at least one cited source visual")
            failures.extend(_citation_closure(result))

        validation = result.get("validation") or {}
        if validation and not validation.get("citation_ids_valid", False):
            failures.append("validation.citation_ids_valid is not true")
        if validation and not validation.get("numeric_guard_passed", False):
            failures.append("validation.numeric_guard_passed is not true")

    required_steps = case.get("required_workflow_steps", [])
    if required_steps:
        actual_steps = [item.get("step") for item in result.get("workflow_trace", [])]
        missing = [step for step in required_steps if step not in actual_steps]
        if missing:
            failures.append("workflow_trace missing steps: " + ", ".join(missing))

    return [f"{case_id}: {item}" for item in failures]


def _runtime_pdf_artifact_check(data_dir: Path) -> dict[str, Any]:
    normalized = data_dir / "evidence_normalized.jsonl"
    manifest_path = data_dir / "normalization_manifest.json"
    if not normalized.exists():
        return {
            "status": "skipped",
            "reason": f"missing {normalized}",
            "checks": [],
        }

    rows = [
        json.loads(line)
        for line in normalized.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    manifest = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    max_chars = int(manifest.get("max_chars", 1000))

    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "pass": bool(ok), "detail": detail})

    ids = [str(row.get("id", "")) for row in rows]
    add("normalized_non_empty", bool(rows), f"chunks={len(rows)}")
    add("chunk_ids_unique", len(ids) == len(set(ids)), f"unique={len(set(ids))}/{len(ids)}")
    add(
        "stable_chunk_id_format",
        all(re.fullmatch(r"pdf-p\d{3}-c\d{2,}", item) for item in ids),
        "",
    )
    add(
        "content_within_max_chars",
        all(0 < len(str(row.get("content", ""))) <= max_chars for row in rows),
        f"max_chars={max_chars}",
    )
    add(
        "valid_physical_pages",
        all(isinstance(row.get("page"), int) and row["page"] >= 1 for row in rows),
        "",
    )

    source_hashes = {str(row.get("source_sha256", "")) for row in rows if row.get("source_sha256")}
    add("single_source_sha256", len(source_hashes) == 1, f"hashes={len(source_hashes)}")

    cross_page: list[str] = []
    missing_assets: list[str] = []
    for row in rows:
        page = int(row["page"])
        for source_id in row.get("metadata", {}).get("source_block_ids", []):
            if not str(source_id).startswith(f"pdf-p{page:03d}-"):
                cross_page.append(f"{row['id']} <- {source_id}")
        asset = row.get("asset_path")
        if asset and not (data_dir / asset).exists():
            missing_assets.append(str(asset))

    add(
        "no_cross_page_chunk_sources",
        not cross_page,
        "; ".join(cross_page[:5]),
    )
    add(
        "linked_page_assets_exist",
        not missing_assets,
        "; ".join(missing_assets[:5]),
    )

    failed = [item for item in checks if not item["pass"]]
    return {
        "status": "pass" if not failed else "fail",
        "normalized_file": str(normalized),
        "checks": checks,
        "failed_count": len(failed),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Project 1 RAG acceptance cases")
    parser.add_argument("--mode", choices=["offline", "live"], default="offline")
    parser.add_argument("--cases", default=str(DEFAULT_CASES))
    parser.add_argument("--case", action="append", dest="case_ids", default=[])
    parser.add_argument("--category", action="append", default=[])
    parser.add_argument("--report")
    parser.add_argument("--require-pdf-artifacts", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    args = parser.parse_args()

    case_path = Path(args.cases).expanduser().resolve()
    cases = _load_cases(case_path)
    if args.case_ids:
        wanted = set(args.case_ids)
        cases = [case for case in cases if case["id"] in wanted]
    if args.category:
        wanted_categories = set(args.category)
        cases = [case for case in cases if case.get("category") in wanted_categories]
    if not cases:
        raise SystemExit("No evaluation cases selected.")

    data_dir = runtime_data_dir()
    pdf_check = _runtime_pdf_artifact_check(data_dir)
    if args.require_pdf_artifacts and pdf_check["status"] != "pass":
        print("[FAIL] runtime PDF artifacts:", pdf_check.get("reason") or pdf_check)
        return 1

    workbench = Workbench(data_dir=data_dir)
    if args.mode == "live" and not workbench.config.api_key:
        raise SystemExit("DEEPSEEK_API_KEY is required for --mode live")

    results: list[dict[str, Any]] = []
    total_failures = 0
    started_all = time.perf_counter()

    for case in cases:
        started = time.perf_counter()
        failures: list[str] = []
        result: dict[str, Any] | None = None
        error: str | None = None
        try:
            result = workbench.write(
                case["topic"],
                case.get("audience", "中国出海品牌的市场与运营团队"),
                case.get("content_type", "auto"),
                args.mode,
                int(case.get("top_k", 6)),
            )
            failures = _check_case(case, result)
        except Exception as exc:  # evaluation report should capture unexpected failures
            error = f"{type(exc).__name__}: {exc}"
            failures = [f"{case['id']}: unexpected exception: {error}"]

        duration_ms = round((time.perf_counter() - started) * 1000)
        passed = not failures
        total_failures += len(failures)
        print(
            f"[{'PASS' if passed else 'FAIL'}] {case['id']} "
            f"({case.get('category', '-')}) {duration_ms} ms"
        )
        for failure in failures:
            print("   -", failure)

        results.append({
            "case": case,
            "pass": passed,
            "failures": failures,
            "error": error,
            "duration_ms": duration_ms,
            "result": result,
        })
        if failures and args.fail_fast:
            break

    report = {
        "suite": "project1_rag",
        "mode": args.mode,
        "case_file": str(case_path),
        "case_count": len(results),
        "passed": sum(1 for item in results if item["pass"]),
        "failed": sum(1 for item in results if not item["pass"]),
        "failure_count": total_failures,
        "duration_ms": round((time.perf_counter() - started_all) * 1000),
        "pdf_artifacts": pdf_check,
        "results": results,
    }

    report_path = (
        Path(args.report).expanduser().resolve()
        if args.report
        else data_dir / "eval" / f"project1_eval_{args.mode}.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print(
        f"Summary: {report['passed']}/{report['case_count']} passed, "
        f"{report['failed']} failed"
    )
    print("Report:", report_path)
    if pdf_check["status"] != "skipped":
        print("PDF artifact integrity:", pdf_check["status"])
    return 0 if report["failed"] == 0 and (not args.require_pdf_artifacts or pdf_check["status"] == "pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
