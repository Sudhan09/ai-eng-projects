import asyncio
import json
import sys

from pydantic import ValidationError

from .client import AiofetchClient
from .settings import get_settings


async def main(paths: list[str]) -> int:
    try:
        settings = get_settings()
    except ValidationError as exc:
        message = " ".join(str(exc).split())
        print(f"aiofetch: bad config: {message}", file=sys.stderr)
        return 2
    async with AiofetchClient.from_settings(settings) as client:
        results = await client.fetch_many(paths)
    all_ok = True
    for result in results:
        print(json.dumps(result.to_row()))
        if not result.ok:
            all_ok = False
    if all_ok:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
