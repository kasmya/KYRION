"""
collaborative_filtering.py

A minimal collaborative‑filtering recommendation engine using user‑based cosine similarity.
The module provides utilities to:

* Build a user‑item rating matrix from a long‑format DataFrame.
* Compute pairwise cosine similarity between users.
* Generate top‑N item recommendations for a given user.
* Evaluate recommendation lists with precision@k, recall@k and MAP@k.

Only the Python standard library together with the widely‑used packages ``pandas``,
``numpy`` and ``scipy`` are required.

Security considerations:
* All public functions validate their inputs and raise explicit exceptions.
* No execution of arbitrary code (e.g., ``eval``) is performed.
* Data‑size checks prevent unreasonable memory consumption.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import numpy as np
import pandas as pd
from scipy.spatial.distance import cosine

__all__ = [
    "build_user_item_matrix",
    "compute_user_cosine_similarity",
    "get_top_n_recommendations",
    "evaluate_recommendations",
]

# --------------------------------------------------------------------------- #
# Helper functions
# --------------------------------------------------------------------------- #


def _validate_dataframe(df: pd.DataFrame, required_columns: Sequence[str]) -> None:
    """
    Validate that ``df`` is a pandas DataFrame containing the required columns.

    Raises:
        TypeError: If ``df`` is not a DataFrame.
        ValueError: If any required column is missing.
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError("Input must be a pandas DataFrame.")
    missing = set(required_columns) - set(df.columns)
    if missing:
        raise ValueError(f"DataFrame is missing required columns: {missing}")


def _ensure_non_negative_int(value: Any, name: str) -> int:
    """
    Convert ``value`` to an int and ensure it is non‑negative.

    Raises:
        TypeError: If conversion fails.
        ValueError: If the integer is negative.
    """
    try:
        ivalue = int(value)
    except Exception as exc:
        raise TypeError(f"{name} must be an integer.") from exc
    if ivalue < 0:
        raise ValueError(f"{name} must be non‑negative.")
    return ivalue


# --------------------------------------------------------------------------- #
# Core functionality
# --------------------------------------------------------------------------- #


def build_user_item_matrix(
    ratings: pd.DataFrame,
    user_col: str = "user_id",
    item_col: str = "item_id",
    rating_col: str = "rating",
) -> pd.DataFrame:
    """
    Construct a user‑item rating matrix where rows are users, columns are items,
    and cell values are the corresponding rating (or 0 if missing).

    Parameters
    ----------
    ratings : pd.DataFrame
        Long‑format table with at least ``user_col``, ``item_col`` and ``rating_col``.
    user_col, item_col, rating_col : str, optional
        Column names in ``ratings`` for user identifiers, item identifiers and
        rating values respectively.

    Returns
    -------
    pd.DataFrame
        A matrix with users as the index and items as the columns.

    Raises
    ------
    ValueError
        If the input DataFrame is empty.
    """
    _validate_dataframe(ratings, [user_col, item_col, rating_col])

    if ratings.empty:
        raise ValueError("Ratings DataFrame is empty.")

    # Pivot to wide format; missing entries become NaN which we replace by 0.
    try:
        matrix = ratings.pivot_table(
            index=user_col,
            columns=item_col,
            values=rating_col,
            aggfunc="mean",
            fill_value=0,
        )
    except Exception as exc:
        raise ValueError("Failed to pivot ratings into a matrix.") from exc

    # Ensure numeric dtype
    matrix = matrix.astype(float)

    # Guard against extremely large matrices (simple heuristic)
    max_cells = 1_000_000
    if matrix.shape[0] * matrix.shape[1] > max_cells:
        raise MemoryError(
            f"Resulting matrix would have >{max_cells} cells; aborting to avoid OOM."
        )

    return matrix


def compute_user_cosine_similarity(matrix: pd.DataFrame) -> pd.DataFrame:
    """
    Compute pairwise cosine similarity between users based on the rating matrix.

    Parameters
    ----------
    matrix : pd.DataFrame
        User‑item matrix as produced by :func:`build_user_item_matrix`.

    Returns
    -------
    pd.DataFrame
        Symmetric DataFrame where entry (u, v) is the cosine similarity between
        users ``u`` and ``v``. Diagonal entries are 1.0.

    Raises
    ------
    ValueError
        If the matrix has no rows or columns.
    """
    if matrix.empty or matrix.shape[1] == 0:
        raise ValueError("Rating matrix must contain at least one user and one item.")

    # Normalise rows to unit vectors; rows with zero norm remain zero.
    norms = np.linalg.norm(matrix.values, axis=1, keepdims=True)
    # Avoid division by zero
    safe_norms = np.where(norms == 0, 1, norms)
    normalized = matrix.values / safe_norms

    # Cosine similarity = dot product of normalized vectors
    similarity = np.dot(normalized, normalized.T)

    # Clip possible numerical errors
    similarity = np.clip(similarity, -1.0, 1.0)

    sim_df = pd.DataFrame(
        similarity, index=matrix.index, columns=matrix.index, dtype=float
    )
    # Force diagonal to 1.0
    np.fill_diagonal(sim_df.values, 1.0)
    return sim_df


def get_top_n_recommendations(
    user_id: Any,
    matrix: pd.DataFrame,
    similarity: pd.DataFrame,
    n: int = 10,
    min_similarity: float = 0.0,
) -> List[Tuple[Any, float]]:
    """
    Generate top‑N item recommendations for ``user_id`` using weighted average
    of ratings from similar users.

    Parameters
    ----------
    user_id : Any
        Identifier of the target user (must exist in ``matrix`` index).
    matrix : pd.DataFrame
        User‑item rating matrix.
    similarity : pd.DataFrame
        User‑user similarity matrix (output of ``compute_user_cosine_similarity``).
    n : int, optional
        Number of items to recommend (default 10). Must be positive.
    min_similarity : float, optional
        Minimum similarity for a neighbor to be considered (default 0.0).

    Returns
    -------
    List[Tuple[Any, float]]
        List of ``(item_id, predicted_score)`` sorted by descending score.

    Raises
    ------
    KeyError
        If ``user_id`` is not present in ``matrix``.
    ValueError
        If ``n`` is not a positive integer.
    """
    n = _ensure_non_negative_int(n, "n")
    if n == 0:
        return []

    if user_id not in matrix.index:
        raise KeyError(f"User {user_id!r} not found in rating matrix.")

    # Retrieve similarity scores for the target user, exclude self
    user_sim = similarity.loc[user_id].drop(labels=user_id)

    # Filter neighbors by similarity threshold
    eligible = user_sim[user_sim >= min_similarity]
    if eligible.empty:
        # No similar users; return empty list
        return []

    # Weighted sum of neighbor ratings
    neighbor_ratings = matrix.loc[eligible.index]
    weights = eligible.values[:, np.newaxis]  # column vector
    weighted_sum = np.dot(weights.T, neighbor_ratings.values)
    weight_total = np.sum(np.abs(weights), axis=0)

    # Avoid division by zero for items no neighbor rated
    with np.errstate(divide="ignore", invalid="ignore"):
        scores = np.where(weight_total != 0, weighted_sum / weight_total, 0)

    # Remove items already rated by the target user
    already_rated = matrix.loc[user_id] != 0
    scores[already_rated.values] = -np.inf

    # Get top N indices
    top_idx = np.argpartition(-scores, range(min(n, len(scores))))[:n]
    top_scores = scores[top_idx]
    sorted_order = np.argsort(-top_scores)
    top_idx = top_idx[sorted_order]
    top_scores = top_scores[sorted_order]

    recommendations = [
        (matrix.columns[i], float(top_scores[pos]))
        for pos, i in enumerate(top_idx)
        if top_scores[pos] != -np.inf
    ]

    return recommendations


def evaluate_recommendations(
    recommendations: Dict[Any, List[Any]],
    ground_truth: Dict[Any, List[Any]],
    k: int = 10,
) -> Dict[str, float]:
    """
    Compute precision@k, recall@k and mean average precision (MAP)@k for a set of
    recommendation lists.

    Parameters
    ----------
    recommendations : dict
        Mapping from user identifier to an ordered list of recommended item IDs.
    ground_truth : dict
        Mapping from user identifier to the list of relevant (e.g., purchased) item IDs.
    k : int, optional
        Cut‑off rank for the metrics (default 10). Must be positive.

    Returns
    -------
    dict
        Dictionary with keys ``precision``, ``recall`` and ``map`` containing
        the respective metric values averaged over all users.

    Raises
    ------
    ValueError
        If ``k`` is not a positive integer or if input dictionaries are empty.
    """
    k = _ensure_non_negative_int(k, "k")
    if k == 0:
        raise ValueError("k must be a positive integer.")
    if not recommendations:
        raise ValueError("Recommendations dictionary is empty.")
    if not ground_truth:
        raise ValueError("Ground truth dictionary is empty.")

    precision_sum = 0.0
    recall_sum = 0.0
    ap_sum = 0.0
    user_count = 0

    for user, rec_items in recommendations.items():
        true_items = set(ground_truth.get(user, []))
        if not true_items:
            # Skip users with no ground truth; they do not contribute to metrics.
            continue

        rec_k = rec_items[:k]
        hits = [1 if item in true_items else 0 for item in rec_k]

        # Precision@k
        precision = sum(hits) / k
        # Recall@k
        recall = sum(hits) / len(true_items)

        # Average Precision
        cum_hits = 0
        ap = 0.0
        for idx, hit in enumerate(hits, start=1):
            if hit:
                cum_hits += 1
                ap += cum_hits / idx
        if hits:
            ap /= min(len(true_items), k)
        else:
            ap = 0.0

        precision_sum += precision
        recall_sum += recall
        ap_sum += ap
        user_count += 1

    if user_count == 0:
        raise ValueError("No users with ground truth were found in the data.")

    return {
        "precision": precision_sum / user_count,
        "recall": recall_sum / user_count,
        "map": ap_sum / user_count,
    }