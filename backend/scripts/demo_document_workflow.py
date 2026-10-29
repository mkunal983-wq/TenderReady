"""Run the real sample-PDF workflow against the local API. Never fakes inference."""
import argparse
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urlparse

import httpx
from tenderready.config import Settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    if urlparse(args.base_url).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("This demonstration only sends credentials to a local API.")
    settings = Settings()
    sample = Path(__file__).resolve().parents[2] / "samples" / "sample-tender.pdf"
    data = sample.read_bytes()
    headers = {"Authorization": f"Bearer {settings.app_api_token.get_secret_value()}"} if settings.app_api_token.get_secret_value() else {}
    with httpx.Client(base_url=args.base_url, headers=headers, timeout=40, trust_env=False) as client:
        def checked(response):
            response.raise_for_status()
            return response.json()
        checked(client.get("/ready"))
        workspace = checked(client.post("/workspaces", json={"title": "Sample tender PDF workflow", "supplier_name": "Synthetic Example IT Supplier"}))
        prefix = f"/workspaces/{workspace['id']}"
        doc = checked(client.post(prefix + "/documents", content=data,
            headers={"Content-Type": "application/pdf", "X-Filename": "sample-tender.pdf"}))
        downloaded = client.get(prefix + f"/documents/{doc['id']}/file")
        downloaded.raise_for_status()
        assert hashlib.sha256(downloaded.content).digest() == hashlib.sha256(data).digest()
        checked(client.post(prefix + f"/documents/{doc['id']}/analyze"))
        deadline = time.monotonic() + settings.analysis_timeout_seconds + 180
        while time.monotonic() < deadline:
            docs = checked(client.get(prefix + "/documents"))
            state = next(d["analysis"] for d in docs if d["id"] == doc["id"])
            if state["status"] in {"succeeded", "failed"}:
                break
            time.sleep(2)
        else:
            raise SystemExit("Analysis still pending; inspect the workspace UI.")
        requirements = checked(client.get(prefix + f"/documents/{doc['id']}/requirements"))
        print(json.dumps({
            "workspace_id": workspace["id"], "document_id": doc["id"],
            "sample": sample.name, "upload": "passed", "source_download_sha256": "matched",
            "page_count": doc["page_count"], "analysis": state,
            "requirement_count": len(requirements), "source_pages": sorted({r["page"] for r in requirements}),
            "all_awaiting_review": all(r["review_status"] == "awaiting_review" for r in requirements),
            "live_inference": "passed" if state["status"] == "succeeded" else "not_completed",
        }, indent=2))
        if state["status"] != "succeeded":
            raise SystemExit(2)


if __name__ == "__main__":
    main()
