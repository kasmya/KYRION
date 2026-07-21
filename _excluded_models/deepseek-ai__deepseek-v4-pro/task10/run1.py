"""
Collaborative Filtering Recommender System

This module provides a complete collaborative-filtering recommender system.
It builds a user-item matrix from raw ratings data, computes cosine similarity
between users or items, generates top-N recommendations, and evaluates
the quality of recommendations using standard metrics.

Supported functionality:
- Build user-item matrix from list of (user, item, rating) tuples
- Compute cosine similarity matrix
- Generate top-N item recommendations for a given user
- Evaluate recommendations using Precision@k and Recall@k
"""

from __future__ import annotations

import csv
import math
import os
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import numpy as np


class CollaborativeFilteringRecommender:
    """
    A collaborative-filtering recommender system.

    Attributes:
        user_item_matrix (np.ndarray): A 2D array where rows represent users and columns represent items.
        user_ids (List[str]): Ordered list of user identifiers corresponding to matrix rows.
        item_ids (List[str]): Ordered list of item identifiers corresponding to matrix columns.
        user_index (Dict[str, int]): Mapping from user ID to row index.
        item_index (Dict[str, int]): Mapping from item ID to column index.
        similarity_matrix (Optional[np.ndarray]): Precomputed similarity matrix (items x items).
    """

    def __init__(self) -> None:
        """Initialize an empty recommender system."""
        self.scores_matrix: Optional[np.ndarray] = None
        self.user_ids: List[str] = []
        self.item_ids: List[str] = []
        self.user_to_idx: Dict[str, int] = {}
        self.item_to_idx: Dict[str, int] = {}
        self.similarity_matrix: Optional[np.ndarray] = None

    def build_matrix(self, ratings: List[Tuple[str, str, float]]) -> None:
        """
        Build a user-item rating matrix from rating tuples.

        Args:
            ratings: A list of (user_id, item_id, rating) tuples.

        Raises:
            ValueError: If ratings list is empty or contains invalid data.
            TypeError: If rating values are not numeric.
        """
        if not ratings:
            raise ValueError("Ratings list cannot be empty.")

        user_ids_set: Set[str] = set()
        item_ids_set: Set[str] = set()
        cleaned_ratings: List[Tuple[str, str, float]] = []

        for user, item, rating in ratings:
            if not isinstance(user, str) or not isinstance(item, str):
                raise ValueError("User and item IDs must be strings.")
            if not isinstance(rating, (int, float)):
                raise TypeError(f"Rating for user {user} and item {item} must be numeric.")
            if math.isnan(float(rating)) or math.isinf(float(rating)):
                raise ValueError(f"Rating for user {user} and item {item} is not finite.")
            user_ids_set.add(user)
            item_ids_set.add(item)
            cleaned_ratings.append((user, item, float(rating)))

        self.user_ids = sorted(user_ids_set)
        self.item_ids = sorted(item_ids_set)

        if not self.user_ids or not self.item_ids:
            raise ValueError("No valid users or items found after processing ratings.")

        self.user_to_idx = {user: idx for idx, user in enumerate(self.user_ids)}
        self.item_to_idx = {item: idx for idx, item in enumerate(self.item_ids)}

        num_users = len(self.user_ids)
        num_items = len(self.item_ids)

        self.scores_matrix = np.full((num_users, num_items), np.nan)

        for user, item, rating in cleaned_ratings:
            user_idx = self.user_to_idx[user]
            item_idx = self.item_to_idx[item]
            self.scores_matrix[user_idx, item_idx] = rating

    def compute_similarity(self, item_based: bool = True) -> np.ndarray:
        """
        Compute cosine similarity between items (or users).

        Args:
            item_based: If True, compute item-item similarity; otherwise user-user.

        Returns:
            A 2D numpy array of cosine similarities.

        Raises:
            RuntimeError: If the user-item matrix has not been built.
        """
        if self.scores_matrix is None:
            raise RuntimeError("User-item matrix has not been built. Call build_matrix() first.")

        if item_based:
            # Compute item-item similarity
            matrix = self.scores_matrix.T
        else:
            matrix = self.scores_matrix

        # Replace NaN with 0 for similarity computation
        matrix_no_nan = np.nan_to_num(matrix, nan=0.0)

        # Compute norms
        norms = np.linalg.norm(matrix_no_nan, axis=1)
        norms[norms == 0] = 1e-10  # Avoid division by zero

        # Normalize rows
        normalized = matrix_no_nan / norms[:, np.newaxis]

        # Cosine similarity = dot product of normalized rows
        similarity = np.dot(normalized, normalized.T)

        # Ensure diagonal is 1 (self-similarity) and clip to avoid numerical issues
        np.fill_diagonal(similarity, 1.0)
        similarity = np.clip(similarity, -1.0, 1.0)

        self.similarity_matrix = similarity
        return similarity

    def recommend(
        self,
        user_id: str,
        top_n: int = 10,
        exclude_rated: bool = True,
        item_similarity: bool = True,
    ) -> List[Tuple[str, float]]:
        """
        Generate top-N item recommendations for a given user.

        Args:
            user_id: The target user ID.
            top_n: Number of recommendations to return.
            exclude_rated: If True, items already rated by the user are excluded.
            item_similarity: If True, use item-based CF; else user-based CF.

        Returns:
            A list of (item_id, predicted_score) tuples sorted by descending score.

        Raises:
            ValueError: If user_id is not found or matrix is not built.
            RuntimeError: If similarity matrix has not been computed.
        """
        if self.scores_matrix is None:
            raise ValueError("User not built. Call build_matrix() first.")
        if self.similarity_matrix is None:
            raise RuntimeError("Similarity matrix not computed. Call compute_similarity() first.")
        if user_id not in self.user_to_idx:
            raise ValueError(f"User '{user_id}' not found in the dataset.")

        user_idx = self.user_to_idx[user_id]
        user_ratings = self.scores_matrix[user_idx, :]

        if item_similarity:
            # Item-based: predicted rating = weighted sum of similar items ratings
            # Use similarity matrix (item x item)
            similarity = self.similarity_matrix
            if similarity.shape[0] != len(self.item_ids):
                raise RuntimeError("Similarity matrix dimensions do not match items. Compute item similarity.")

            # For each item, compute weighted sum
            pred_ratings = np.zeros(len(self.item_ids))
            for i in range(len(self.item_ids)):
                if exclude_rated and not np.isnan(user_ratings[i]):
                    pred_ratings[i] = np.nan
                    continue
                # Get similarities of item i to all items
                sim_vec = similarity[i, :]
                # Mask out NaN user ratings (set weights to 0)
                mask = ~np.isnan(user_ratings)
                if np.sum(mask) == 0:
                    pred_ratings[i] = 0.0
                    continue
                weights = sim_vec * mask
                sum_weights = np.sum(np.abs(weights))
                if sum_weights < 1e-10:
                    pred_ratings[i] = 0.0
                    continue
                pred_ratings[i] = np.dot(weights, np.nan_to_num(user_ratings, nan=0.0)) / sum_weights
        else:
            # User-based CF
            similarity = self.similarity_matrix
            if similarity.shape[0] != len(self.user_ids):
                raise RuntimeError("Similarity matrix dimensions do not match users. Compute user similarity.")

            pred_ratings = np.zeros(len(self.item_ids))
            for i in range(len(self.item_ids)):
                if exclude_rated and not np.isnan(user_ratings[i]):
                    pred_ratings[i] = np.nan
                    continue
                # Get ratings of all users for item i
                item_col = self.scores_matrix[:, i]
                mask = ~np.isnan(item_col)  # Users who rated this item
                if np.sum(mask) == 0:
                    pred_ratings[i] = 0.0
                    continue
                sim_vec = similarity[user_idx, :]
                weights = sim_vec * mask
                sum_weights = np.sum(np.abs(weights))
                if sum_weights < 1e-10:
                    pred_ratings[i] = 0.0
                    continue
                pred_ratings[i] = np.dot(weights, np.nan_to_num(item_col, nan=0.0)) / sum_weights

        # Build result list, excluding NaN predictions (if any)
        result: List[Tuple[str, float]] = []
        for idx, score in enumerate(pred_ratings):
            if np.isnan(score):
                continue
            result.append((self.item_ids[idx], float(score)))

        # Sort by score descending
        result.sort(key=lambda x: x[1], reverse=True)
        return result[:top_n]

    def evaluate(
        self,
        test_ratings: List[Tuple[str, str, float]],
        top_n: int = 10,
        item_similarity: bool = True,
    ) -> Dict[str, float]:
        """
        Evaluate recommendation quality using Precision@k and Recall@k.

        Args:
            test_ratings: List of (user_id, item_id, true_rating) tuples for testing.
            top_n: Number of top recommendations to consider.
            item_similarity: Whether to use item-based (True) or user-based (False) CF.

        Returns:
            Dictionary with 'precision@k' and 'recall@k' keys.

        Raises:
            RuntimeError: If model components are not initialized.
        """
        if self.scores_matrix is None or self.similarity_matrix is None:
            raise RuntimeError("Model not fully initialized. Build matrix and compute similarity first.")

        # Organize test data per user
        user_test_items: Dict[str, Set[str]] = defaultdict(set)
        for user, item, _ in test_ratings:
            if user in self.user_to_idx and item in self.item_to_idx:
                user_test_items[user].add(item)

        if not user_test_items:
            return {"precision@k": 0.0, "recall@k": 0.0}

        total_precision = 0.0
        total_recall = 0.0
        num_users_evaluated = 0

        for user_id, true_items in user_test_items.items():
            try:
                recs = self.recommend(user_id, top_n=top_n, exclude_rated=True, item_similarity=item_similarity)
            except (ValueError, RuntimeError):
                continue

            recommended_items = {item for item, _ in recs}
            if not recommended_items:
                continue

            hits = len(recommended_items.intersection(true_items))
            precision = hits / min(top_n, len(recommended_items)) if recommended_items else 0.0
            recall = hits / len(true_items) if true_items else 0.0

            total_precision += precision
            total_recall += recall
            num_users_evaluated += 1

        if num_users_evaluated == 0:
            return {"precision@k": 0.0, "recall@k": 0.0}

        avg_precision = total_precision / num_users_evaluated
        avg_recall = total_recall / num_users_evaluated

        return {"precision@k": avg_precision, "recall@k": avg_recall}

    def load_from_csv(
        self,
        filepath: str,
        user_col: int = 0,
        item_col: int = 1,
        rating_col: int = 2,
        has_header: bool = True,
        encoding: str = "utf-8",
    ) -> None:
        """
        Load ratings from a CSV file and build the user-item matrix.

        Args:
            filepath: Path to the CSV file.
            delimiter: Field delimiter character.
            user_col: Index of the user ID column (0-based).
            item_col: Index of the item ID column.
            rating_col: Index of the rating column.
            has_header: Whether the CSV file has a header row.
            encoding: File encoding.

        Raises:
            FileNotFoundError: If the file does not exist.
            PermissionError: If the file cannot be read.
            ValueError: If the CSV format is invalid.
        """
        if not os.path.isfile(filepath):
            raise FileNotFoundError(f"File not found: {filepath}")

        ratings: List[Tuple[str, str, float]] = []

        try:
            with open(filepath, "r", encoding=encoding) as f:
                reader = csv.reader(f, delimiter=delimiter)
                if has_header:
                    next(reader, None)
                for row_num, row in enumerate(reader, start=1):
                    if len(row) <= max(user_col, item_col, rating_col):
                        continue  # Skip malformed rows
                    user_id = row[user_col].strip()
                    item_id = row[item_col].strip()
                    try:
                        rating = float(row[rating_col].strip())
                    except (ValueError, IndexError):
                        continue  # Skip rows with non-numeric rating
                    if user_id and item_id:
                        ratings.append((user_id, item_id, rating))
        except PermissionError:
            raise PermissionError(f"Permission denied when reading file: {filepath}")
        except csv.Error as e:
            raise ValueError(f"CSV parsing error: {e}")

        self.build_matrix(ratings)