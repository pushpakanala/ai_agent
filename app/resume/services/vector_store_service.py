import faiss
import numpy as np


def chunk_resume(
    text: str,
    chunk_size: int = 500,
):

    words = text.split()

    chunks = []

    for i in range(
        0,
        len(words),
        chunk_size,
    ):

        chunks.append(
            " ".join(
                words[i:i + chunk_size]
            )
        )

    return chunks


def build_faiss_index(
    embeddings,
):

    dimension = len(
        embeddings[0]
    )

    index = faiss.IndexFlatL2(
        dimension
    )

    vectors = np.array(
        embeddings,
        dtype=np.float32,
    )

    index.add(vectors)

    return index