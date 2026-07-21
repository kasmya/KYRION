"""
collab_filter.py

A lightweight collaborative‑filtering recommender system built with the
standard scientific Python stack. It provides utilities to:

* Build a user‑item rating matrix from a ``pandas.DataFrame``.
* Compute pairwise user cosine similarity.
* Generate top‑N item recommendations for a given user.
* Evaluate recommendations using precision@k, recall@k and MAP@k.

The implementation follows security best practices by validating inputs,
avoiding execution of untrusted code and handling edge cases explicitly.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple, Optional

import numpy as np
import pandas as pd
from scipy.spatial.distance import cdist

__all__ = [
    "build_user_item_matrix",
    "compute_user_similarity",
    "recommend_top_n",
    "evaluate_recommendations",
]

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def _validate_dataframe(
    df: pd.DataFrame,
    required_columns: List[str],
    context: str = "DataFrame",
) -> None:
    """
    Validate that ``df`` contains all ``required_columns``.

    Raises
    ------
    TypeError
        If ``df`` is not a ``pandas.DataFrame``.
    ValueError
        If any required column is missing.
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"{context} must be a pandas.DataFrame, got {type(df)}.")
    missing = [c for c in required_columns if c not in df.columns]
    if missing:
        raise ValueError(f"{context} is missing required columns: {missing}.")


def build_user_item_matrix(
    ratings: pd.DataFrame,
    user_col: str = "user_id",
    item_col: str = "item_id",
    rating_col: str = "rating",
) -> pd.DataFrame:
    """
    Construct a user‑item matrix (users as rows, items as columns).

    Parameters
    ----------
    ratings : pd.DataFrame
        Long‑format rating data.
    user_col, item_col, rating_col : str
        Column names for user identifier, item identifier and rating value.

    Returns
    -------
    pd.DataFrame
        A matrix where missing entries are filled with ``0`` (interpreted
        as “no interaction”.

    Raises
    ------
    TypeError, ValueError
        Propagated from internal validation.
    """
    _validate_dataframe(
        ratings,
        required_columns=[user_col, item_col, rating_col],
        context="ratings DataFrame",
    )
    try:
        matrix = (
            ratings.pivot_table(
                index=user_col,
                columns=item_col,
                values=rating_col,
                aggfunc="mean",
                fill_value=0,
            )
            .astype(float)
        )
    except Exception as exc:
        logger.exception("Failed to build user‑item matrix.")
        raise RuntimeError("Could not construct user‑item matrix.") from exc
    return matrix


def compute_user_similarity(user_item_matrix: pd.DataFrame) -> pd.DataFrame:
    """
    Compute cosine similarity between users.

    Cosine similarity is defined as ``1 - cosine_distance``. Users with no
    interactions are excluded from similarity computation to avoid division
    by zero.

    Parameters
    ----------
    user_item_matrix : pd.DataFrame
        Matrix returned by :func:`build_user_item_matrix`.

    Returns
    -------
    pd.DataFrame
        Symmetric DataFrame where entry ``(u, v)`` is the similarity between
        users ``u`` and ``v``.

    Raises
    ------
    ValueError
        If the matrix contains no non‑zero rows.
    """
    if not isinstance(user_item_matrix, pd.DataFrame):
        raise TypeError("user_item_matrix must be a pandas.DataFrame.")
    if user_item_matrix.shape[0] == 0:
        raise ValueError("user_item_matrix must contain at least one user.")
    # Convert to numpy for distance calculation
    matrix_np = user_item_matrix.values
    # Identify rows with at least one non‑zero entry
    non_empty = np.any(matrix_np != 0, axis=1)
    if not np.any(non_empty):
        raise ValueError("All rows in user_item_matrix are empty.")
    filtered = matrix_np[non_empty]
    # Compute cosine distance, then similarity
    distance = cdist(filtered, filtered, metric="cosine")
    similarity = 1.0 - distance
    # Re‑inject empty rows as zeros to keep original indexing
    full_similarity = np.zeros((user_item_matrix.shape[0],) * 2, dtype=float)
    idx = np.where(non_empty)[0]
    full_similarity[np.ix_(idx, idx)] = similarity
    # Build DataFrame with proper labels
    sim_df = pd.DataFrame(
        full_similarity,
        index=user_item_matrix.index,
        columns=user_item_matrix.index,
    )
    return sim_df


def recommend_top_n(
    user_id: Any,
    user_item_matrix: pd.DataFrame,
    user_similarity: pd.DataFrame,
    n: int = 10,
) -> List[Tuple[Any, float]]:
    """
    Generate top‑N item recommendations for ``user_id`` using user‑based
    collaborative filtering.

    The predicted preference for an unseen item is the weighted average of
    ratings from similar users, where weights are the cosine similarities.

    Parameters
    ----------
    user_id : Any
        Identifier of the target user (must exist in the matrix index).
    user_item_matrix : pd.DataFrame
        User‑item rating matrix.
    user_similarity : pd.DataFrame
        Pairwise user similarity matrix.
    n : int, default 10
        Number of recommendations to return.

    Returns
    -------
    List[Tuple[Any, float]]
        List of ``(item_id, predicted_score)`` sorted by descending score.

    Raises
    ------
    KeyError
        If ``user_id`` is not present in the matrix.
    ValueError
        If ``n`` is not a positive integer.
    """
    if n <= 0:
        raise ValueError("Parameter n must be a positive integer.")
    if user_id not in user_item_matrix.index:
        raise KeyError(f"user_id {user_id!r} not found in user_item_matrix.")
    # Extract similarity vector for the target user
    sim_vec = user_similarity.loc[user_id].values.reshape(1, -1)  # shape (1, users)
    # Compute weighted sum of ratings
    weighted_ratings = sim_vec @ user_item_matrix.values  # shape (1, items)
    # Normalise by sum of absolute similarities to avoid bias from zero‑sum rows
    sim_sum = np.abs(sim_vec).sum()
    if sim_sum == 0:
        logger.warning("User %s has zero similarity to all others.", user_id)
        predicted = np.zeros(user_item_matrix.shape[1])
    else:
        predicted = (weighted_ratings / sim_sum).flatten()
    # Exclude items already rated by the user
    user_rated = user_item_matrix.loc[user_id] != 0
    predicted[user_rated.values] = -np.inf  # mask known items
    # Get top‑N indices
    top_idx = np.argpartition(-predicted, range(min(n, len(predicted))))[:n]
    top_scores = predicted[top_idx]
    # Sort the top results
    sorted_order = np.argsort(-top_scores)
    top_idx = top_idx[sorted_order]
    top_scores = top_scores[sorted_order]
    # Map column positions back to item identifiers
    item_ids = user_item_matrix.columns[top_idx]
    recommendations = list(zip(item_ids, top_scores.astype(float)))
    return recommendations


def evaluate_recommendations(
    recommendations: Dict[Any, List[Any]],
    test_interactions: pd.DataFrame,
    user_col: str = "user_id",
    item_col: str = "item_id",
    k: int = 10,
) -> Dict[str, float]:
    """
    Evaluate recommendation lists against a held‑out test set.

    Computes Precision@k, Recall@k and MAP@k (Mean Average Precision).

    Parameters
    ----------
    recommendations : dict
        Mapping ``user_id -> list of recommended item_ids`` (ordered).
    test_interactions : pd.DataFrame
        Ground‑truth interactions (only positive feedback considered).
    user_col, item_col : str
        Column names for user and item identifiers in ``test_interactions``.
    k : int, default 10
        Cut‑off rank for the metrics.

    Returns
    -------
    dict
        Dictionary with keys ``precision``, ``recall`` and ``map`` containing
        the respective scores (float).

    Raises
    ------
    TypeError, ValueError
        If inputs are malformed.
    """
    _validate_dataframe(
        test_interactions,
        required_columns=[user_col, item_col],
        context="test_interactions DataFrame",
    )
    if k <= 0:
        raise ValueError("Parameter k must be a positive integer.")
    # Build ground‑truth lookup
    gt: Dict[Any, set] = {}
    for uid, iid in zip(
        test_interactions[user_col], test_interactions[item_col]
    ):
        gt.setdefault(uid, set()).add(iid)

    precisions: List[float] = []
    recalls: List[float] = []
    average_precisions: List[float] = []

    for user, rec_items in recommendations.items():
        relevant = gt.get(user, set())
        if not relevant:
            continue  # No ground‑truth for this user; skip
        rec_at_k = rec_items[:k]
        hit_set = set(rec_at_k) & relevant
        precision = len(hit_set) / min(k, len(rec_at_k)) if rec_at_k else 0.0
        recall = len(hit_set) / len(relevant)
        precisions.append(precision)
        recalls.append(recall)

        # MAP computation
        hit_count = 0
        sum_precisions = 0.0
        for rank, item in enumerate(rec_at_k, start=1):
            if item in relevant:
                hit_count += 1
                sum_precisions += hit_count / rank
        avg_prec = sum_precisions / len(relevant) if relevant else 0.0
        average_precisions.append(avg_prec)

    if not precisions:
        raise ValueError("No overlapping users between recommendations and test set.")

    metrics = {
        "precision": float(np.mean(precisions)),
        "recall": float(np.mean(recalls)),
        "map": float(np.mean(average_precisions)),
    }
    return metrics