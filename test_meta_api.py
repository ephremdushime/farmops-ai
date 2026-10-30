import getpass
from openai import OpenAI, AuthenticationError, APIError

api_key = getpass.getpass("Paste your NEW Meta API key (hidden): ").strip()

client = OpenAI(
    base_url="https://api.meta.ai/v1",
    api_key=api_key,
    timeout=60.0,
    max_retries=0,
)

try:
    response = client.responses.create(
        model="muse-spark-1.3",
        input="Reply with exactly: FarmOps AI connection successful."
    )

    print("\nAPI CONNECTION: SUCCESS")
    print("MODEL:", response.model)
    print("RESPONSE:", response.output_text)

except AuthenticationError:
    print("\n401: Meta rejected the API key.")
    print("Check the key in the dashboard and its authorization.")

except APIError as error:
    print("\nAPI ERROR:", error.status_code)
    print(error.message)

except Exception as error:
    print("\nOTHER ERROR:", type(error).__name__)
    print(str(error))