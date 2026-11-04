"""A small SSE reader: a frame is dispatched only at a blank line, as the spec says.

It keeps one value per field, which is enough for one-line tokens; the spec joins
repeated `data:` lines with a newline.
"""


def frames(body):
    """The frames in an SSE body, as dicts of field -> value. Comment lines are skipped."""
    out, fields = [], {}
    for line in body.replace("\r\n", "\n").split("\n")[
        :-1
    ]:  # after the last \n: not a line yet
        if line == "":  # the blank line ends a frame
            if fields:
                out.append(fields)
            fields = {}
        elif not line.startswith(":"):  # ": ping" and other comments carry no data
            name, _, value = line.partition(":")
            fields[name] = value.removeprefix(
                " "
            )  # one space after the colon is dropped
    return out  # a frame with no blank line after it is never dispatched
