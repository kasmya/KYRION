"""
Collaborative Filtering Recommender System

This module implements a collaborative-filtering recommender using a user-item matrix.
It provides functionality to build the matrix from raw data, compute cosine similarity
between users, generate top-N item recommendations, and evaluate the model using
precision, recall, and RMSE metrics.

Security: Input validation is performed on all public functions. Data is sanitized
to prevent injection or malformed structures. Only standard library and widely-used
PyPI packages (numpy, scipy) are used.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import numpy as np
from scipy.sparse import csr_matrix, lil_matrix
from scipy.sparse.linalg import norm

# Configure module-level logger
logger = logging.getLogger(__name__)


def _validate_ratings(ratings: List[Dict[str, Any]]) -> None:
    """
    Validate structure and data types of rating records.

    Each record must be a dict with keys: user_id, item_id, rating.
    user_id and item_id must be hashable (str or int). rating must be numeric.

    Args:
        ratings: List of rating dictionaries.

    Raises:
        ValueError: If any rating record is invalid.
    """
    if not isinstance(ratings, list):
        raise ValueError("Ratings must be provided as a list of dictionaries.")
    for idx, record in enumerate(ratings):
        if not isinstance(record, dict):
            raise ValueError(f"Record at index {idx} is not a dictionary.")
        for key in ("user_id", "item_id", "rating"):
            if key not in record:
                raise ValueError(f"Record at index {idx} is missing required key '{key}'.")
        if not isinstance(record["user_id"], (str, int)):
            raise ValueError(f"'user_id' at index {idx} must be str or int.")
        if not isinstance(record["item_id"], (str, int)):
            raise ValueError(f"'item_id' at index {idx} must be str or int.")
        if not isinstance(record["rating"], (int, float, np.integer, np.floating)):
            raise ValueError(f"'rating' at index {idx} must be numeric.")


def _map_ids_to_indices(ids: List[str]) -> Tuple[Dict[str, int], List[str]]:
    """
    Create mapping from id to integer index and reverse mapping.

    Args:
        ids: List of string or integer identifiers.

    Returns:
        Tuple of (id_to_index dict, index_to_id list).
    """
    id_to_idx: Dict[str, int] = {}
    idx_to_id: List[str] = []
    for id_ in ids:
        id_str = str(id_)
        if id_str not in id_to_idx:
            id_to_idx[id_str] = len(idx_to_id)
            idx_to_id.append(id_str)
    return id_to_idx, idx_to_id


def build_user_item_matrix(
    ratings: List[Dict[str, Any]],
    min_ratings_per_user: int = 0,
    min_ratings_per_item: int = 0,
) -> Tuple[csr_matrix, Dict[str, int], Dict[str, int], List[str], List[str]]:
    """
    Build a sparse user-item rating matrix from a list of rating records.

    Args:
        ratings: List of dictionaries, each with keys 'user_id', 'item_id', 'rating'.
        min_ratings_per_user: Minimum number of ratings a user must have to be retained.
        min_ratings_per_item: Minimum number of ratings an item must have to be retained.

    Returns:
        Tuple containing:
            - Sparse CSR matrix of shape (num_users, num_items).
            - Mapping from user_id to row index.
            - Mapping from item_id to column index.
            - List of user IDs in row order.
            - List of item IDs in column order.

    Raises:
        ValueError: If ratings list is empty or contains invalid data.
    """
    if not ratings:
        raise ValueError("Ratings list cannot be empty.")
    _validate_ratings(ratings)

    # Filter users and items based on min thresholds
    user_counts: Dict[str, int] = {}
    item_counts: Dict[str, int] = {}
    for r in ratings:
        uid = str(r["user_id"])
        iid = str(r["item_id"])
        user_counts[uid] = user_counts.get(uid, 0) + 1
        item_counts[iid] = item_counts.get(iid, 0) + 1

    valid_users: Set[str] = {uid for uid, cnt in user_counts.items() if cnt >= min_ratings_per_user}
    valid_items: Set[str] = {iid for iid, cnt in item_counts.items() if cnt >= min_ratings_per_item}

    if not valid_users or not valid_items:
        raise ValueError("No users or items meet the minimum rating thresholds.")

    # Create ID mappings
    user_to_idx, user_list = _map_ids_to_indices(list(valid_users))
    item_to_idx, item_list = _map_ids_to_indices(list(valid_items))

    # Build sparse matrix
    matrix = lil_matrix((len(user_list), len(item_list)), dtype=np.float64)
    for rec in ratings:
        uid = str(rec["user_id"])
        iid = str(rec["item_id"])
        if uid in valid_users and iid in valid_items:
            row = user_to_idx[uid]
            col = item_to_idx[iid]
            rating = float(rec["rating"])
            matrix[row, col] = rating

    return csr_matrix(matrix), user_to_idx, item_to_idx, user_list, item_list


def _cosine_similarity_sparse(matrix: csr_matrix) -> np.ndarray:
    """
    Compute pairwise cosine similarity between rows (users) of a sparse matrix.

    Args:
        matrix: Sparse user-item matrix (users x items).

    Returns:
        Dense 2D numpy array of shape (num_users, num_users).
    """
    # Normalize rows to unit vectors (handle zero rows)
    norms = norm(matrix, axis=1)
    # Avoid division by zero: replace 0 norms with 1 to get zero similarity later
    norms[norms == 0] = 1
    normalized = matrix.multiply(1.0 / norms.reshape(-1, 1))
    # Cosine similarity = dot product of normalized vectors
    similarity = normalized.dot(normalized.T).toarray()
    # Ensure diagonal is 1 for non-zero users
    np.fill_diagonal(similarity, np.where(norms > 0, 1.0, 0.0))
    return similarity


def recommend_items(
    user_id: str,
    user_item_matrix: csr_matrix,
    user_to_idx: Dict[str, int],
    item_to_idx: Dict[str, int],
    user_similarity: np.ndarray,
    n_recommendations: int = 5,
    exclude_rated: bool = True,
) -> List[Tuple[str, float]]:
    """
    Generate top-N item recommendations for a given user using user-based collaborative filtering.

    Args:
        user_id: Target user identifier.
        user_item_matrix: Sparse user-item rating matrix.
        user_to_idx: Mapping from user_id to row index.
        item_to_idx: Mapping from item_id to column index.
        user_similarity: Precomputed user-user cosine similarity matrix.
        n_recommendations: Number of items to recommend.
        exclude_rated: If True, exclude items already rated by the user.

    Returns:
        List of tuples (item_id, predicted_score) sorted by descending score.

    Raises:
        ValueError: If user_id is unknown or parameters are invalid.
    """
    if user_id not in user_to_idx:
        raise ValueError(f"User '{user_id}' not found in user mapping.")
    if n_recommendations < 1:
        raise ValueError("n_recommendations must be a positive integer.")
    if not isinstance(user_item_matrix, csr_matrix):
        raise ValueError("user_item_matrix must be a scipy.sparse.csr_matrix.")
    if user_similarity.shape[0] != user_item_matrix.shape[0]:
        raise ValueError("Similarity matrix dimensions do not match user count.")

    user_idx = user_to_idx[user_id]
    num_items = user_item_matrix.shape[1]

    # User's similarity to all others
    sim_vector = user_similarity[user_idx]

    # Compute weighted sum of ratings from all users
    # Avoid using user's own rating (set similarity to 0 for self)
    sim_vector = np.copy(sim_vector)
    sim_vector[user_idx] = 0.0

    # Weighted score: similarity * ratings, summed over users
    # Use sparse dot product: (1 x users) * (users x items)
    # sim_vector is dense, matrix is sparse
    predicted_scores = sim_vector @ user_item_matrix.toarray()  # TODO: optimize for large matrices
    # Normalize by sum of absolute similarities (to avoid division by zero)
    sim_abs_sum = np.sum(np.abs(sim_vector))
    if sim_abs_sum > 0:
        predicted_scores /= sim_abs_sum

    # Create list of (item_id, score)
    idx_to_item = {v: k for k, v in item_to_idx.items()}
    item_scores = []
    for col in range(num_items):
        item_id = idx_to_item[col]
        score = predicted_scores[col]
        item_scores.append((item_id, score))

    # Exclude already rated items if requested
    if exclude_rated:
        user_ratings = user_item_matrix[user_idx].nonzero()[1]
        rated_cols = set(user_ratings)
        item_scores = [
            (item_id, score)
            for col, (item_id, score) in enumerate(item_scores)
            if col not in rated_cols
        ]

    # Sort by score descending
    item_scores.sort(key=lambda x: x[1], reverse=True)

    # Return top N
    return item_scores[:n_recommendations]


def evaluate_recommender(
    ratings: List[Dict[str, Any]],
    user_item_matrix: csr_matrix,
    user_to_idx: Dict[str, int],
    item_to_idx: Dict[str, int],
    user_similarity: np.ndarray,
    n_recommendations: int = 5,
    test_fraction: float = 0.2,
    random_seed: int = 42,
) -> Dict[str, float]:
    """
    Evaluate the recommender using precision, recall, and RMSE on a held-out test set.

    This function performs a single train/test split, hiding a fraction of each user's
    ratings as test data.

    Args:
        ratings: Original list of rating records.
        user_item_matrix: Full user-item matrix (used to compute similarity).
        user_to_idx: User ID to row index mapping.
        item_to_idx: Item ID to column index mapping.
        user_similarity: Precomputed user-user similarity matrix.
        n_recommendations: Number of items to recommend per user for evaluation.
        test_fraction: Fraction of ratings to hold out per user (0 < fraction < 1).
        random_seed: Seed for reproducibility.

    Returns:
        Dictionary with keys 'precision', 'recall', 'rmse'.

    Raises:
        ValueError: If parameters are invalid or no test ratings can be generated.
    """
    if not 0 < test_fraction < 1:
        raise ValueError("test_fraction must be between 0 and 1 (exclusive).")
    if n_recommendations < 1:
        raise ValueError("n_recommendations must be positive.")

    rng = np.random.default_rng(random_seed)

    # Build per-user list of item indices
    user_rated_items: Dict[str, List[int]] = {}
    for rec in ratings:
        uid = str(rec["user_id"])
        iid = str(rec["item_id"])
        if uid in user_to_idx and iid in item_to_idx:
            item_col = item_to_idx[iid]
            user_rated_items.setdefault(uid, []).append(item_col)

    if not user_rated_items:
        raise ValueError("No valid ratings available for evaluation.")

    # Split: for each user, randomly select test items
    train_ratings: List[Dict[str, Any]] = []
    test_pairs: List[Tuple[str, int, float]] = []  # (user_id, item_col, true_rating)
    test_items_per_user: Dict[str, Set[int]] = {}
    for uid, items in user_rated_items.items():
        if len(items) < 2:
            # Need at least two ratings to leave one out
            continue
        n_test = max(1, int(len(items) * test_fraction))
        test_indices = rng.choice(items, size=n_test, replace=False).tolist()
        test_set = set(test_indices)
        test_items_per_user[uid] = test_set
        for col in items:
            # Find original rating value
            rating_val = user_item_matrix[user_to_idx[uid], col]
            if col in test_set:
                test_pairs.append((uid, col, rating_val))
            else:
                # Keep in train matrix
                test_ratings.append({
                    "user_id": uid,
                    "item_id": list(item_to_idx.keys())[col],
                    "rating": rating_val,
                })

    if not test_pairs:
        raise ValueError("Not enough ratings to create test set. Use a smaller test_fraction or more data.")

    # Build train matrix from remaining ratings
    try:
        train_matrix, train_user_to_idx, train_item_to_idx, _, _ = build_user_item_matrix(
            train_ratings,
            min_ratings_per_user=1,
            min_ratings_per_item=1,
        )
    except ValueError as e:
        raise ValueError(f"Failed to build train matrix: {e}")

    # Recompute similarity on train matrix
    train_similarity = _cosine_similarity_sparse(train_matrix)

    # Evaluation metrics
    hits_at_k = 0
    total_recommended = 0
    total_test = len(test_pairs)
    sum_sq_errors = 0.0
    rating_predictions = 0

    # For each user in test set, get recommendations and check hits
    for uid, test_item_col, true_rating in test_pairs:
        if uid not in train_user_to_idx:
            continue
        try:
            recs = recommend_items(
                user_id=uid,
                user_item_matrix=train_matrix,
                user_to_idx=train_user_to_idx,
                item_to_idx=train_item_to_idx,
                user_similarity=train_similarity,
                n_recommendations=n_recommendations,
                exclude_rated=True,
            )
        except ValueError:
            continue

        # Check if test item is in recommended list
        test_item_id = list(item_to_idx.keys())[test_item_col]
        recommended_ids = {item_id for item_id, _ in recs}
        if test_item_id in recommended_ids:
            hits += 1

        # For RMSE: predict rating for test item using collaborative filtering
        # Use train_matrix and similarity to predict rating
        user_idx = train_user_to_idx[uid]
        sim_vector = train_similarity[user_idx]
        sim_vector[user_idx] = 0.0
        # Get column index in train matrix
        if test_item_id not in train_item_to_idx:
            # Item not in train matrix (rare), skip
            continue
        item_col = train_item_to_idx[test_item_id]
        # Predicted rating = weighted average of other users' ratings for this item
        other_ratings = train_matrix[:, item_col].toarray().flatten()
        numerator = np.dot(sim_vector, other_ratings)
        denominator = np.sum(np.abs(sim_vector))
        if denominator > 0:
            pred_rating = numerator / denominator
            sq_error = (pred_rating - true_rating) ** 2
            sum_sq_errors += sq_error
            pred_count += 1

    precision = hits / n_recommendations if n_recommendations > 0 else 0.0
    recall = hits / total_test if total_test > 0 else 0.0
    rmse = np.sqrt(sum_sq_errors / rating_predictions) if rating_predictions > 0 else float("nan")

    return {
        "precision": precision,
        "recall": recall,
        "rmse": rmse,
    }


def load_ratings_from_csv(
    file_path: Union[str, Path],
    user_col: str = "user_id",
    item_col: str = "item_id",
    rating_col: str = "rating",
    has_header: bool = True,
) -> List[Dict[str, Any]]:
    """
    Load ratings from a CSV file.

    Args:
        file_path: Path to the CSV file.
        user_col: Column name for user IDs.
        item_col: Column name for item IDs.
        rating_col: Column name for ratings.
        has_header: Whether the CSV has a header row.

    Returns:
        List of rating dictionaries.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file format is invalid.
    """
    path = Path(file_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    ratings: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f) if has_header else csv.reader(f)
            if not has_header:
                # Assume columns are in order user_id, item_id, rating
                for row in reader:
                    if len(row) < 3:
                        continue
                    ratings.append({
                        "user_id": row[0].strip(),
                        "item_id": row[1].strip(),
                        "rating": float(row[2]),
                    })
            else:
                for row in reader:
                    ratings.append({
                        "user_id": row[user_col].strip(),
                        "item_id": row[item_col].strip(),
                        "rating": float(row[rating_col]),
                    })
    except (csv.Error, UnicodeDecodeError) as e:
        raise ValueError(f"Error reading CSV file: {e}")
    return ratings


# Example usage and simple demonstration
if __name__ == "__main__":
    # Sample data for demonstration
    sample_ratings = [
        {"user_id": "Alice", "item