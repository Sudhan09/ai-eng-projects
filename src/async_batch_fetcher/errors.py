"""The failure family: every error says whether a retry could help."""


class FetchError(Exception):
    """A job failed. `job_id` says which one, and `reason` why."""

    transient: bool = False

    def __init__(self, job_id: int, reason: str) -> None:
        super().__init__(f"job {job_id}: {reason}")
        self.job_id = job_id
        self.reason = reason


class TransientError(FetchError):
    """Worth retrying later: the server was busy (503) or too slow (timeout)."""

    transient = True


class PermanentError(FetchError):
    """Never worth retrying: the job doesn't exist (404)."""

    transient = False
