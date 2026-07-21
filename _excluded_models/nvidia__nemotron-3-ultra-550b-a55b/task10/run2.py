"""
Collaborative Filtering Recommender System

This module implements an item-based collaborative filtering recommender.
It builds a user-item matrix, computes cosine similarities between items,
generates top-N recommendations for a given user, and evaluates predictions
using Root Mean Squared Error (RMSE).

All functions include type hints, docstrings, and explicit error handling.
Only the Python standard library is used.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Dict, Hashable, List, Tuple, Set, Optional


def build_matrices(
    data: List[Tuple[Hashable, Hashable, float]]
) -> Tuple[Dict[Hashable, Dict[Hashable, float]], Dict[Hashable, Dict[Hashable, float]]]:
    """
    Build user-item and item-user matrices from raw rating data.

    Args:
        data: List of tuples (user_id, item_id, rating).

    Returns:
        A tuple (user_item_matrix, item_user_matrix) where:
            user_item_matrix: {user_id: {item_id: rating}}
            item_user_matrix: {item_id: {user_id: rating}}

    Raises:
        ValueError: If data is empty or contains invalid ratings.
        TypeError: If data is not a list of 3-element tuples.
    """
    if not data:
        raise ValueError("Input data cannot be empty.")

    user_item: Dict[Hashable, Dict[Hashable, float]] = defaultdict(dict)
    item_user: Dict[Hashable, Dict[Hashable, float]] = defaultdict(dict)

    for idx, record in enumerate(data):
        if not isinstance(record, tuple) or len(record) != 3:
            raise TypeError(f"Record at index {idx} must be a 3-element tuple (user, item, rating).")
        user, item, rating = record
        if not isinstance(rating, (int, float)):
            raise TypeError(f"Rating for user {user}, item {item} must be numeric.")
        if math.isnan(rating) or math.isinf(rating):
            raise ValueError(f"Rating for user {user}, item {item} cannot be NaN or infinite.")

        user_item[user][item] = float(rating)
        item_user[item][user] = float(rating)

    return dict(user_item), dict(item_user)


def cosine_similarity(
    vec_a: Dict[Hashable, float], vec_b: Dict[Hashable, float]
) -> float:
    """
    Compute cosine similarity between two sparse vectors represented as dictionaries.

    Args:
        vec_a: Mapping from key to value (e.g., user -> rating).
        vec_b: Mapping from key to value.

    Returns:
        Cosine similarity in [-1, 1]. Returns 0.0 if either vector has zero magnitude.
    """
    if not vec_a or not vec_b:
        return 0.0

    common_keys = set(vec_a.keys()) & set(vec_b.keys())
    if not common_keys:
        return 0.0

    dot_product = sum(vec_a[k] * vec_b[k] for k in common_keys)
    norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
    norm_b = math.sqrt(sum(v * v for v in vec_b.values()))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return dot_product / (norm_a * norm_b)


def compute_item_similarities(
    item_user_matrix: Dict[Hashable, Dict[Hashable, float]],
    min_overlap: int = 1
) -> Dict[Hashable, Dict[Hashable, float]]:
    """
    Compute pairwise cosine similarities between all items.

    Args:
        item_user_matrix: {item_id: {user_id: rating}}.
        min_overlap: Minimum number of common users required to compute similarity.

    Returns:
        Nested dictionary {item_i: {item_j: similarity}}.
        Only similarities > 0 are stored; diagonal is omitted.

    Raises:
        ValueError: If item_user_matrix is empty or min_overlap < 1.
    """
    if not item_user_matrix:
        raise ValueError("Item-user matrix cannot be empty.")
    if min_overlap < 1:
        raise ValueError("min_overlap must be at least 1.")

    items = list(item_user_matrix.keys())
    similarities: Dict[Hashable, Dict[Hashable, float]] = defaultdict(dict)

    for i, item_i in enumerate(items):
        vec_i = item_user_matrix[item_i]
        for item_j in items[i + 1:]:
            vec_j = item_user_matrix[item_j]
            common_users = set(vec_i.keys()) & set(vec_j.keys())
            if len(common_users) < min_overlap:
                continue
            sim = cosine_similarity(vec_i, vec_j)
            if sim > 0:
                similarities[item_i][item_j] = sim
                similarities[item_j][item_i] = sim

    return {k: dict(v) for k, v in similarities.items()}


def predict_rating(
    user: Hashable,
    item: Hashable,
    user_item_matrix: Dict[Hashable, Dict[Hashable, float]],
    item_similarities: Dict[Hashable, Dict[Hashable, float]],
    k: int = 10
) -> Optional[float]:
    """
    Predict a user's rating for an item using weighted average of k most similar items.

    Args:
        user: Target user ID.
        item: Target item ID.
        user_item_matrix: {user_id: {item_id: rating}}.
        item_similarities: {item_id: {neighbor_item_id: similarity}}.
        k: Number of top similar items to consider.

    Returns:
        Predicted rating as float, or None if prediction is not possible.

    Raises:
        ValueError: If k <= 0.
        KeyError: If user not in user_item_matrix (handled gracefully, returns None).
    """
    if k <= 0:
        raise ValueError("k must be a positive integer.")

    if user not in user_item_matrix:
        return None

    user_ratings = user_item_matrix[user]
    if item in user_ratings:
        # Already rated; return actual rating (or could return None to indicate no prediction needed)
        return user_ratings[item]

    if item not in item_similarities:
        return None

    # Candidate neighbors: items the user has rated that are similar to target item
    neighbors = item_similarities[item]
    rated_neighbors = [(nbr, sim) for nbr, sim in neighbors.items() if nbr in user_ratings]
    if not rated_neighbors:
        return None

    # Select top-k by similarity
    rated_neighbors.sort(key=lambda x: x[1], reverse=True)
    top_k = rated_neighbors[:k]

    weighted_sum = 0.0
    sim_sum = 0.0
    for nbr, sim in top_k:
        rating = user_ratings[nbr]
        weighted_sum += sim * rating
        sim_sum += sim

    if sim_sum == 0.0:
        return None

    return weighted_sum / sim_sum


def recommend(
    user: Hashable,
    user_item_matrix: Dict[Hashable, Dict[Hashable, float]],
    item_similarities: Dict[Hashable, Dict[Hashable, float]],
    n: int = 10,
    k: int = 10
) -> List[Tuple[Hashable, float]]:
    """
    Generate top-N item recommendations for a user.

    Args:
        user: Target user ID.
        user_item_matrix: {user_id: {item_id: rating}}.
        item_similarities: {item_id: {neighbor_item_id: similarity}}.
        n: Number of recommendations to return.
        k: Number of similar items to use for each prediction.

    Returns:
        List of (item_id, predicted_rating) sorted by predicted_rating descending.
        Returns empty list if user unknown or no predictions possible.

    Raises:
        ValueError: If n <= 0 or k <= 0.
    """
    if n <= 0:
        raise ValueError("n must be a positive integer.")
    if k <= 0:
        raise ValueError("k must be a positive integer.")

    if user not in user_item_matrix:
        return []

    user_rated = set(user_item_matrix[user].keys())
    candidates = set(item_similarities.keys()) - user_rated
    if not candidates:
        return []

    predictions = []
    for item in candidates:
        pred = predict_rating(user, item, user_item_matrix, item_similarities, k)
        if pred is not None:
            predictions.append((item, pred))

    predictions.sort(key=lambda x: x[1], reverse=True)
    return predictions[:n]


def evaluate_rmse(
    test_data: List[Tuple[Hashable, Hashable, float]],
    user_item_matrix: Dict[Hashable, Dict[Hashable, float]],
    item_similarities: Dict[Hashable, Dict[Hashable, float]],
    k: int = 10
) -> float:
    """
    Evaluate the model using Root Mean Squared Error (RMSE) on test data.

    Args:
        test_data: List of (user, item, true_rating) tuples.
        user_item_matrix: Training user-item matrix (used for predictions).
        item_similarities: Precomputed item similarities.
        k: Number of neighbors for prediction.

    Returns:
        RMSE value. Returns float('nan') if no valid predictions.

    Raises:
        ValueError: If test_data is empty or k <= 0.
    """
    if not test_data:
        raise ValueError("Test data cannot be empty.")
    if k <= 0:
        raise ValueError("k must be a positive integer.")

    squared_errors = []
    for user, item, true_rating in test_data:
        pred = predict_rating(user, item, user_item_matrix, item_similarities, k)
        if pred is not None:
            squared_errors.append((pred - true_rating) ** 2)

    if not squared_errors:
        return float('nan')

    mse = sum(squared_errors) / len(squared_errors)
    return math.sqrt(mse)


class CollaborativeFilteringRecommender:
    """
    Item-based Collaborative Filtering Recommender.

    Encapsulates model building, recommendation, and evaluation.
    """

    def __init__(self, min_overlap: int = 1) -> None:
        """
        Initialize the recommender.

        Args:
            min_overlap: Minimum number of common users required to compute item similarity.
        """
        if min_overlap < 1:
            raise ValueError("min_overlap must be at least 1.")
        self.min_overlap = min_overlap
        self.user_item_matrix: Dict[Hashable, Dict[Hashable, float]] = {}
        self.item_user_matrix: Dict[Hashable, Dict[Hashable, float]] = {}
        self.item_similarities: Dict[Hashable, Dict[Hashable, float]] = {}
        self._is_fitted = False

    def fit(self, data: List[Tuple[Hashable, Hashable, float]]) -> None:
        """
        Train the model on rating data.

        Args:
            data: List of (user_id, item_id, rating) tuples.

        Raises:
            ValueError: If data is empty or invalid.
        """
        self.user_item_matrix, self.item_user_matrix = build_matrices(data)
        self.item_similarities = compute_item_similarities(
            self.item_user_matrix, min_overlap=self.min_overlap
        )
        self._is_fitted = True

    def predict(self, user: Hashable, item: Hashable, k: int = 10) -> Optional[float]:
        """
        Predict rating for a user-item pair.

        Args:
            user: User ID.
            item: Item ID.
            k: Number of similar items to use.

        Returns:
            Predicted rating or None if not possible.

        Raises:
            RuntimeError: If model not fitted.
            ValueError: If k <= 0.
        """
        self._check_fitted()
        return predict_rating(user, item, self.user_item_matrix, self.item_similarities, k)

    def recommend(self, user: Hashable, n: int = 10, k: int = 10) -> List[Tuple[Hashable, float]]:
        """
        Recommend top-N items for a user.

        Args:
            user: User ID.
            n: Number of recommendations.
            k: Number of similar items per prediction.

        Returns:
            List of (item_id, predicted_rating) sorted descending.

        Raises:
            RuntimeError: If model not fitted.
            ValueError: If n <= 0 or k <= 0.
        """
        self._check_fitted()
        return recommend(user, self.user_item_matrix, self.item_similarities, n, k)

    def evaluate(self, test_data: List[Tuple[Hashable, Hashable, float]], k: int = 10) -> float:
        """
        Compute RMSE on test data.

        Args:
            test_data: List of (user, item, true_rating).
            k: Number of neighbors for prediction.

        Returns:
            RMSE value.

        Raises:
            RuntimeError: If model not fitted.
            ValueError: If test_data empty or k <= 0.
        """
        self._check_fitted()
        return evaluate_rmse(test_data, self.user_item_matrix, self.item_similarities, k)

    def _check_fitted(self) -> None:
        """Raise RuntimeError if model has not been fitted."""
        if not self._is_fitted:
            raise RuntimeError("Model must be fitted before use. Call fit() first.")


# Example usage (can be removed or guarded under __main__)
if __name__ == "__main__":
    # Sample data: (user, item, rating)
    sample_data = [
        ("A", "Item1", 5.0), ("A", "Item2", 3.0), ("A", "Item3", 4.0),
        ("B", "Item1", 4.0), ("B", "Item2", 2.0), ("B", "Item4", 5.0),
        ("C", "Item1", 3.0), ("C", "Item3", 5.0), ("C", "Item4", 4.0),
        ("D", "Item2", 4.0), ("D", "Item3", 3.0), ("D", "Item4", 2.0),
    ]

    # Split into train/test (simple hold-out)
    train_data = sample_data[:9]
    test_data = sample_data[9:]

    model = CollaborativeFilteringRecommender(min_overlap=1)
    model.fit(train_data)

    # Recommend for user A
    recs = model.recommend("A", n=2, k=2)
    print(f"Recommendations for user A: {recs}")

    # Evaluate
    rmse = model.evaluate(test_data, k=2)
    print(f"RMSE on test set: {rmse:.4f}")