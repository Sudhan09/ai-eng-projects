import asyncio

import numpy as np

from aiofetch.client import AiofetchClient
from aiofetch.embed import cosine_matrix, to_matrix
from aiofetch.flaky import FlakyAPI


def test_fetched_embeddings_stack_into_float32_rows_with_self_similarity_one():
    texts = ["refund", "invoice", "shipping", "refund"]

    async def main():
        transport = FlakyAPI()
        async with AiofetchClient("http://api.test", transport=transport) as client:
            return await client.fetch_many([f"/embed/{t}" for t in texts])

    vectors = [r.value["vector"] for r in asyncio.run(main())]
    matrix = to_matrix(vectors)
    assert matrix.dtype == np.float32 and matrix.shape == (4, 8)
    sims = cosine_matrix(matrix)
    assert np.allclose(np.diag(sims), 1.0, atol=1e-6)
    assert np.isclose(sims[0, 3], 1.0, atol=1e-6)  # same text, same vector
