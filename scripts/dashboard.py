"""Local CP2 dashboard. Run: python scripts/dashboard.py"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from statistics import mean
from urllib.parse import urlparse

import yaml

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "data" / "logs.jsonl"
HTML = ROOT / "scripts" / "dashboard.html"
CONFIG = ROOT / "config" / "dashboard.yaml"


def percentile(values: list[float], percent: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * percent / 100
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower), 2)


def snapshot() -> dict:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["dashboard"]
    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=config["time_range_minutes"])
    rows = []
    if LOG.exists():
        for line in LOG.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                ts = datetime.fromisoformat(row["ts"].replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if start <= ts <= now:
                    row["_minute"] = ts.strftime("%H:%M")
                    rows.append(row)
            except (ValueError, KeyError, TypeError):
                continue

    first_minute = now.replace(second=0, microsecond=0) - timedelta(minutes=59)
    minutes = [(first_minute + timedelta(minutes=i)).strftime("%H:%M") for i in range(60)]
    groups = defaultdict(list)
    for row in rows:
        groups[row["_minute"]].append(row)

    def by_event(event: str) -> list[dict]:
        return [row for row in rows if row.get("event") == event]

    def num(row: dict, field: str) -> float:
        try:
            return float(row.get(field) or 0)
        except (TypeError, ValueError):
            return 0

    received = by_event("request_received")
    sent = by_event("response_sent")
    failed = by_event("request_failed")
    with_tool = [row for row in rows if isinstance(row.get("tool_success"), bool)]
    error_rate = len(failed) / len(received) * 100 if received else None
    retrieval_success = sum(row["tool_success"] for row in with_tool) / len(with_tool) * 100 if with_tool else None
    error_types = defaultdict(int)
    for row in failed:
        error_types[row.get("error_type") or "unknown"] += 1

    series = {key: [] for key in (
        "p50", "p95", "p99", "ttft_p95", "traffic", "errors", "retrieval",
        "cost", "tokens_in", "tokens_out", "quality",
    )}
    cumulative_cost = cumulative_in = cumulative_out = 0
    for minute in minutes:
        bucket = groups[minute]
        responses = [row for row in bucket if row.get("event") == "response_sent"]
        requests = [row for row in bucket if row.get("event") == "request_received"]
        failures = [row for row in bucket if row.get("event") == "request_failed"]
        retrievals = [row for row in bucket if isinstance(row.get("tool_success"), bool)]
        latencies = [num(row, "latency_ms") for row in responses]
        ttfts = [num(row, "ttft_ms") for row in responses]
        for key, pct in (("p50", 50), ("p95", 95), ("p99", 99)):
            series[key].append(percentile(latencies, pct))
        series["ttft_p95"].append(percentile(ttfts, 95))
        series["traffic"].append(len(requests))
        series["errors"].append(round(len(failures) / len(requests) * 100, 2) if requests else None)
        series["retrieval"].append(round(sum(row["tool_success"] for row in retrievals) / len(retrievals) * 100, 2) if retrievals else None)
        cumulative_cost += sum(num(row, "cost_usd") for row in responses)
        cumulative_in += sum(num(row, "tokens_in") for row in responses)
        cumulative_out += sum(num(row, "tokens_out") for row in responses)
        series["cost"].append(round(cumulative_cost, 6))
        series["tokens_in"].append(cumulative_in)
        series["tokens_out"].append(cumulative_out)
        scores = [num(row, "quality_score") for row in responses if row.get("quality_score") is not None]
        series["quality"].append(round(mean(scores), 3) if scores else None)

    return {
        "title": config["title"], "minutes": minutes, "series": series,
        "time_range_minutes": config["time_range_minutes"], "refresh_seconds": config["refresh_seconds"],
        "generated_at": now.isoformat(),
        "thresholds": {panel["id"]: panel["threshold"] for panel in config["panels"]},
        "panels": {panel["id"]: {"title": panel["title"], "unit": panel["unit"]} for panel in config["panels"]},
        "summary": {
            "latency": {"p50": percentile([num(r, "latency_ms") for r in sent], 50),
                        "p95": percentile([num(r, "latency_ms") for r in sent], 95),
                        "p99": percentile([num(r, "latency_ms") for r in sent], 99),
                        "ttft_p95": percentile([num(r, "ttft_ms") for r in sent], 95)},
            "traffic": {"requests": len(received), "rate_per_minute": round(len(received) / 60, 2)},
            "errors": {"error_rate_pct": round(error_rate, 2) if error_rate is not None else None,
                       "retrieval_success_pct": round(retrieval_success, 2) if retrieval_success is not None else None,
                       "error_types": dict(error_types)},
            "cost": {"total_usd": round(sum(num(r, "cost_usd") for r in sent), 6)},
            "tokens": {"input": int(sum(num(r, "tokens_in") for r in sent)),
                       "output": int(sum(num(r, "tokens_out") for r in sent))},
            "quality": {"mean": round(mean([num(r, "quality_score") for r in sent]), 3) if sent else None},
        },
    }


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/data":
            body = json.dumps(snapshot(), ensure_ascii=False).encode("utf-8")
            mime = "application/json; charset=utf-8"
        elif path == "/":
            body = HTML.read_bytes()
            mime = "text/html; charset=utf-8"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    print("Dashboard: http://127.0.0.1:8501", flush=True)
    ThreadingHTTPServer(("127.0.0.1", 8501), Handler).serve_forever()
