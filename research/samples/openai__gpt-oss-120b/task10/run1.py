"""
collab_filter.py

A lightweight collaborative‑filtering recommender system based on user‑based
cosine similarity. The module provides utilities to:

* Build a user‑item rating matrix from a pandas DataFrame.
* Compute pairwise user similarity using cosine distance.
* Generate top‑N item recommendations for a given user.
* Evaluate recommendations with precision@K and recall@K.

Only the Python standard library and widely‑used packages (pandas, numpy,
scipy) are required.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd
from scipy.spatial.distance import cosine

__all__ = [
    "build_user_item_matrix",
    "compute_user_similarity",
    "recommend_top_n",
    "precision_at_k",
    "recall_at_k",
    "train_test_split",
]

# Configure a module‑level logger.
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def _validate_dataframe(
    df: pd.DataFrame,
    required_columns: Iterable[str],
) -> None:
    """
    Ensure that *df* contains all *required_columns*.

    Args:
        df: DataFrame to validate.
        required_columns: Column names that must be present.

    Raises:
        ValueError: If any required column is missing.
    """
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


def build_user_item_matrix(
    ratings: pd.DataFrame,
    user_col: str = "user_id",
    item_col: str = "item_id",
    rating_col: str = "rating",
) -> pd.DataFrame:
    """
    Construct a user‑item matrix where rows are users, columns are items,
    and cells contain the rating (or ``0`` if missing).

    Args:
        ratings: DataFrame with at least ``user_col``, ``item_col`` and
            ``rating_col``.
        user_col: Name of the column containing user identifiers.
        item_col: Name of the column containing item identifiers.
        rating_col: Name of the column containing rating values.

    Returns:
        A DataFrame indexed by users and columned by items.

    Raises:
        ValueError: If required columns are absent or if the rating column
            contains non‑numeric data.
    """
    _validate_dataframe(ratings, [user_col, item_col, rating_col])

    if not np.issubdtype(ratings[rating_col].dtype, np.number):
        raise ValueError(f"Column '{rating_col}' must contain numeric values.")

    logger.debug("Pivoting ratings DataFrame to user‑item matrix.")
    matrix = ratings.pivot_table(
        index=user_col,
        columns=item_col,
        values=rating_col,
        aggfunc="mean",
        fill_value=0,
    )
    logger.info(
        "User‑item matrix built with %d users and %d items.",
        matrix.shape[0],
        matrix.shape[1],
    )
    return matrix


def compute_user_similarity(matrix: pd.DataFrame) -> pd.DataFrame:
    """
    Compute cosine similarity between all pairs of users.

    Args:
        matrix: User‑item rating matrix (users as rows).

    Returns:
        A DataFrame where entry ``(u, v)`` is the cosine similarity between
        users *u* and *v*.

    Raises:
        ValueError: If the matrix is empty or contains non‑numeric values.
    """
    if matrix.empty:
        raise ValueError("The input user‑item matrix is empty.")
    if not np.issubdtype(matrix.values.dtype, np.number):
        raise ValueError("User‑item matrix must contain numeric values.")

    logger.debug("Normalizing user vectors for cosine similarity.")
    # Normalize rows to unit length; avoid division by zero.
    norm = np.linalg.norm(matrix.values, axis=1, keepdims=True)
    norm[norm == 0] = 1.0
    normalized = matrix.values / norm

    logger.debug("Computing pairwise cosine similarity.")
    similarity = np.dot(normalized, normalized.T)

    # Clip possible numeric noise.
    np.clip(similarity, -1.0, 1.0, out=similarity)

    sim_df = pd.DataFrame(
        similarity,
        index=matrix.index,
        columns=matrix.index,
    )
    logger.info("User similarity matrix computed.")
    return sim_df


def recommend_top_n(
    user_id,
    matrix: pd.DataFrame,
    similarity: pd.DataFrame,
    n: int = 10,
    filter_seen: bool = True,
) -> List[Tuple]:
    """
    Generate the top‑N item recommendations for *user_id*.

    The score for an unseen item is the weighted average of ratings from
    similar users, weighted by cosine similarity.

    Args:
        user_id: Identifier of the target user (must be present in *matrix*).
        matrix: User‑item rating matrix.
        similarity: User‑user similarity matrix.
        n: Number of items to recommend.
        filter_seen: If ``True``, items already rated by the user are excluded.

    Returns:
        A list of tuples ``(item_id, score)`` sorted by descending score.

    Raises:
        KeyError: If *user_id* is not found in *matrix* or *similarity*.
        ValueError: If *n* is not a positive integer.
    """
    if n <= 0:
        raise ValueError("Parameter 'n' must be a positive integer.")
    if user_id not in matrix.index:
        raise KeyError(f"User ID {user_id!r} not found in the rating matrix.")
    if user_id not in similarity.index:
        raise KeyError(f"User ID {user_id!r} not found in the similarity matrix.")

    logger.debug("Computing recommendation scores for user %s.", user_id)
    user_ratings = matrix.loc[user_id]
    similar_users = similarity[user_id]

    # Exclude the target user from the similarity weights.
    similar_users = similar_users.drop(user_id)

    # Weighted sum of ratings.
    weighted_ratings = np.dot(similar_users.values, matrix.values)
    similarity_sums = similar_users.values.sum()
    if similarity_sums == 0:
        logger.warning("User %s has zero similarity sum; returning empty list.", user_id)
        return []

    scores = weighted_ratings / similarity_sums

    # Build a Series aligned with items.
    score_series = pd.Series(scores, index=matrix.columns)

    if filter_seen:
        unseen = user_ratings[user_ratings == 0].index
        score_series = score_series.loc[unseen]

    top_items = score_series.nlargest(n)
    recommendations = list(zip(top_items.index, top_items.values))
    logger.info("Generated %d recommendations for user %s.", len(recommendations), user_id)
    return recommendations


def precision_at_k(
    recommendations: Dict,
    test_interactions: pd.DataFrame,
    user_col: str = "user_id",
    item_col: str = "item_id",
    k: int = 10,
) -> float:
    """
    Compute precision@K across all users.

    Args:
        recommendations: Mapping ``user_id -> list of recommended item_id``.
        test_interactions: Ground‑truth interactions (must contain *user_col*
            and *item_col*).
        user_col: Name of the user identifier column in *test_interactions*.
        item_col: Name of the item identifier column in *test_interactions*.
        k: Cut‑off rank for evaluation.

    Returns:
        Mean precision@K.

    Raises:
        ValueError: If *k* is not positive or if inputs are malformed.
    """
    if k <= 0:
        raise ValueError("Parameter 'k' must be a positive integer.")
    _validate_dataframe(test_interactions, [user_col, item_col])

    # Build ground‑truth sets.
    gt: Dict = defaultdict(set)
    for _, row in test_interactions.iterrows():
        gt[row[user_col]].add(row[item_col])

    precisions = []
    for user, recs in recommendations.items():
        if not recs:
            continue
        top_k = recs[:k]
        hit_count = sum(1 for item in top_k if item in gt.get(user, set()))
        precisions.append(hit_count / k)

    if not precisions:
        logger.warning("No recommendations to evaluate for precision@%d.", k)
        return 0.0
    mean_precision = float(np.mean(precisions))
    logger.info("Precision@%d = %.4f", k, mean_precision)
    return mean_precision


def recall_at_k(
    recommendations: Dict,
    test_interactions: pd.DataFrame,
    user_col: str = "user_id",
    item_col: str = "item_id",
    k: int = 10,
) -> float:
    """
    Compute recall@K across all users.

    Args:
        recommendations: Mapping ``user_id -> list of recommended item_id``.
        test_interactions: Ground‑truth interactions (must contain *user_col*
            and *item_col*).
        user_col: Name of the user identifier column in *test_interactions*.
        item_col: Name of the item identifier column in *test_interactions*.
        k: Cut‑off rank for evaluation.

    Returns:
        Mean recall@K.

    Raises:
        ValueError: If *k* is not positive or if inputs are malformed.
    """
    if k <= 0:
        raise ValueError("Parameter 'k' must be a positive integer.")
    _validate_dataframe(test_interactions, [user_col, item_col])

    gt: Dict = defaultdict(set)
    for _, row in test_interactions.iterrows():
        gt[row[user_col]].add(row[item_col])

    recalls = []
    for user, recs in recommendations.items():
        relevant = gt.get(user, set())
        if not relevant:
            continue
        top_k = recs[:k]
        hit_count = sum(1 for item in top_k if item in relevant)
        recalls.append(hit_count / len(relevant))

    if not recalls:
        logger.warning("No recommendations to evaluate for recall@%d.", k)
        return 0.0
    mean_recall = float(np.mean(recalls))
    logger.info("Recall@%d = %.4f", k, mean_recall)
    return mean_recall


def train_test_split(
    ratings: pd.DataFrame,
    test_ratio: float = 0.2,
    user_col: str = "user_id",
    item_col: str = "item_id",
    rating_col: str = "rating",
    random_state: int | None = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Split the rating data into train and test sets while preserving each
    user's interactions.

    Args:
        ratings: Full rating DataFrame.
        test_ratio: Fraction of each user's interactions to allocate to test.
        user_col: Column name for users.
        item_col: Column name for items.
        rating_col: Column name for rating values.
        random_state: Seed for reproducibility.

    Returns:
        A tuple ``(train_df, test_df)``.

    Raises:
        ValueError: If *test_ratio* is not between 0 and 1.
    """
    if not (0.0 < test_ratio < 1.0):
        raise ValueError("test_ratio must be between 0 and 1 (exclusive).")
    _validate_dataframe(ratings, [user_col, item_col, rating_col])

    rng = np.random.default_rng(random_state)
    train_frames = []
    test_frames = []

    logger.debug("Performing stratified train/test split with ratio %.2f.", test_ratio)
    for user, group in ratings.groupby(user_col):
        n_total = len(group)
        n_test = max(1, int(np.floor(test_ratio * n_total)))
        shuffled = group.sample(frac=1, random_state=rng.integers(0, 2**32 - 1))
        test_frames.append(shuffled.iloc[:n_test])
        train_frames.append(shuffled.iloc[n_test:])

    train_df = pd.concat(train_frames).reset_index(drop=True)
    test_df = pd.concat(test_frames).reset_index(drop=True)

    logger.info(
        "Split data into %d training and %d testing interactions.",
        len(train_df),
        len(test_df),
    )
    return train_df, test_df