"""
RRF hybrid retrieval (Cormack et al. 2009 + HINDSIGHT 4-channel application).

Pure Python, no external deps. The cross-encoder reranker is a stub that
swaps in a real model at a documented seam.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Tuple


DEFAULT_K = 60  # RRF constant per Cormack et al. 2009


def rrf_fuse(channels: Dict[str, List[str]], k: int = DEFAULT_K) -> List[Tuple[str, float]]:
    """Reciprocal Rank Fusion.

    channels: {channel_name: [doc_id_ranked_1, doc_id_ranked_2, ...], ...}
    Returns: [(doc_id, fusion_score), ...] sorted descending by fusion_score.

    Formula: RRF(doc) = sum over channels c of: 1 / (k + rank_c(doc))
    where rank is 1-indexed within each channel.
    Items missing from a channel contribute 0 from that channel.
    """
    # RRF constant must be non-negative: with 1-indexed ranks the smallest
    # denominator is k+1, so k < 0 makes k+rank hit 0 (ZeroDivisionError) or go
    # negative (nonsensical scores). Standard is k=60 (Cormack et al. 2009).
    if k < 0:
        raise ValueError(f"RRF constant k must be >= 0, got {k}")
    scores: Dict[str, float] = defaultdict(float)
    for ranking in channels.values():
        for rank_zero, doc_id in enumerate(ranking):
            rank = rank_zero + 1  # 1-indexed per RRF spec
            scores[doc_id] += 1.0 / (k + rank)
    fused = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return fused


def cross_encoder_rerank(
    candidates: List[Tuple[str, float]],
    query: str,
    score_fn: Optional[Callable[[str, str], float]] = None,
    metadata: Optional[Dict[str, str]] = None,
) -> List[Tuple[str, float, float]]:
    """Rerank candidates by a cross-encoder score.

    candidates: [(doc_id, fusion_score), ...]
    Returns: [(doc_id, fusion_score, rerank_score), ...] sorted by rerank_score desc.

    `score_fn(query, doc_id)` returns a relevance score. If None, a heuristic
    using metadata-stored text falls back; if metadata is empty, identity
    (rerank_score = fusion_score).

    Production: swap in a real cross-encoder (ms-marco-MiniLM, bge-reranker,
    etc.). The signature here is the seam.
    """
    metadata = metadata or {}
    if score_fn is None:
        # Fallback: substring-match score against doc text in metadata
        def _heuristic(q: str, doc_id: str) -> float:
            text = metadata.get(doc_id, doc_id).lower()
            q_lower = q.lower()
            q_tokens = set(q_lower.split())
            text_tokens = set(text.split())
            if not q_tokens:
                return 0.0
            overlap = len(q_tokens & text_tokens) / len(q_tokens)
            return overlap

        score_fn = _heuristic
    reranked = [(doc_id, fusion_score, score_fn(query, doc_id))
                for doc_id, fusion_score in candidates]
    reranked.sort(key=lambda x: x[2], reverse=True)
    return reranked


def token_budget_filter(
    items: List[Tuple[str, float, float]],
    get_tokens: Callable[[str], int],
    budget: int,
) -> List[Dict[str, Any]]:
    """Filter items so cumulative token count is under budget.

    Walks items in order (caller should pre-sort by importance).
    Returns: [{doc_id, fusion_score, rerank_score, token_count}, ...]
    """
    out = []
    used = 0
    for doc_id, fusion_score, rerank_score in items:
        n = get_tokens(doc_id)
        if used + n > budget:
            continue
        out.append({
            "doc_id": doc_id,
            "fusion_score": fusion_score,
            "rerank_score": rerank_score,
            "token_count": n,
        })
        used += n
    return out


def hybrid_retrieve(
    query: str,
    channel_callables: Dict[str, Callable[[str], List[str]]],
    k: int = DEFAULT_K,
    top_n_for_rerank: int = 20,
    final_budget: int = 4000,
    get_tokens: Optional[Callable[[str], int]] = None,
    rerank_score_fn: Optional[Callable[[str, str], float]] = None,
    metadata: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """End-to-end pipeline. Each channel_callable takes the query and
    returns a list of doc_ids in rank order.

    Returns final filtered list per `token_budget_filter`.
    """
    if get_tokens is None:
        get_tokens = lambda doc_id: 250  # default chunk-token estimate
    rankings = {name: fn(query) for name, fn in channel_callables.items()}
    fused = rrf_fuse(rankings, k=k)
    top = fused[:top_n_for_rerank]
    reranked = cross_encoder_rerank(top, query, score_fn=rerank_score_fn, metadata=metadata)
    return token_budget_filter(reranked, get_tokens, final_budget)
