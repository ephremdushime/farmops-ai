import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError


def main():
    load_dotenv(Path(__file__).resolve().with_name(".env"), override=False)
    api_key = os.getenv("MODEL_API_KEY")
    if not api_key:
        print("Meta API check skipped: MODEL_API_KEY is not configured.")
        return 2

    client = OpenAI(
        base_url="https://api.meta.ai/v1",
        api_key=api_key,
        timeout=60.0,
        max_retries=0,
    )
    try:
        response = client.responses.create(
            model=os.getenv("META_MODEL_ID", "muse-spark-1.3"),
            input="Reply with exactly: FarmOps API check passed.",
        )
    except OpenAIError as error:
        status = getattr(error, "status_code", None)
        print(f"Meta API check failed: {type(error).__name__}; HTTP status={status}.")
        return 1

    if response.output_text.strip() != "FarmOps API check passed.":
        print("Meta API responded, but the smoke-test response did not match.")
        return 1
    print(f"Meta API check succeeded. Model: {response.model}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
