"""
Collaborative Filtering Recommender System

This module provides a complete implementation of a collaborative filtering
recommender system using cosine similarity on a user-item matrix.
It includes functionality for building the matrix, computing similarities,
generating top-N recommendations, and evaluating prediction accuracy.

Security: Inputs are validated; no unsafe deserialisation or dynamic code execution is used.
"""

import math
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import numpy as np
from numpy.typing import NDArray


def _validate_ratings(ratings: List[Tuple[Any, Any, float]]) -> None:
    """
    Validate the structure and content of the ratings list.

    Args:
        ratings: List of (user, item, score) tuples.

    Raises:
        ValueError: If ratings list is empty or contains invalid entries.
    """
    if not ratings:
        raise ValueError("Ratings list must not be empty.")
    for idx, entry in enumerate(ratings):
        if not isinstance(entry, tuple) or len(entry) != 3:
            raise ValueError(
                f"Invalid rating entry at index {idx}: expected (user, item, score) tuple."
            )
        user, item, score = entry
        if not isinstance(score, (int, float)):
            raise ValueError(
                f"Invalid score type at index {idx}: {type(score)}. Must be int or float."
            )
        if math.isnan(score) or math.isinf(score):
            raise ValueError(f"Score at index {idx} is NaN or Inf, which is not allowed.")


def build_user_item_matrix(
    ratings: List[Tuple[Any, Any, float]],
    min_ratings_per_user: int = 1,
    min_ratings_per_item: int = 1,
) -> Tuple[NDArray[np.float64], Dict[Any, int], Dict[Any, int]]:
    """
    Construct a dense user-item matrix from sparse rating tuples.

    Users and items are mapped to consecutive integer indices.
    Rows represent users, columns represent items.
    Missing ratings are filled with 0.0.

    Args:
        ratings: List of (user, item, score) tuples.
        min_ratings_per_user: Minimum number of ratings a user must have to be included.
        min_ratings_per_item: Minimum number of ratings an item must have to be included.

    Returns:
        Tuple containing:
            - 2D numpy array of shape [num_users, num_items] with dtype float64.
            - Dictionary mapping user ID to row index.
            - Dictionary mapping item ID to column index.

    Raises:
        ValueError: If after filtering no users or items remain.
    """
    _validate_ratings(ratings)

    user_counts: Dict[Any, int] = defaultdict(int)
    item_counts: Dict[Any, int] = defaultdict(int)

    for user, item, _ in ratings:
        user_counts[user] += 1
        item_counts[item] += 1

    valid_users = {u for u, c in user_counts.items() if c >= min_ratings_per_user}
    valid_items = {i for i, c in item_counts.items() if c >= min_ratings_per_item}

    if not valid_users:
        raise ValueError(
            "No users meet the minimum required ratings count "
            f"(min_ratings_per_user={min_ratings_per_user})."
        )
    if not valid_items:
        raise ValueError(
            "No items meet the minimum required ratings count "
            f"(min_ratings_per_item={min_ratings_per_item})."
        )

    user_to_idx: Dict[Any, int] = {}
    item_to_idx: Dict[str, int] = {}
    for idx, user in enumerate(sorted(valid_users, key=str)):
        user_to_idx[user] = idx
    for idx, item in enumerate(sorted(valid_items, key=str)):
        # item can be any hashable type; store as-is but use string key in dict
        item_to_idx[str(item)] = idx

    matrix = np.zeros((len(user_to_idx), len(item_to_idx)), dtype=np.float64)

    for user, item, score in ratings:
        if user in valid_users and item in valid_items:
            row = user_to_idx[user]
            col = item_to_idx[str(item)]
            matrix[row, col] = score

    return matrix, user_to_idx, item_to_idx


def cosine_similarity(matrix: NDArray[np.float64]) -> NDArray[np.float64]:
    """
    Compute user-user cosine similarity matrix.

    Similarity is defined as the cosine of the angle between two user vectors.
    Self-similarity is set to 0 to avoid recommending the user to themselves.

    Args:
        matrix: 2D numpy array of shape (num_users, num_items).

    Returns:
        Square similarity matrix of shape (num_users, num_users) with dtype float64.

    Raises:
        ValueError: If the input matrix is not 2D or is empty.
    """
    if matrix.ndim != 2:
        raise ValueError("Input matrix must be 2-dimensional.")
    if matrix.size == 0:
        raise ValueError("Input matrix must not be empty.")

    norms = np.linalg.norm(matrix, axis=1)
    # Avoid division by zero for users with no ratings (all zero vector)
    norms[norms == 0] = 1e-10
    normalized = matrix / norms[:, np.newaxis]
    similarity = np.dot(normalized, normalized.T)
    # Ensure diagonal is 1.0 for valid comparisons; set to 0 to ignore self
    np.fill_diagonal(similarity, 0.0)
    # Clip to handle floating point inaccuracies
    similarity = np.clip(similarity, -1.0, 1.0)
    return similarity


def recommend_items(
    user_id: Any,
    user_to_idx: Dict[Any, int],
    item_to_idx: Dict[str, int],
    matrix: NDArray[np.float64],
    similarity: NDArray[np.float64],
    top_n: int = 5,
    exclude_rated: bool = True,
) -> List[Tuple[Any, float]]:
    """
    Generate top-N item recommendations for a given user.

    Predictions are computed as a weighted average of ratings from similar users.
    Items already rated by the target user can be excluded.

    Args:
        user_id: The ID of the target user.
        user_to_idx: Mapping from user ID to matrix row index.
        item_to_idx: Mapping from item ID (str) to matrix column index.
        matrix: User-item rating matrix.
        similarity: User-user similarity matrix.
        top_n: Number of recommendations to return.
        exclude_rated: If True, exclude items the user has already rated.

    Returns:
        List of (item_id, predicted_score) tuples sorted by descending score.

    Raises:
        ValueError: If user_id is not found in the index, or top_n <= 0.
    """
    if user_id not in user_to_idx:
        raise ValueError(f"User ID '{user_id}' not found in the user index.")
    if top_n <= 0:
        raise ValueError("top_n must be a positive integer.")

    user_row = user_to_idx[user_id]
    sim_vector = similarity[user_row]  # shape (num_users,)

    # Find neighbors with positive similarity (exclude self, which is 0)
    neighbor_mask = sim_vector > 0
    if not np.any(neighbor_mask):
        return []

    sim_weights = sim_vector[neighbor_mask]
    neighbor_ratings = matrix[neighbor_mask]  # (num_neighbors, num_items)

    # Weighted sum of neighbor ratings
    weighted_sum = np.dot(sim_weights, neighbor_ratings)  # (num_items,)
    # Normalize by sum of similarities (avoid division by zero)
    norm = np.sum(sim_weights)
    if norm == 0:
        return []
    predictions = weighted_sum / norm

    # Exclude already rated items if requested
    if exclude_rated:
        rated_mask = matrix[user_row] > 0
        predictions[rated_mask] = -np.inf

    # Get top-N indices
    if top_n >= len(predictions):
        candidate_indices = np.argsort(predictions)[::-1]
    else:
        # Use argpartition for efficiency
        candidate_indices = np.argpartition(predictions, -top_n)[-top_n:]
        candidate_indices = candidate_indices[np.argsort(predictions[candidate_indices])[::-1]]

    # Map indices back to item IDs
    idx_to_item = {v: k for k, v in item_to_idx.items()}
    recommendations = []
    for col in candidate_indices:
        score = predictions[col]
        if np.isneginf(score):
            continue
        item_id = idx_to_item[col]
        recommendations.append((item_id, float(score)))
        if len(recommendations) == top_n:
            break

    return recommendations


def evaluate_recommender(
    ratings: List[Tuple[Any, Any, float]],
    test_pairs: Set[Tuple[Any, Any]],
    top_n: int = 5,
    min_ratings_per_user: int = 1,
    min_ratings_per_item: int = 1,
) -> Dict[str, float]:
    """
    Evaluate the recommender using hold-out test pairs.

    The function builds the model on all provided ratings, then for each user in
    the test set, generates recommendations and measures hit-rate and
    precision@k.

    Args:
        ratings: Training ratings as (user, item, score) tuples.
        test_pairs: Set of (user, item) tuples that are held out for evaluation.
        top_n: Number of recommendations considered for precision.
        min_ratings_per_user: Minimum training ratings per user.
        min_ratings_per_item: Minimum training ratings per item.

    Returns:
        Dictionary with evaluation metrics: 'hit_rate', 'precision_at_k'.

    Raises:
        ValueError: If no test pairs are provided or if model building fails.
    """
    if not test_pairs:
        raise ValueError("Test pairs set must not be empty.")

    try:
        train_matrix, user_to_idx, item_to_idx = build_user_item_matrix(
            ratings,
            min_ratings_per_user=min_ratings_per_user,
            min_ratings_per_item=min_ratings_per_item,
        )
    except ValueError as exc:
        raise ValueError(f"Failed to build training matrix: {exc}") from exc

    similarity = compute_similarity(train_matrix)

    # Group test pairs by user
    user_test_items: Dict[Any, Set[Any]] = defaultdict(set)
    for user, item in test_pairs:
        user_test_items[user].add(item)

    hits = 0
    total_test_users = 0
    precision_sum = 0.0

    for user, true_items in user_test_items.items():
        if user not in user_to_idx:
            continue
        total_test_users += 1
        try:
            recs = recommend_items(
                user_id=user,
                user_to_idx=user_to_idx,
                item_to_idx=item_to_idx,
                matrix=train_matrix,
                similarity=similarity,
                top_n=top_n,
                exclude_rated=True,
            )
        except ValueError:
            continue

        rec_items = {item for item, _ in recs}
        hit = not rec_items.isdisjoint(true_items)
        if hit:
            hits += 1
        # Precision@k: fraction of recommended items that are in test set
        precision_sum += len(rec_items & test_items) / top_n

    if total_test_users == 0:
        return {"hit_rate": 0.0, "precision_at_k": 0.0}

    hit_rate = hits / total_test_users
    precision_at_k = precision_sum / total_test_users
    return {"hit_rate": hit_rate, "precision_at_k": precision_at_k}


def recommend_train_matrix(
    user_id: Any,
    user_to_idx: Dict[Any, int],
    item_to_idx: Dict[str, int],
    matrix: NDArray[np.float64],
    similarity: NDArray[np.float64],
    top_n: int = 5,
    exclude_rated: bool = True,
) -> List[Tuple[Any, float]]:
    """
    Wrapper around recommend_items that accepts Any user_id.

    This function is used internally by evaluate_recommender to map user_id
    to row index before calling the core recommendation logic.

    Args:
        user_id: User identifier (any hashable type).
        user_to_idx: Mapping from user ID to matrix row index.
        item_to_idx: Mapping from item ID (str) to matrix column index.
        matrix: User-item matrix.
        similarity: User-user similarity matrix.
        top_n: Number of recommendations.
        exclude_rated: Whether to exclude already rated items.

    Returns:
        List of (item_id, score) tuples.
    """
    if user_id not in user_to_idx:
        raise ValueError(f"User ID '{user_id}' not found.")
    return recommend_items(
        user_to_idx[user_id],
        user_to_idx,
        item_to_idx,
        matrix,
        similarity,
        top_n,
        exclude_rated,
    )


# Example usage (not executed on import)
if __name__ == "__main__":
    # Example data
    example_ratings = [
        ("Alice", "ItemA", 5.0),
        ("Alice", "ItemB", 3.0),
        ("Bob", "ItemA", 4.0),
        ("Bob", "ItemC", 2.0),
        ("Charlie", "ItemB", 4.0),
        ("Charlie", "ItemC", 5.0),
    ]
    test = {("Alice", "ItemC"), ("Bob", "ItemB"), ("Charlie", "ItemA")}

    try:
        matrix, u2i, i2i = build_user_item_matrix(example_ratings)
        sim = compute_similarity(matrix)
        recs = recommend_items("Alice", u2i, i2i, matrix, sim, top_n=2)
        print("Recommendations for Alice:", recs)
        metrics = evaluate_recommender(example_ratings, test, top_n=2)
        print("Evaluation metrics:", metrics)
    except Exception as e:
        print("Error:", e)