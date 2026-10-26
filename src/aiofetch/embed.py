import numpy as np
from numpy.typing import NDArray


def to_matrix(vectors: list[list[float]]) -> NDArray[np.float32]:
    rows: list[NDArray[np.float32]] = []
    for vector in vectors:
        rows.append(np.asarray(vector, dtype=np.float32))
    return np.vstack(rows)


def cosine_matrix(matrix: NDArray[np.float32]) -> NDArray[np.float32]:
    lengths = np.linalg.norm(matrix, axis=1, keepdims=True)
    unit = matrix / lengths
    return np.asarray(unit @ unit.T, dtype=np.float32)
