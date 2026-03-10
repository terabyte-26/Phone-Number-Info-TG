"""Quick script to inspect Groq rate-limit headers and usage for a single key."""

import sys
from groq import Groq

def main():
    if len(sys.argv) < 2:
        print("Usage: python test_groq_key_usage.py <GROQ_API_KEY>")
        sys.exit(1)

    api_key = sys.argv[1]
    client = Groq(api_key=api_key)

    try:
        raw = client.chat.completions.with_raw_response.create(
            messages=[{"role": "user", "content": "hi"}],
            model="llama-3.3-70b-versatile",
            max_tokens=1,
        )
    except Exception as e:
        print(f"API call failed: {e}")
        sys.exit(1)

    print("=== Rate Limit Headers ===")
    for name, value in sorted(raw.headers.items()):
        if "ratelimit" in name.lower():
            print(f"  {name}: {value}")

    response = raw.parse()
    usage = response.usage

    print("\n=== Token Usage (this request) ===")
    print(f"  prompt_tokens:     {usage.prompt_tokens}")
    print(f"  completion_tokens: {usage.completion_tokens}")
    print(f"  total_tokens:      {usage.total_tokens}")

    print("\n=== Timing ===")
    print(f"  queue_time:        {usage.queue_time:.4f}s")
    print(f"  prompt_time:       {usage.prompt_time:.4f}s")
    print(f"  completion_time:   {usage.completion_time:.4f}s")
    print(f"  total_time:        {usage.total_time:.4f}s")

    # Derived info
    limit_tok = int(raw.headers.get("x-ratelimit-limit-tokens", 0))
    remain_tok = int(raw.headers.get("x-ratelimit-remaining-tokens", 0))
    limit_req = int(raw.headers.get("x-ratelimit-limit-requests", 0))
    remain_req = int(raw.headers.get("x-ratelimit-remaining-requests", 0))

    print("\n=== Summary ===")
    print(f"  TPM  (tokens/min):   {limit_tok - remain_tok} / {limit_tok} used")
    print(f"  RPD  (requests/day): {limit_req - remain_req} / {limit_req} used")
    print(f"  TPD  (tokens/day):   not available in headers (only shown in 429 errors)")


if __name__ == "__main__":
    main()
