"""
Collaborative Filtering Recommender System
==========================================

This module provides a simple user‑based collaborative filtering implementation
with the following capabilities:

* Construction of a user‑item rating matrix from a Pandas DataFrame.
* Cosine similarity computation between users.
* Generation of top‑N item recommendations for a given user.
* Evaluation utilities: precision@k, recall@k, MAP@k, and NDCG@k.

Only the Python standard library together with ``numpy`` and ``pandas`` are
required.
"""

from __future__ import annotations

import math
import warnings
from typing import Dict, Iterable, List, Tuple, Union

import numpy as np
import pandas as pd


class CollaborativeFilteringRecommender:
    """
    User‑based collaborative filtering recommender.

    Parameters
    ----------
    min_common : int, optional
        Minimum number of common rated items required to compute a similarity
        value between two users. Defaults to ``1``.
    """

    def __init__(self, min_common: int = 1) -> None:
        if not isinstance(min_common, int) or min_common < 1:
            raise ValueError("min_common must be a positive integer.")
        self.min_common = min_common
        self.user_ids: List[int] = []
        self.item_ids: List[int] = []
        self.rating_matrix: np.ndarray | None = None
        self.user_similarity: np.ndarray | None = None
        self._user_index: Dict[int, int] = {}
        self._item_index: Dict[int, int] = {}

    # --------------------------------------------------------------------- #
    # Data preparation
    # --------------------------------------------------------------------- #
    def fit(self, interactions: pd.DataFrame) -> None:
        """
        Build the user‑item rating matrix and compute the user similarity matrix.

        Parameters
        ----------
        interactions : pd.DataFrame
            Must contain the columns ``user_id``, ``item_id`` and ``rating``.
            ``rating`` should be numeric (float or int). Rows with missing values
            are ignored.

        Raises
        ------
        ValueError
            If required columns are missing or if the DataFrame is empty.
        """
        required = {"user_id", "item_id", "rating"}
        if not required.issubset(interactions.columns):
            raise ValueError(f"DataFrame must contain columns: {required}")

        df = interactions.dropna(subset=["user_id", "item_id", "rating"]).copy()
        if df.empty:
            raise ValueError("No valid interaction records found after cleaning.")

        # Encode users & items as contiguous integer indices
        self.user_ids = sorted(df["user_id"].unique())
        self.item_ids = sorted(df["item_id"].unique())
        self._user_index = {uid: i for i, uid in enumerate(self.user_ids)}
        self._item_index = {iid: i for i, iid in enumerate(self.item_ids)}
        n_users = len(self.user_ids)
        n_items = len(self.item_ids)

        # Sparse matrix construction using dense numpy array (suitable for small‑medium data)
        self.rating_matrix = np.zeros((n_users, n_items), dtype=np.float32)

        for _, row in df.iterrows():
            try:
                u = self._user_index[int(row["user_id"])]
                i = self._item_index[int(row["item_id"])]
                self.rating_matrix[u, i] = float(row["rating"])
            except (KeyError, ValueError) as exc:
                # Defensive programming: skip malformed rows
                warnings.warn(f"Skipping row due to unexpected values: {exc}")

        self._compute_user_similarity()

    # --------------------------------------------------------------------- #
    # Similarity computation
    # --------------------------------------------------------------------- #
    def _compute_user_similarity(self) -> None:
        """Compute cosine similarity between users, respecting ``min_common``."""
        if self.rating_matrix is None:
            raise RuntimeError("Model must be fitted before computing similarity.")

        n_users = self.rating_matrix.shape[0]
        self.user_similarity = np.zeros((n_users, n_users), dtype=np.float32)

        # Pre‑compute norms, handling zero‑norm vectors safely
        norms = np.linalg.norm(self.rating_matrix, axis=1)
        zero_norm_mask = norms == 0
        if np.any(zero_norm_mask):
            warnings.warn("Some users have zero rating vectors; they will have no similarity.")
            norms[zero_norm_mask] = 1.0  # Prevent division by zero

        normalized = self.rating_matrix / norms[:, None]

        # Compute full cosine similarity matrix
        sim = normalized @ normalized.T

        # Apply min_common filter
        common_counts = (self.rating_matrix > 0).astype(int) @ (self.rating_matrix > 0).T.astype(int)
        sim[common_counts < self.min_common] = 0.0

        # Clip numerical noise
        np.clip(sim, -1.0, 1.0, out=sim)
        self.user_similarity = sim

    # --------------------------------------------------------------------- #
    # Recommendation
    # --------------------------------------------------------------------- #
    def recommend(self, user_id: int, n: int = 10, filter_seen: bool = True) -> List[Tuple[int, float]]:
        """
        Generate top‑N item recommendations for a given user.

        Parameters
        ----------
        user_id : int
            Identifier of the target user.
        n : int, optional
            Number of recommendations to return. Must be positive. Default is ``10``.
        filter_seen : bool, optional
            If ``True`` (default), items already rated by the user are excluded
            from the results.

        Returns
        -------
        List[Tuple[int, float]]
            List of ``(item_id, predicted_score)`` sorted by descending score.

        Raises
        ------
        KeyError
            If ``user_id`` is unknown to the model.
        ValueError
            If ``n`` is not a positive integer.
        """
        if self.user_similarity is None or self.rating_matrix is None:
            raise RuntimeError("Model has not been fitted.")
        if not isinstance(n, int) or n <= 0:
            raise ValueError("Parameter 'n' must be a positive integer.")
        if user_id not in self._user_index:
            raise KeyError(f"User ID {user_id} not found in the model.")

        user_idx = self._user_index[user_id]
        sim_vector = self.user_similarity[user_idx]  # shape: (n_users,)

        # Weighted sum of other users' ratings
        weighted_ratings = sim_vector @ self.rating_matrix  # shape: (n_items,)

        # Normalise by sum of absolute similarities to avoid bias from many similar users
        sim_abs_sum = np.sum(np.abs(sim_vector))
        if sim_abs_sum == 0:
            warnings.warn(f"User {user_id} has zero similarity to any other user.")
            scores = np.zeros_like(weighted_ratings)
        else:
            scores = weighted_ratings / sim_abs_sum

        if filter_seen:
            seen_mask = self.rating_matrix[user_idx] > 0
            scores[seen_mask] = -np.inf  # Ensure they are not recommended

        # Retrieve top‑N indices
        top_idx = np.argpartition(-scores, range(min(n, scores.size)))[:n]
        top_idx_sorted = top_idx[np.argsort(-scores[top_idx])]

        recommendations = [
            (self.item_ids[i], float(scores[i])) for i in top_idx_sorted if not np.isinf(scores[i])
        ]

        return recommendations

    # --------------------------------------------------------------------- #
    # Evaluation utilities
    # --------------------------------------------------------------------- #
    @staticmethod
    def _precision_at_k(true_items: Iterable[int], pred_items: List[int], k: int) -> float:
        if k == 0:
            return 0.0
        pred_k = set(pred_items[:k])
        true_set = set(true_items)
        return len(pred_k & true_set) / k

    @staticmethod
    def _recall_at_k(true_items: Iterable[int], pred_items: List[int], k: int) -> float:
        if k == 0:
            return 0.0
        pred_k = set(pred_items[:k])
        true_set = set(true_items)
        if not true_set:
            return 0.0
        return len(pred_k & true_set) / len(true_set)

    @staticmethod
    def _average_precision_at_k(true_items: Iterable[int], pred_items: List[int], k: int) -> float:
        """Mean Average Precision (MAP) for a single user."""
        true_set = set(true_items)
        if not true_set:
            return 0.0
        score = 0.0
        hits = 0
        for i in range(min(k, len(pred_items))):
            if pred_items[i] in true_set:
                hits += 1
                score += hits / (i + 1)
        return score / min(len(true_set), k)

    @staticmethod
    def _dcg_at_k(pred_items: List[int], true_items: Iterable[int], k: int) -> float:
        """Discounted Cumulative Gain."""
        true_set = set(true_items)
        dcg = 0.0
        for i in range(min(k, len(pred_items))):
            rel = 1 if pred_items[i] in true_set else 0
            if rel:
                dcg += 1 / math.log2(i + 2)  # i+2 because rank starts at 1
        return dcg

    @staticmethod
    def _ndcg_at_k(true_items: Iterable[int], pred_items: List[int], k: int) -> float:
        """Normalized Discounted Cumulative Gain."""
        ideal_dcg = CollaborativeFilteringRecommender._dcg_at_k(
            list(true_items)[:k], true_items, k
        )
        if ideal_dcg == 0:
            return 0.0
        actual_dcg = CollaborativeFilteringRecommender._dcg_at_k(pred_items, true_items, k)
        return actual_dcg / ideal_dcg

    def evaluate(
        self,
        test_interactions: pd.DataFrame,
        ks: Iterable[int] = (5, 10, 20),
    ) -> Dict[int, Dict[str, float]]:
        """
        Evaluate the recommender on a test set using precision, recall, MAP and NDCG.

        Parameters
        ----------
        test_interactions : pd.DataFrame
            Must contain ``user_id`` and ``item_id`` columns. Each row is a
            ground‑truth interaction (e.g., a held‑out rating).
        ks : Iterable[int], optional
            Cut‑off values for the metrics. Default ``(5, 10, 20)``.

        Returns
        -------
        Dict[int, Dict[str, float]]
            Mapping from ``k`` to a dictionary with metric names and their mean values.
        """
        if not {"user_id", "item_id"}.issubset(test_interactions.columns):
            raise ValueError("test_interactions must contain 'user_id' and 'item_id' columns.")

        # Build ground truth per user
        gt: Dict[int, List[int]] = {}
        for _, row in test_interactions.iterrows():
            uid = int(row["user_id"])
            iid = int(row["item_id"])
            gt.setdefault(uid, []).append(iid)

        results: Dict[int, Dict[str, float]] = {}
        for k in ks:
            precisions, recalls, maps, ndcgs = [], [], [], []
            for uid, true_items in gt.items():
                if uid not in self._user_index:
                    # Skip unknown users – could also count as zero score
                    continue
                recs = self.recommend(uid, n=k, filter_seen=False)
                pred_items = [iid for iid, _ in recs]

                precisions.append(self._precision_at_k(true_items, pred_items, k))
                recalls.append(self._recall_at_k(true_items, pred_items, k))
                maps.append(self._average_precision_at_k(true_items, pred_items, k))
                ndcgs.append(self._ndcg_at_k(true_items, pred_items, k))

            # Aggregate (mean) scores; handle division by zero when no users are evaluated.
            divisor = max(1, len(precisions))
            results[k] = {
                "precision": sum(precisions) / divisor,
                "recall": sum(recalls) / divisor,
                "map": sum(maps) / divisor,
                "ndcg": sum(ndcgs) / divisor,
            }

        return results

    # --------------------------------------------------------------------- #
    # Utility / safety
    # --------------------------------------------------------------------- #
    @staticmethod
    def _safe_int(value: Union[int, str, float]) -> int:
        """Convert a value to int safely, raising a clear error on failure."""
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Unable to convert {value!r} to int.") from exc