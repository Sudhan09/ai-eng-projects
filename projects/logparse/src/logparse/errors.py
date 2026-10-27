class ParseError(ValueError):
    transient: bool = False


class MalformedLineError(ParseError):
    pass


class UnknownLevelError(ParseError):
    pass
