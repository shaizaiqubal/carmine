import argparse
import os
import platform
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

import torch

from app.config import Settings
from app.llm.configuration import LLMConfig


def token_lengths(tokenizer, texts: list[str]) -> tuple[float, int]:
    encoded = tokenizer(
        texts,
        add_special_tokens=True,
        padding=False,
        truncation=False,
        return_attention_mask=True,
    )
    lengths = [len(ids) for ids in encoded["input_ids"]]
    return sum(lengths) / len(lengths), max(lengths)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunks", type=int, default=300)
    parser.add_argument("--batch-size", type=int, default=int(os.getenv("EMBEDDING_BATCH_SIZE", "32")))
    parser.add_argument("--max-seq-length", type=int, default=int(os.getenv("EMBEDDING_MAX_SEQ_LENGTH", "128")))
    parser.add_argument("--threads", type=int, default=int(os.getenv("EMBEDDING_THREADS", "2")))
    args = parser.parse_args()

    torch.set_num_threads(args.threads)
    try:
        torch.set_num_interop_threads(max(1, min(args.threads, 2)))
    except RuntimeError:
        pass

    config = LLMConfig.load(settings=Settings(turso_database_url="", turso_auth_token=""))
    device = "cpu"
    chunks = [
        f"Sample startup research chunk {index}. It describes a customer, market, or business model assumption."
        for index in range(args.chunks)
    ]

    from sentence_transformers import SentenceTransformer

    load_started = time.perf_counter()
    model = SentenceTransformer(config.embedding_model, revision=config.embedding_revision, device=device)
    model.max_seq_length = args.max_seq_length
    load_seconds = time.perf_counter() - load_started

    average_tokens, max_tokens = token_lengths(model.tokenizer, chunks)
    warmup_count = min(args.batch_size, len(chunks))
    model.encode(
        chunks[:warmup_count],
        batch_size=args.batch_size,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )

    encode_started = time.perf_counter()
    model.encode(
        chunks,
        batch_size=args.batch_size,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    encode_seconds = time.perf_counter() - encode_started

    print(f"where={platform.platform()} python={platform.python_version()}")
    print(f"device={device} torch={torch.__version__} cuda_available={torch.cuda.is_available()}")
    print(f"model={config.embedding_model} revision={config.embedding_revision} dimensions={config.embedding_dim}")
    print(f"chunks={len(chunks)} batch_size={args.batch_size} max_seq_length={args.max_seq_length} threads={torch.get_num_threads()}")
    print(f"avg_chunk_tokens={average_tokens:.2f} max_chunk_tokens={max_tokens}")
    print(f"model_load_seconds={load_seconds:.3f}")
    print(f"warmup_chunks={warmup_count} warmup_excluded=true")
    print(f"encode_seconds={encode_seconds:.3f} chunks_per_second={len(chunks) / max(encode_seconds, 1e-9):.2f}")


if __name__ == "__main__":
    main()
