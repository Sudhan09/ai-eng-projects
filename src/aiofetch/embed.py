import numpy as np


def to_matrix(vectors):
    rows = []
    for vector in vectors:
        rows.append(np.asarray(vector, dtype=np.float32))
    return np.vstack(rows)


def cosine_matrix(matrix):
    lengths = np.linalg.norm(matrix, axis=1, keepdims=True)
    unit = matrix / lengths
    return unit @ unit.T
