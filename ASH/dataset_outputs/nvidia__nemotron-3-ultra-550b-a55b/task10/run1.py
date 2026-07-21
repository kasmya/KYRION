"""
Collaborative Filtering Recommender System

This module implements a user-based collaborative filtering recommender.
It builds a user-item matrix, computes cosine similarity between users,
generates top-N recommendations, and provides evaluation metrics.

Example:
    >>> from recommender import CollaborativeFilteringRecommender
    >>> interactions = [
    ...     ("user1", "item1", 5),
    ...     ("user1", "item2", 3),
    ...     ("user2", "item1", 4),
    ...     ("user2", "item3", 2),
    ... ]
    >>> model = CollaborativeFilteringRecommender()
    >>> model.fit(interactions)
    >>> recommendations = model.recommend("user1", n=2)
    >>> print(recommendations)
    ['item3', 'item2']
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Dict, List, Tuple, Set, Optional, Any

import numpy as np


class CollaborativeFilteringRecommender:
    """
    User-based collaborative filtering recommender using cosine similarity.

    Attributes:
        user_item_matrix: Dict mapping user -> Dict[item -> rating]
        user_similarities: Dict mapping user -> Dict[other_user -> similarity]
        all_items: Set of all item IDs encountered during fit
    """

    def __init__(self) -> None:
        """Initialize an empty recommender."""
        self.user_item_matrix: Dict[str, Dict[str, float]] = {}
        self.user_similarities: Dict[str, Dict[str, float]] = {}
        self.all_items: Set[str] = set()
        self._is_fitted = False

    def fit(self, interactions: List[Tuple[str, str, float]]) -> None:
        """
        Build user-item matrix and compute user-user cosine similarities.

        Args:
            interactions: List of (user_id, item_id, rating) tuples.
                Ratings should be numeric (implicit or explicit feedback).

        Raises:
            ValueError: If interactions list is empty or contains invalid entries.
            TypeError: If interactions is not a list of 3-element tuples.
        """
        if not isinstance(interactions, list):
            raise TypeError("interactions must be a list of tuples")

        if not interactions:
            raise ValueError("interactions list cannot be empty")

        # Validate and build user-item matrix
        self.user_item_matrix = defaultdict(dict)
        self.all_items = set()

        for idx, interaction in enumerate(interactions):
            if not isinstance(interaction, tuple) or len(interaction) != 3:
                raise TypeError(
                    f"Interaction at index {idx} must be a 3-element tuple "
                    f"(user_id, item_id, rating)"
                )
            user_id, item_id, rating = interaction
            if not isinstance(user_id, str) or not isinstance(item_id, str):
                raise TypeError(
                    f"User ID and item ID must be strings at index {idx}"
                )
            try:
                rating_val = float(rating)
            except (TypeError, ValueError):
                raise TypeError(f"Rating must be numeric at index {idx}")
            self.user_item_matrix[user_id][item_id] = rating_val
            self.all_items.add(item_id)

        # Convert to regular dict for safety
        self.user_item_matrix = dict(self.user_item_matrix)

        # Compute user-user cosine similarities
        self.user_similarities = self._compute_user_similarities()
        self._is_fitted = True

    def _compute_user_similarities(self) -> Dict[str, Dict[str, float]]:
        """
        Compute cosine similarity between all pairs of users.

        Returns:
            Nested dictionary: user_a -> {user_b: similarity, ...}
        """
        users = list(self.user_item_matrix.keys())
        n_users = len(users)
        similarities: Dict[str, Dict[str, float]] = {u: {} for u in users}

        # Precompute user vectors as numpy arrays for efficiency
        all_items_list = sorted(self.all_items)
        item_to_idx = {item: i for i, item in enumerate(all_items_list)}
        user_vectors = np.zeros((n_users, len(all_items_list)), dtype=np.float32)

        for u_idx, user in enumerate(users):
            for item, rating in self.user_item_matrix[user].items():
                user_vectors[u_idx, item_to_idx[item]] = rating

        # Compute cosine similarity matrix
        # Normalize rows to unit length
        norms = np.linalg.norm(user_vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0  # Avoid division by zero
        normalized = user_vectors / norms

        # Cosine similarity = normalized @ normalized.T
        sim_matrix = normalized @ normalized.T

        # Fill dictionary (only upper triangle to avoid redundancy)
        for i in range(n_users):
            for j in range(i + 1, n_users):
                sim = float(sim_matrix[i, j])
                user_i = users[i]
                user_j = users[j]
                similarities[user_i][user_j] = sim
                similarities[user_j][user_i] = sim

        return similarities

    def recommend(
        self,
        user_id: str,
        n: int = 10,
        min_similarity: float = 0.0,
        exclude_rated: bool = True,
    ) -> List[str]:
        """
        Generate top-N item recommendations for a user.

        Args:
            user_id: Target user ID.
            n: Number of recommendations to return.
            min_similarity: Minimum similarity threshold for neighbor users.
            exclude_rated: Whether to exclude items the user has already rated.

        Returns:
            List of recommended item IDs (length <= n).

        Raises:
            RuntimeError: If model has not been fitted.
            KeyError: If user_id is not in the training data.
            ValueError: If n <= 0.
        """
        if not self._is_fitted:
            raise RuntimeError("Model must be fitted before making recommendations")

        if user_id not in self.user_item_matrix:
            raise KeyError(f"User '{user_id}' not found in training data")

        if n <= 0:
            raise ValueError("n must be a positive integer")

        # Get similar users above threshold
        similar_users = {
            u: sim
            for u, sim in self.user_similarities[user_id].items()
            if sim >= min_similarity
        }

        if not similar_users:
            return []

        # Aggregate weighted ratings from similar users
        user_rated = set(self.user_item_matrix[user_id].keys())
        item_scores: Dict[str, float] = defaultdict(float)
        item_weights: Dict[str, float] = defaultdict(float)

        for other_user, similarity in similar_users.items():
            for item, rating in self.user_item_matrix[other_user].items():
                if exclude_rated and item in user_rated:
                    continue
                item_scores[item] += similarity * rating
                item_weights[item] += similarity

        # Compute weighted average scores
        scored_items = [
            (item, item_scores[item] / item_weights[item])
            for item in item_scores
            if item_weights[item] > 0
        ]

        # Sort by score descending, then by item ID for determinism
        scored_items.sort(key=lambda x: (-x[1], x[0]))

        return [item for item, _ in scored_items[:n]]

    def evaluate(
        self,
        test_interactions: List[Tuple[str, str, float]],
        k: int = 10,
        min_similarity: float = 0.0,
    ) -> Dict[str, float]:
        """
        Evaluate recommender using Precision@K and Recall@K.

        Args:
            test_interactions: Held-out interactions for evaluation.
            k: Number of recommendations to consider.
            min_similarity: Minimum similarity threshold for neighbors.

        Returns:
            Dictionary with 'precision_at_k', 'recall_at_k', 'f1_at_k'.

        Raises:
            RuntimeError: If model has not been fitted.
            ValueError: If test_interactions is empty or k <= 0.
        """
        if not self._is_fitted:
            raise RuntimeError("Model must be fitted before evaluation")

        if not test_interactions:
            raise ValueError("test_interactions cannot be empty")

        if k <= 0:
            raise ValueError("k must be a positive integer")

        # Build test user -> relevant items mapping
        test_user_items: Dict[str, Set[str]] = defaultdict(set)
        for user_id, item_id, rating in test_interactions:
            # Consider only positive interactions (rating > 0) as relevant
            if rating > 0:
                test_user_items[user_id].add(item_id)

        if not test_user_items:
            return {"precision_at_k": 0.0, "recall_at_k": 0.0, "f1_at_k": 0.0}

        precisions = []
        recalls = []

        for user_id, relevant_items in test_user_items.items():
            if user_id not in self.user_item_matrix:
                # User not in training data -> no recommendations possible
                precisions.append(0.0)
                recalls.append(0.0)
                continue

            recommended = self.recommend(
                user_id, n=k, min_similarity=min_similarity, exclude_rated=True
            )
            recommended_set = set(recommended)

            # Precision@K: fraction of recommended items that are relevant
            hits = len(recommended_set & relevant_items)
            precision = hits / len(recommended_set) if recommended_set else 0.0
            precisions.append(precision)

            # Recall@K: fraction of relevant items that are recommended
            recall = hits / len(relevant_items) if relevant_items else 0.0
            recalls.append(recall)

        avg_precision = sum(precisions) / len(precisions) if precisions else 0.0
        avg_recall = sum(recalls) / len(recalls) if recalls else 0.0

        # F1 score
        if avg_precision + avg_recall > 0:
            f1 = 2 * avg_precision * avg_recall / (avg_precision + avg_recall)
        else:
            f1 = 0.0

        return {
            "precision_at_k": round(avg_precision, 4),
            "recall_at_k": round(avg_recall, 4),
            "f1_at_k": round(f1, 4),
        }

    def get_similar_users(
        self, user_id: str, top_n: int = 10, min_similarity: float = 0.0
    ) -> List[Tuple[str, float]]:
        """
        Retrieve most similar users to a given user.

        Args:
            user_id: Target user ID.
            top_n: Number of similar users to return.
            min_similarity: Minimum similarity threshold.

        Returns:
            List of (user_id, similarity) tuples sorted by similarity descending.

        Raises:
            RuntimeError: If model not fitted.
            KeyError: If user_id not in training data.
        """
        if not self._is_fitted:
            raise RuntimeError("Model must be fitted first")

        if user_id not in self.user_similarities:
            raise KeyError(f"User '{user_id}' not found")

        similar = [
            (u, sim)
            for u, sim in self.user_similarities[user_id].items()
            if sim >= min_similarity
        ]
        similar.sort(key=lambda x: (-x[1], x[0]))
        return similar[:top_n]