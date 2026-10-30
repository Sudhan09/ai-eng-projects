import random

WORDS = (
    "the", "model", "streams", "each", "token", "as", "soon", "as", "it", "is", "ready",
    "so", "you", "see", "words", "arrive", "one", "by", "one", "instead", "of", "waiting",
) 

def token_at(prompt, index):
    return " " + random.Random(f"{prompt}|{index}").choice(WORDS)