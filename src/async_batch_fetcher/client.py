"""The client half of the protocol: one connection, one job."""

import asyncio

from async_batch_fetcher.errors import PermanentError, TransientError

HOST = "127.0.0.1"


async def fetch(job_id: int, port: int, host: str = HOST) -> str:
    reader, writer = await asyncio.open_connection(host, port)
    try:
        writer.write(f"GET {job_id}\n".encode())
        await writer.drain()
        line = (await reader.readline()).decode()
        words = line.split()
        if words[0] == "OK":
            return words[2]
        elif words[1] == "404":
            raise PermanentError(job_id, words[1])
        else:
            raise TransientError(job_id, words[1])
    finally:
        writer.close()
        await writer.wait_closed()
