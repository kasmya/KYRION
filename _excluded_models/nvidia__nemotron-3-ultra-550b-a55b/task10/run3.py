"""
Collaborative Filtering Recommender System

This module implements a user-based collaborative filtering recommender using cosine similarity.
It includes functions for building a user-item matrix, computing user similarities,
generating top-N recommendations, and evaluating the model with precision@k and recall@k.

All functions include type hints, docstrings, and explicit error handling.
Only Python standard library modules are used.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Dict, Hashable, List, Tuple, Set, Any


def build_user_item_matrix(
    interactions: List[Tuple[Hashable, Hashable, float]]
) -> Dict[Hashable, Dict[Hashable, float]]:
    """
    Build a user-item matrix from interaction data.

    Args:
        interactions: List of (user_id, item_id, rating) tuples.

    Returns:
        Nested dictionary mapping user_id -> {item_id: rating}.

    Raises:
        ValueError: If interactions list is empty or contains invalid tuples.
        TypeError: If interactions is not a list or tuple elements are not hashable.
    """
    if not interactions:
        raise ValueError("Interactions list cannot be empty")

    user_item_matrix: Dict[Hashable, Dict[Hashable, float]] = defaultdict(dict)

    for idx, interaction in enumerate(interactions):
        if not isinstance(interaction, tuple) or len(interaction) != 3:
            raise ValueError(f"Interaction at index {idx} must be a 3-tuple (user, item, rating)")

        user, item, rating = interaction

        try:
            hash(user)
            hash(item)
        except TypeError as e:
            raise TypeError(f"User and item IDs must be hashable: {e}")

        if not isinstance(rating, (int, float)):
            raise TypeError(f"Rating must be numeric, got {type(rating)}")

        user_item_matrix[user][item] = float(rating)

    return dict(user_item_matrix)


def compute_cosine_similarity(
    user_ratings1: Dict[Hashable, float],
    user_ratings2: Dict[Hashable, float]
) -> float:
    """
    Compute cosine similarity between two users' rating vectors.

    Args:
        user_ratings1: Dictionary of item_id -> rating for user 1.
        user_ratings2: Dictionary of item_id -> rating for user 2.

    Returns:
        Cosine similarity score between -1.0 and 1.0.

    Raises:
        ValueError: If either rating dictionary is empty.
    """
    if not user_ratings1 or not user_ratings2:
        raise ValueError("Rating dictionaries cannot be empty")

    # Find common items
    common_items: Set[Hashable] = set(user_ratings1.keys()) & set(user_ratings2.keys())

    if not common_items:
        return 0.0

    # Compute dot product and magnitudes
    dot_product = sum(user_ratings1[item] * user_ratings2[item] for item in common_items)
    magnitude1 = math.sqrt(sum(r * r for r in user_ratings1.values()))
    magnitude2 = math.sqrt(sum(r * r for r in user_ratings2.values()))

    if magnitude1 == 0.0 or magnitude2 == 0.0:
        return 0.0

    return dot_product / (magnitude1 * magnitude2)


def compute_all_user_similarities(
    user_item_matrix: Dict[Hashable, Dict[Hashable, float]]
) -> Dict[Hashable, Dict[Hashable, float]]:
    """
    Compute pairwise cosine similarities between all users.

    Args:
        user_item_matrix: User-item matrix from build_user_item_matrix.

    Returns:
        Nested dictionary mapping user1 -> {user2: similarity}.

    Raises:
        ValueError: If user_item_matrix is empty or has fewer than 2 users.
    """
    if not user_item_matrix:
        raise ValueError("User-item matrix cannot be empty")

    users = list(user_item_matrix.keys())
    if len(users) < 2:
        raise ValueError("At least two users are required to compute similarities")

    similarities: Dict[Hashable, Dict[Hashable, float]] = defaultdict(dict)

    for i, user1 in enumerate(users):
        ratings1 = user_item_matrix[user1]
        for user2 in users[i + 1:]:
            ratings2 = user_item_matrix[user2]
            try:
                sim = compute_cosine_similarity(ratings1, ratings2)
            except ValueError:
                sim = 0.0
            similarities[user1][user2] = sim
            similarities[user2][user1] = sim

    return dict(similarities)


def get_top_n_recommendations(
    user: Hashable,
    user_item_matrix: Dict[Hashable, Dict[Hashable, float]],
    user_similarities: Dict[Hashable, Dict[Hashable, float]],
    n: int = 10,
    min_similarity: float = 0.0
) -> List[Tuple[Hashable, float]]:
    """
    Generate top-N item recommendations for a user using weighted average of similar users' ratings.

    Args:
        user: Target user ID.
        user_item_matrix: User-item matrix.
        user_similarities: Precomputed user-user similarities.
        n: Number of recommendations to return.
        min_similarity: Minimum similarity threshold for considering a neighbor.

    Returns:
        List of (item_id, predicted_score) tuples sorted by predicted_score descending.

    Raises:
        KeyError: If user not found in user_item_matrix or user_similarities.
        ValueError: If n <= 0.
    """
    if n <= 0:
        raise ValueError("n must be positive")

    if user not in user_item_matrix:
        raise KeyError(f"User {user} not found in user-item matrix")

    if user not in user_similarities:
        raise KeyError(f"User {user} not found in similarity matrix")

    user_rated_items = set(user_item_matrix[user].keys())
    candidate_scores: Dict[Hashable, Tuple[float, float]] = defaultdict(lambda: (0.0, 0.0))  # (weighted_sum, weight_sum)

    for neighbor, similarity in user_similarities[user].items():
        if similarity <= min_similarity or neighbor == user:
            continue

        neighbor_ratings = user_item_matrix[neighbor]
        for item, rating in neighbor_ratings.items():
            if item in user_rated_items:
                continue
            weighted_sum, weight_sum = candidate_scores[item]
            candidate_scores[item] = (weighted_sum + similarity * rating, weight_sum + abs(similarity))

    # Compute predicted scores
    predictions: List[Tuple[Hashable, float]] = []
    for item, (weighted_sum, weight_sum) in candidate_scores.items():
        if weight_sum > 0:
            predicted_score = weighted_sum / weight_sum
            predictions.append((item, predicted_score))

    # Sort by predicted score descending
    predictions.sort(key=lambda x: x[1], reverse=True)

    return predictions[:n]


def evaluate_recommender(
    test_interactions: List[Tuple[Hashable, Hashable, float]],
    user_item_matrix: Dict[Hashable, Dict[Hashable, float]],
    user_similarities: Dict[Hashable, Dict[Hashable, float]],
    n: int = 10,
    relevance_threshold: float = 3.5
) -> Dict[str, float]:
    """
    Evaluate recommender using Precision@N and Recall@N.

    Args:
        test_interactions: Held-out interactions for evaluation.
        user_item_matrix: Training user-item matrix.
        user_similarities: Precomputed user-user similarities.
        n: Number of recommendations to consider.
        relevance_threshold: Minimum rating to consider an item relevant.

    Returns:
        Dictionary with 'precision_at_n', 'recall_at_n', 'f1_at_n'.

    Raises:
        ValueError: If test_interactions is empty or n <= 0.
    """
    if not test_interactions:
        raise ValueError("Test interactions cannot be empty")
    if n <= 0:
        raise ValueError("n must be positive")

    # Build ground truth relevant items per user
    ground_truth: Dict[Hashable, Set[Hashable]] = defaultdict(set)
    for user, item, rating in test_interactions:
        if rating >= relevance_threshold:
            ground_truth[user].add(item)

    if not ground_truth:
        return {"precision_at_n": 0.0, "recall_at_n": 0.0, "f1_at_n": 0.0}

    total_precision = 0.0
    total_recall = 0.0
    evaluated_users = 0

    for user, relevant_items in ground_truth.items():
        if user not in user_item_matrix:
            continue

        try:
            recommendations = get_top_n_recommendations(user, user_item_matrix, user_similarities, n)
        except KeyError:
            continue

        recommended_items = {item for item, _ in recommendations}
        if not recommended_items:
            continue

        hits = len(recommended_items & relevant_items)
        precision = hits / len(recommended_items)
        recall = hits / len(relevant_items) if relevant_items else 0.0

        total_precision += precision
        total_recall += recall
        evaluated_users += 1

    if evaluated_users == 0:
        return {"precision_at_n": 0.0, "recall_at_n": 0.0, "f1_at_n": 0.0}

    avg_precision = total_precision / evaluated_users
    avg_recall = total_recall / evaluated_users

    if avg_precision + avg_recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * avg_precision * avg_recall / (avg_precision + avg_recall)

    return {
        "precision_at_n": avg_precision,
        "recall_at_n": avg_recall,
        "f1_at_n": f1
    }


if __name__ == "__main__":
    # Example usage with synthetic data
    sample_interactions = [
        ("user1", "item1", 5.0), ("user1", "item2", 4.0), ("user1", "item3", 3.0),
        ("user2", "item1", 4.0), ("user2", "item2", 5.0), ("user2", "item4", 2.0),
        ("user3", "item2", 3.0), ("user3", "item3", 4.0), ("user3", "item5", 5.0),
        ("user4", "item1", 2.0), ("user4", "item4", 4.0), ("user4", "item5", 3.0),
    ]

    # Split into train/test (simple hold-out)
    train_interactions = sample_interactions[:8]
    test_interactions = sample_interactions[8:]

    try:
        # Build model
        user_item_matrix = build_user_item_matrix(train_interactions)
        user_similarities = compute_all_user_similarities(user_item_matrix)

        # Get recommendations for user1
        recs = get_top_n_recommendations("user1", user_item_matrix, user_similarities, n=3)
        print(f"Top-3 recommendations for user1: {recs}")

        # Evaluate
        metrics = evaluate_recommender(test_interactions, user_item_matrix, user_similarities, n=3)
        print(f"Evaluation metrics: {metrics}")

    except (ValueError, KeyError, TypeError) as e:
        print(f"Error: {e}")