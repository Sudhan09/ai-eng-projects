async def frames(source, prompt, max_tokens):
    sent = 0
    async for token in source.stream(prompt, max_tokens):
        sent += 1
        yield {"event": "token", "id": str(sent), "data": token}
    yield {"event": "done", "data": "[DONE]"}