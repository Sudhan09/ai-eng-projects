from dataclasses import dataclass
from enum import Enum

from logparse.errors import MalformedLineError, UnknownLevelError


class LogLevel(Enum):
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50


@dataclass(frozen=True, slots=True)
class LogRecord:
    timestamp: str
    level: LogLevel
    component: str
    message: str

    def __str__(self) -> str:
        return f"{self.level.name} {self.component}: {self.message}"


def parse_line(line: str) -> LogRecord:
    try:
        timestamp, level, rest = line.split(" ", 2)
        component, message = rest.split(": ", 1)
    except ValueError as exc:
        raise MalformedLineError(f"bad shape: {line}") from exc
    try:
        lvl = LogLevel[level]
    except KeyError as exc:
        raise UnknownLevelError(f"unknown level: {level}") from exc
    return LogRecord(timestamp, lvl, component, message)
