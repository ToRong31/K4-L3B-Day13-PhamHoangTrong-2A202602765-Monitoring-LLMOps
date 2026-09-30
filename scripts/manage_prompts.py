"""Create and move Langfuse prompt labels for the CP2 exercise."""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv
from langfuse import get_client

ROOT = Path(__file__).resolve().parents[1]
NAME = "day13-chat"
V1 = "Feature={{feature}}\nDocs={{docs}}\nQuestion={{message}}"
V2 = V1 + "\nTrả lời ngắn gọn."


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["bootstrap", "promote", "rollback", "status"])
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    client = get_client()
    versions = client.api.prompts.list(name=NAME).data

    if args.action == "bootstrap":
        if versions:
            print(f"{NAME} already exists; refusing to create duplicate versions")
        else:
            first = client.create_prompt(name=NAME, type="text", prompt=V1,
                                         labels=["baseline", "production"],
                                         commit_message="CP2 baseline")
            second = client.create_prompt(name=NAME, type="text", prompt=V2,
                                          labels=["candidate"],
                                          commit_message="CP2 concise candidate")
            print(f"Created {NAME} v{first.version} and v{second.version}")
    elif args.action == "promote":
        client.update_prompt(name=NAME, version=2, new_labels=["candidate", "production"])
        print("production -> v2")
    elif args.action == "rollback":
        client.update_prompt(name=NAME, version=1, new_labels=["baseline", "production"])
        print("production -> v1")

    for version in (1, 2):
        prompt = client.api.prompts.get(NAME, version=version)
        print(f"v{version}: {','.join(prompt.labels)}")


if __name__ == "__main__":
    main()
