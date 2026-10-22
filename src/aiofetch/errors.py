
class FetchError(Exception):
    transient = False
    def __init__(self, url, reason):
        super().__init__(f"{url}: {reason}")
        self.url = url
        self.reason = reason

class TransientError(FetchError):
    transient = True
    def __init__(self, url, reason, retry_after=None):
        super().__init__(url, reason)
        self.retry_after = retry_after

class PermanentError(FetchError):
    transient = False

def is_transient_status(status, body=""):
    if "insufficient_quota" in body:
        return False
    return status in {408, 409, 429} or status >= 500

def error_for(url, response):
    problem = f"{response.status_code} {response.reason_phrase}"
    if is_transient_status(response.status_code, response.text):
        return TransientError(url, problem)
    return PermanentError(url, problem)
