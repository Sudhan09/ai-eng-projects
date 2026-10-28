"""Your typed words, for the drivers: what to ask for, and what the fake server should answer."""


def scripted(text, path_of=lambda word: word):
    """"/v2/items/7 /items/1=503,503,200" -> (["/v2/items/7", "/items/1"], {"/items/1": [503, 503, 200]}).

    After "=", the fake's answers for that path, in order: status codes, or a word the fake knows ("timeout").
    """
    asks, script = [], {}
    for word in text.split():
        ask, _, answers = word.partition("=")
        asks.append(ask)
        if answers:
            script[path_of(ask)] = [int(a) if a.isdigit() else a for a in answers.split(",") if a]
    return asks, script
