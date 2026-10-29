import argparse
import asyncio
import json
import sys
from .config import get_settings
from .nebius import IntegrationError, NemotronClient, SourceInput


async def run(command):
    client = NemotronClient(get_settings())
    try:
        if command == "models":
            models = await client.list_models()
            print(json.dumps({"available_nemotron_models": models}, indent=2))
        else:
            result = await client.extract_requirements([SourceInput(
                source_id="sample-page-1",
                text="The bidder must provide a manufacturer authorization letter naming the bidder and the proposed laptop model.",
            )])
            if not result.batch.requirements:
                raise IntegrationError("Connectivity succeeded, but the smoke test extracted no requirements.")
            print(result.model_dump_json(indent=2))
    finally:
        await client.close()


def main():
    parser = argparse.ArgumentParser(description="Token Factory integration checks (live API calls)")
    parser.add_argument("command", choices=["models", "smoke"])
    args = parser.parse_args()
    try:
        asyncio.run(run(args.command))
    except IntegrationError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
