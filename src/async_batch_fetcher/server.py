"""A mock service that speaks the one-line protocol: GET <id> -> OK/ERR."""

import asyncio
import contextlib

HOST = "127.0.0.1"


class MockServer:
    def __init__(
        self,
        delay: float = 0.05,
        fail_every: int = 0,
        slow: frozenset[int] = frozenset(),
        slow_delay: float = 5.0,
    ) -> None:
        self.delay = delay
        self.fail_every = fail_every
        self.slow = slow
        self.slow_delay = slow_delay
        self.in_flight = 0
        self.peak = 0
        self.served = 0
        self.server: asyncio.Server | None = None

    def reply(self, job_id: int) -> str:
        """503 for jobs 9, 29, 49...; 404 for 19, 39, 59... when fail_every=10."""
        n = self.fail_every
        if n and job_id % n == n - 1:
            return "ERR 503" if (job_id // n) % 2 == 0 else "ERR 404"
        return f"OK {job_id} payload-{job_id}"

    async def handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self.in_flight += 1
        self.peak = max(self.peak, self.in_flight)
        try:
            words = (await reader.readline()).decode().split()
            if (
                len(words) == 2 and words[1].isdigit()
            ):  # a client that left sent nothing
                job_id = int(words[1])
                await asyncio.sleep(
                    self.slow_delay if job_id in self.slow else self.delay
                )
                writer.write((self.reply(job_id) + "\n").encode())
                await writer.drain()
                self.served += 1
        except ConnectionError:
            pass  # the client hung up before the answer: nothing left to send
        finally:
            self.in_flight -= 1
            writer.close()
            with contextlib.suppress(ConnectionError):
                await writer.wait_closed()

    async def start(self) -> int:
        self.server = await asyncio.start_server(self.handle, HOST, 0, backlog=1024)
        return self.server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
            self.server = None

    async def __aenter__(self) -> "MockServer":
        await self.start()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.stop()

    @property
    def port(self) -> int:
        assert self.server is not None, "server not started"
        return self.server.sockets[0].getsockname()[1]
