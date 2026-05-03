#!/usr/bin/env python3
"""Run or readiness-check the RAGAS Amnesty QA benchmark.

Default local evaluator:
- LLM: Ollama `qwen3.5:9b`
- Embeddings: existing TEI/Jina v5 endpoint at http://127.0.0.1:7997/embed

The report is public-safe: it records config, aggregate scores, and per-row scores,
but not raw contexts, answers, references, prompts, or secrets.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REQUIRED_PACKAGES = ("datasets", "ragas", "langchain_ollama")
DEFAULT_DATASET_ID = "vibrantlabsai/amnesty_qa"
DEFAULT_DATASET_CONFIG = "english_v3"
DEFAULT_SPLIT = "eval"
DEFAULT_OLLAMA_MODEL = "qwen3.5:9b"
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_TEI_URL = "http://127.0.0.1:7997/embed"
DEFAULT_TEI_MODEL = "jinaai/jina-embeddings-v5-text-small-retrieval"


@dataclass(frozen=True)
class TeiEmbeddings:
    url: str
    query_prefix: str = "query: "
    document_prefix: str = "document: "
    timeout_seconds: int = 30

    def _post(self, inputs: list[str]) -> list[list[float]]:
        request = urllib.request.Request(
            self.url,
            data=json.dumps({"inputs": inputs}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if isinstance(payload, list):
            return [[float(value) for value in row] for row in payload]
        if isinstance(payload, dict) and isinstance(payload.get("data"), list):
            return [[float(value) for value in item["embedding"]] for item in payload["data"]]
        if isinstance(payload, dict) and isinstance(payload.get("embeddings"), list):
            return [[float(value) for value in row] for row in payload["embeddings"]]
        raise RuntimeError("unsupported TEI embedding response shape")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._post([self.document_prefix + text for text in texts])

    def embed_query(self, text: str) -> list[float]:
        return self._post([self.query_prefix + text])[0]


def _package_present(package: str) -> bool:
    return importlib.util.find_spec(package) is not None


def _ollama_model_present(model: str) -> bool:
    proc = subprocess.run(
        ["ollama", "show", model],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    return proc.returncode == 0


def _tei_ready(url: str) -> bool:
    try:
        embeddings = TeiEmbeddings(url=url, timeout_seconds=5).embed_query("benchmark smoke")
    except Exception:
        return False
    return bool(embeddings)


def _readiness(*, ollama_model: str, tei_url: str, dataset_id: str, dataset_config: str, split: str, sample_count: int) -> dict[str, Any]:
    missing_dependencies = [package for package in REQUIRED_PACKAGES if not _package_present(package)]
    issues: list[dict[str, Any]] = []
    for dependency in missing_dependencies:
        issues.append({"code": "missing_dependency", "dependency": dependency})
    ollama_ready = _ollama_model_present(ollama_model)
    if not ollama_ready:
        issues.append({"code": "ollama_model_missing_or_unavailable", "model": ollama_model})
    tei_ready = _tei_ready(tei_url)
    if not tei_ready:
        issues.append({"code": "tei_embeddings_unavailable", "url": tei_url})
    ready = not issues
    return {
        "schema": "brainstack.ragas_amnesty_readiness.v2",
        "status": "ready" if ready else "not_ready",
        "ready": ready,
        "dataset": {
            "id": dataset_id,
            "config": dataset_config,
            "split": split,
            "sample_count": int(sample_count),
        },
        "evaluator": {
            "llm_provider": "ollama",
            "llm_model": ollama_model,
            "ollama_ready": ollama_ready,
            "embeddings_provider": "tei",
            "embeddings_model": DEFAULT_TEI_MODEL,
            "embeddings_url": tei_url,
            "tei_ready": tei_ready,
        },
        "required_dependencies": list(REQUIRED_PACKAGES),
        "missing_dependencies": missing_dependencies,
        "issues": issues,
        "public_safe": True,
    }


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if value != value:  # NaN
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    metric_names = sorted({key for row in rows for key in row if key not in {"case_index"}})
    metrics: dict[str, Any] = {}
    for name in metric_names:
        values = [_safe_float(row.get(name)) for row in rows]
        clean = [value for value in values if value is not None]
        metrics[name] = {
            "mean": round(statistics.fmean(clean), 6) if clean else None,
            "count": len(clean),
            "missing_count": len(values) - len(clean),
        }
    return metrics


def _load_eval_dataset(dataset_id: str, dataset_config: str, split: str, sample_count: int):
    from datasets import load_dataset
    from ragas import EvaluationDataset, SingleTurnSample

    dataset = load_dataset(dataset_id, dataset_config, split=split)
    rows = []
    for index, row in enumerate(dataset):
        if index >= sample_count:
            break
        rows.append(
            SingleTurnSample(
                user_input=row["user_input"],
                retrieved_contexts=list(row["retrieved_contexts"]),
                response=row["response"],
                reference=row["reference"],
            )
        )
    return EvaluationDataset(samples=rows), len(rows)


def _result_rows(result: Any) -> list[dict[str, Any]]:
    try:
        frame = result.to_pandas()
        rows: list[dict[str, Any]] = []
        for index, row in frame.iterrows():
            item: dict[str, Any] = {"case_index": int(index)}
            for key, value in row.to_dict().items():
                if key in {"user_input", "response", "reference", "retrieved_contexts", "contexts", "answer", "ground_truth"}:
                    continue
                safe = _safe_float(value)
                if safe is not None:
                    item[key] = round(safe, 6)
            rows.append(item)
        return rows
    except Exception:
        scores = getattr(result, "scores", []) or []
        rows = []
        for index, score in enumerate(scores):
            item = {"case_index": index}
            if isinstance(score, dict):
                for key, value in score.items():
                    safe = _safe_float(value)
                    if safe is not None:
                        item[key] = round(safe, 6)
            rows.append(item)
        return rows


def _selected_metric_names(raw: str) -> list[str]:
    names = [name.strip() for name in raw.split(",") if name.strip()]
    valid = {"faithfulness", "context_precision", "context_recall", "answer_relevancy"}
    unknown = [name for name in names if name not in valid]
    if unknown:
        raise ValueError(f"unknown metric(s): {', '.join(unknown)}")
    return names


def _run_ragas(*, args: argparse.Namespace, readiness: dict[str, Any]) -> dict[str, Any]:
    from langchain_ollama import ChatOllama
    from ragas import evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import Faithfulness, LLMContextPrecisionWithReference, LLMContextRecall, ResponseRelevancy
    from ragas.run_config import RunConfig

    dataset, actual_sample_count = _load_eval_dataset(
        args.dataset_id,
        args.dataset_config,
        args.split,
        args.sample_count,
    )
    llm = LangchainLLMWrapper(
        ChatOllama(
            model=args.ollama_model,
            base_url=args.ollama_base_url,
            temperature=0,
            num_ctx=args.ollama_num_ctx,
            num_predict=args.ollama_num_predict,
            reasoning=False,
        )
    )
    embeddings = LangchainEmbeddingsWrapper(
        TeiEmbeddings(url=args.tei_url, timeout_seconds=args.tei_timeout_seconds)
    )
    selected_metrics = _selected_metric_names(args.metrics)
    metric_result_names = {
        "faithfulness": "faithfulness",
        "context_precision": "llm_context_precision_with_reference",
        "context_recall": "context_recall",
        "answer_relevancy": "answer_relevancy",
    }
    metrics = []
    for metric_name in selected_metrics:
        if metric_name == "faithfulness":
            metrics.append(Faithfulness(llm=llm, max_retries=1))
        elif metric_name == "context_precision":
            metrics.append(LLMContextPrecisionWithReference(llm=llm, max_retries=1))
        elif metric_name == "context_recall":
            metrics.append(LLMContextRecall(llm=llm, max_retries=1))
        elif metric_name == "answer_relevancy":
            metrics.append(ResponseRelevancy(llm=llm, embeddings=embeddings))
    start = time.perf_counter()
    result = evaluate(
        dataset=dataset,
        metrics=metrics,
        llm=llm,
        embeddings=embeddings,
        run_config=RunConfig(timeout=args.timeout_seconds, max_workers=args.max_workers, max_retries=1),
        raise_exceptions=False,
        show_progress=True,
        batch_size=args.batch_size,
    )
    elapsed_ms = round((time.perf_counter() - start) * 1000, 3)
    rows = _result_rows(result)
    metric_summary = _aggregate(rows)
    issues: list[dict[str, Any]] = []
    for requested_name in selected_metrics:
        result_name = metric_result_names[requested_name]
        summary = metric_summary.get(result_name)
        if not summary or summary.get("count") != actual_sample_count:
            issues.append(
                {
                    "code": "requested_metric_missing_or_partial",
                    "metric": requested_name,
                    "result_name": result_name,
                    "available_count": 0 if not summary else summary.get("count", 0),
                    "expected_count": actual_sample_count,
                }
            )
    status = "pass" if not issues else "partial"
    return {
        "schema": "brainstack.ragas_amnesty_benchmark.v1",
        "status": status,
        "ready": True,
        "public_safe": True,
        "claim_boundary": "External RAGAS Amnesty QA run using local Ollama evaluator and TEI/Jina embeddings. Per-row raw dataset text is intentionally omitted from this report.",
        "dataset": {
            "id": args.dataset_id,
            "config": args.dataset_config,
            "split": args.split,
            "sample_count_requested": int(args.sample_count),
            "sample_count_actual": actual_sample_count,
        },
        "evaluator": readiness["evaluator"],
        "metric_selection": {
            "requested": selected_metrics,
            "result_names": {name: metric_result_names[name] for name in selected_metrics},
        },
        "runtime": {
            "elapsed_ms": elapsed_ms,
            "timeout_seconds": args.timeout_seconds,
            "max_workers": args.max_workers,
            "batch_size": args.batch_size,
        },
        "metrics": metric_summary,
        "case_scores": rows,
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--dataset-id", default=DEFAULT_DATASET_ID)
    parser.add_argument("--dataset-config", default=DEFAULT_DATASET_CONFIG)
    parser.add_argument("--split", default=DEFAULT_SPLIT)
    parser.add_argument("--sample-count", type=int, default=20)
    parser.add_argument("--metrics", default="faithfulness,context_precision")
    parser.add_argument("--readiness-only", action="store_true")
    parser.add_argument("--ollama-model", default=DEFAULT_OLLAMA_MODEL)
    parser.add_argument("--ollama-base-url", default=DEFAULT_OLLAMA_BASE_URL)
    parser.add_argument("--ollama-num-ctx", type=int, default=8192)
    parser.add_argument("--ollama-num-predict", type=int, default=4096)
    parser.add_argument("--tei-url", default=DEFAULT_TEI_URL)
    parser.add_argument("--tei-timeout-seconds", type=int, default=30)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--max-workers", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=1)
    args = parser.parse_args()

    readiness = _readiness(
        ollama_model=args.ollama_model,
        tei_url=args.tei_url,
        dataset_id=args.dataset_id,
        dataset_config=args.dataset_config,
        split=args.split,
        sample_count=args.sample_count,
    )
    report = readiness if args.readiness_only or not readiness["ready"] else _run_ragas(args=args, readiness=readiness)
    text = json.dumps(report, indent=2, sort_keys=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    if report.get("status") == "pass":
        return 0
    if report.get("status") == "partial":
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
