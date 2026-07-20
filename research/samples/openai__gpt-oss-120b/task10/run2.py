"""
Collaborative Filtering Recommendation System
==============================================

This module provides a simple user‑based collaborative filtering implementation
with the following capabilities:

* Construction of a user‑item rating matrix from a DataFrame.
* Cosine similarity computation between users.
* Generation of top‑N item recommendations for a specific user.
* Evaluation of recommendations using precision@k, recall@k, MAP and NDCG.

Only the Python standard library together with ``numpy`` and ``pandas`` are used.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd

__all__ = [
    "CollaborativeFilteringRecommender",
    "cosine_similarity",
]

# Configure a module‑level logger (security‑best‑practice: never use print for lib code)
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def cosine_similarity(matrix: np.ndarray) -> np.ndarray:
    """
    Compute the cosine similarity between rows of a matrix.

    Parameters
    ----------
    matrix: np.ndarray
        2‑D array where each row represents an entity (e.g., a user).

    Returns
    -------
    np.ndarray
        Square similarity matrix (shape: n_entities × n_entities).

    Raises
    ------
    ValueError
        If ``matrix`` is not 2‑dimensional.
    """
    if matrix.ndim != 2:
        raise ValueError("Input matrix must be 2‑dimensional")

    # L2 norm per row; add epsilon to avoid division by zero
    epsilon = np.finfo(float).eps
    norms = np.linalg.norm(matrix, axis=1, keepdims=True) + epsilon
    normalized = matrix / norms

    # Cosine similarity = dot product of normalized vectors
    similarity = normalized @ normalized.T
    # Numerical errors may push values slightly outside [-1, 1]
    np.clip(similarity, -1.0, 1.0, out=similarity)
    return similarity


class CollaborativeFilteringRecommender:
    """
    User‑based collaborative filtering recommender.

    Parameters
    ----------
    ratings : pd.DataFrame
        DataFrame containing at least three columns:
        ``user_id``, ``item_id`` and ``rating`` (numeric).

    Notes
    -----
    The class stores the user‑item matrix and the user similarity matrix
    internally after calling :meth:`fit`.
    """

    REQUIRED_COLUMNS = {"user_id", "item_id", "rating"}

    def __init__(self, ratings: pd.DataFrame) -> None:
        self._validate_ratings(ratings)
        # Preserve original identifiers for later mapping
        self._raw_ratings = ratings.copy()
        self._user_ids: List[Any] = []
        self._item_ids: List[Any] = []
        self._user_item_matrix: pd.DataFrame | None = None
        self._user_similarity: pd.DataFrame | None = None

    @staticmethod
    def _validate_ratings(ratings: pd.DataFrame) -> None:
        """Validate the input ratings DataFrame."""
        if not isinstance(ratings, pd.DataFrame):
            raise TypeError("ratings must be a pandas DataFrame")
        missing = CollaborativeFilteringRecommender.REQUIRED_COLUMNS - set(ratings.columns)
        if missing:
            raise ValueError(f"ratings DataFrame missing required columns: {missing}")
        if ratings.empty:
            raise ValueError("ratings DataFrame is empty")
        if ratings["rating"].isnull().any():
            raise ValueError("rating column contains NaN values")

    def fit(self) -> None:
        """
        Build the user‑item matrix and compute user similarity.
        """
        logger.info("Building user‑item matrix")
        self._user_item_matrix = (
            self._raw_ratings.pivot_table(
                index="user_id", columns="item_id", values="rating", fill_value=0
            )
            .astype(float)
        )
        self._user_ids = list(self._user_item_matrix.index)
        self._item_ids = list(self._user_item_matrix.columns)

        logger.info("Computing cosine similarity between users")
        matrix = self._user_item_matrix.values
        sim = cosine_similarity(matrix)
        self._user_similarity = pd.DataFrame(
            sim, index=self._user_ids, columns=self._user_ids
        )
        logger.info("Model fitting completed")

    def _ensure_fitted(self) -> None:
        """Raise an informative error if the model has not been fitted."""
        if self._user_item_matrix is None or self._user_similarity is None:
            raise RuntimeError(
                "Model has not been fitted yet. Call `.fit()` before using other methods."
            )

    def get_top_n_recommendations(
        self, user_id: Any, n: int = 10, min_similarity: float = 0.0
    ) -> List[Tuple[Any, float]]:
        """
        Produce top‑N item recommendations for a given user.

        Parameters
        ----------
        user_id : Any
            Identifier of the target user (must exist in the training data).
        n : int, default 10
            Number of items to recommend.
        min_similarity : float, default 0.0
            Minimum similarity for a neighbor to be considered.

        Returns
        -------
        List[Tuple[Any, float]]
            List of (item_id, aggregated_score) sorted by descending score.

        Raises
        ------
        KeyError
            If ``user_id`` is unknown.
        ValueError
            If ``n`` is not a positive integer.
        """
        self._ensure_fitted()
        if user_id not in self._user_item_matrix.index:
            raise KeyError(f"User ID {user_id!r} not found in training data")
        if n <= 0:
            raise ValueError("n must be a positive integer")

        # Retrieve similarity vector for target user
        user_sim = self._user_similarity.loc[user_id]
        # Exclude the user itself and low‑similarity neighbors
        neighbors = user_sim[user_sim >= min_similarity].drop(labels=user_id, errors="ignore")
        if neighbors.empty:
            logger.warning("No neighbors with similarity >= %s for user %s", min_similarity, user_id)
            return []

        # Weighted sum of neighbor ratings
        neighbor_ratings = self._user_item_matrix.loc[neighbors.index]
        weights = neighbors.values[:, np.newaxis]  # shape (n_neighbors, 1)
        weighted_ratings = (neighbor_ratings.values * weights).sum(axis=0)

        # Normalise by sum of absolute similarities to avoid bias towards prolific users
        denom = np.abs(weights).sum()
        if denom == 0:
            logger.warning("Sum of neighbor similarities is zero for user %s", user_id)
            return []

        scores = weighted_ratings / denom

        # Mask items already rated by the user
        user_history = self._user_item_matrix.loc[user_id].values
        already_rated = user_history > 0
        scores[already_rated] = -np.inf  # exclude

        # Get top‑N indices
        top_idx = np.argpartition(-scores, range(min(n, len(scores))))[:n]
        top_items = [(self._item_ids[i], float(scores[i])) for i in top_idx]
        # Sort final list by score descending
        top_items.sort(key=lambda x: x[1], reverse=True)
        return top_items

    @staticmethod
    def _precision_at_k(recommended: List[Any], relevant: set[Any], k: int) -> float:
        if k == 0:
            return 0.0
        hits = len(set(recommended[:k]) & relevant)
        return hits / k

    @staticmethod
    def _recall_at_k(recommended: List[Any], relevant: set[Any], k: int) -> float:
        if not relevant:
            return 0.0
        hits = len(set(recommended[:k]) & relevant)
        return hits / len(relevant)

    @staticmethod
    def _average_precision(recommended: List[Any], relevant: set[Any], k: int) -> float:
        """Mean Average Precision at k."""
        if not relevant:
            return 0.0
        score = 0.0
        hits = 0
        for i, item in enumerate(recommended[:k], start=1):
            if item in relevant:
                hits += 1
                score += hits / i
        return score / min(len(relevant), k)

    @staticmethod
    def _dcg_at_k(recommended: List[Any], relevant: set[Any], k: int) -> float:
        """Discounted Cumulative Gain at k."""
        dcg = 0.0
        for i, item in enumerate(recommended[:k], start=1):
            if item in relevant:
                dcg += 1.0 / math.log2(i + 1)
        return dcg

    @staticmethod
    def _idcg_at_k(relevant: set[Any], k: int) -> float:
        """Ideal DCG (sorted by relevance) at k."""
        ideal_hits = min(len(relevant), k)
        idcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal_hits + 1))
        return idcg

    def evaluate(
        self,
        test_ratings: pd.DataFrame,
        k: int = 10,
        rating_threshold: float = 0.0,
    ) -> Dict[str, float]:
        """
        Evaluate the recommender on a test set.

        Parameters
        ----------
        test_ratings : pd.DataFrame
            DataFrame with the same schema as the training data.
        k : int, default 10
            Maximum number of recommendations considered for metrics.
        rating_threshold : float, default 0.0
            Minimum rating to consider an item as relevant.

        Returns
        -------
        dict
            Dictionary containing ``precision``, ``recall``, ``map`` and ``ndcg``.

        Raises
        ------
        ValueError
            If ``k`` is non‑positive or ``test_ratings`` is malformed.
        """
        self._ensure_fitted()
        if k <= 0:
            raise ValueError("k must be a positive integer")
        if not isinstance(test_ratings, pd.DataFrame):
            raise TypeError("test_ratings must be a pandas DataFrame")
        missing = self.REQUIRED_COLUMNS - set(test_ratings.columns)
        if missing:
            raise ValueError(f"test_ratings missing required columns: {missing}")

        # Build a mapping user -> set of relevant items in test set
        relevance: Dict[Any, set[Any]] = defaultdict(set)
        for _, row in test_ratings.iterrows():
            if row["rating"] >= rating_threshold:
                relevance[row["user_id"]].add(row["item_id"])

        if not relevance:
            raise ValueError("No relevant items found in test data with the given threshold")

        # Accumulate metrics
        precision_sum = recall_sum = map_sum = ndcg_sum = 0.0
        evaluated_users = 0

        for user, rel_items in relevance.items():
            # Skip users absent from training data
            if user not in self._user_item_matrix.index:
                continue
            recs = self.get_top_n_recommendations(user, n=k)
            rec_items = [item for item, _ in recs]

            precision_sum += self._precision_at_k(rec_items, rel_items, k)
            recall_sum += self._recall_at_k(rec_items, rel_items, k)
            map_sum += self._average_precision(rec_items, rel_items, k)

            dcg = self._dcg_at_k(rec_items, rel_items, k)
            idcg = self._idcg_at_k(rel_items, k)
            ndcg_sum += dcg / idcg if idcg > 0 else 0.0

            evaluated_users += 1

        if evaluated_users == 0:
            raise RuntimeError("No users in test set were present in the training data")

        metrics = {
            "precision@k": precision_sum / evaluated_users,
            "recall@k": recall_sum / evaluated_users,
            "map@k": map_sum / evaluated_users,
            "ndcg@k": ndcg_sum / evaluated_users,
        }
        logger.info("Evaluation completed on %d users", evaluated_users)
        return metrics