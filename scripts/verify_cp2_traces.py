"""Check CP2 observations against request IDs in the local structured log."""

from __future__ import annotations

import json
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from langfuse import get_client

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def main() -> None:
    lines = (ROOT / "data" / "logs.jsonl").read_text(encoding="utf-8").splitlines()
    requests = {r["correlation_id"] for line in lines if (r := json.loads(line)).get("event") == "request_received"}
    client = get_client()
    for attempt in range(3):
        try:
            response = client.api.observations.get_many(
                from_start_time=datetime.now(timezone.utc) - timedelta(hours=1),
                fields="core,basic,metadata,model,usage,prompt", limit=100,
            )
            break
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2)
    by_trace = defaultdict(list)
    for obs in response.data:
        if (obs.metadata or {}).get("correlation_id") in requests:
            by_trace[obs.trace_id].append(obs)
    complete = []
    print(f"Log requests: {len(requests)} | Langfuse traces matched: {len(by_trace)}")
    for trace_id, observations in by_trace.items():
        agent = next((o for o in observations if o.name == "lab-agent-run"), None)
        retrieval = next((o for o in observations if o.name == "retrieval"), None)
        generation = next((o for o in observations if o.name == "generation"), None)
        if not (agent and retrieval and generation):
            continue
        if retrieval.parent_observation_id != agent.id or generation.parent_observation_id != agent.id:
            continue
        complete.append(trace_id)
        metadata = agent.metadata or {}
        usage = generation.usage_details or {}
        cost = generation.cost_details or {}
        print(
            f"{trace_id} | {metadata.get('correlation_id')} | "
            f"{metadata.get('prompt_label')} v{metadata.get('prompt_version')} "
            f"source={metadata.get('prompt_source')} | "
            f"model={generation.model} input={usage.get('input')} output={usage.get('output')} "
            f"cost=${cost.get('total')} | prompt_link={generation.prompt_name} v{generation.prompt_version}"
        )
    print(f"Complete trees: {len(complete)}")
    if len(complete) < 10:
        raise SystemExit("Fewer than 10 complete traces")


if __name__ == "__main__":
    main()
