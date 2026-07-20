"""
Collaborative Filtering Recommendation System

Features
--------
- User‑item rating matrix construction from a pandas DataFrame.
- Cosine similarity computation between users.
- Top‑N item recommendations for a given user.
- Evaluation metrics: precision@k, recall@k, MAP@k.

Only standard library plus numpy and pandas are used.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Tuple, Union

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def _validate_dataframe(df: pd.DataFrame) -> None:
    """Validate that a DataFrame contains the required columns.

    Expected columns: ``user_id``, ``item_id``, ``rating`` (rating may be
    optional for implicit feedback).

    Raises
    ------
    ValueError
        If required columns are missing or contain NaN values.
    """
    required = {"user_id", "item_id"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    if df[["user_id", "item_id"]].isnull().any().any():
        raise ValueError("user_id and item_id columns must not contain NaN")


def _safe_read_csv(
    path: Union[str, pathlib.Path],
    *,
    sep: str = ",",
    dtype: Dict[str, object] | None = None,
) -> pd.DataFrame:
    """Read a CSV file in a safe, deterministic way.

    Parameters
    ----------
    path : str or pathlib.Path
        Path to the CSV file.
    sep : str, optional
        Field delimiter, by default ",".
    dtype : dict, optional
        Column dtypes to enforce, by default None.

    Returns
    -------
    pd.DataFrame
        The loaded data.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    PermissionError
        If the file is not readable.
    ValueError
        If parsing fails.
    """
    file_path = pathlib.Path(path).expanduser().resolve()
    if not file_path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")
    if not os.access(file_path, os.R_OK):
        raise PermissionError(f"File not readable: {file_path}")

    try:
        return pd.read_csv(file_path, sep=sep, dtype=dtype, engine="c")
    except Exception as exc:
        raise ValueError(f"Failed to parse CSV: {exc}") from exc


# ---------------------------------------------------------------------------
# Core recommender implementation
# ---------------------------------------------------------------------------


@dataclass
class CollaborativeFiltering:
    """User‑based collaborative filtering recommender.

    Parameters
    ----------
    min_rating : float, optional
        Minimum rating value to consider a user interacted with an item.
        Items with rating < min_rating are treated as missing.
        For implicit data set to 0, by default 0.
    """

    min_rating: float = 0.0
    user_item_matrix: pd.DataFrame = field(init=False, default_factory=pd.DataFrame)
    user_similarity: pd.DataFrame = field(init=False, default_factory=pd.DataFrame)

    # -----------------------------------------------------------------------
    # Data preparation
    # -----------------------------------------------------------------------

    def build_user_item_matrix(self, data: pd.DataFrame) -> pd.DataFrame:
        """Create a pivot table (user x item) from raw interaction data.

        Parameters
        ----------
        data : pd.DataFrame
            Must contain columns ``user_id``, ``item_id`` and optionally ``rating``.

        Returns
        -------
        pd.DataFrame
            Sparse‑style matrix with users as index, items as columns and
            ratings (or 1 for implicit feedback) as values.

        Raises
        ------
        ValueError
            If the input DataFrame is invalid.
        """
        _validate_dataframe(data)

        # Use explicit rating column if present; otherwise treat each row as implicit interaction
        if "rating" in data.columns:
            df = data.copy()
            df["rating"] = pd.to_numeric(df["rating"], errors="coerce").fillna(0.0)
            df.loc[df["rating"] < self.min_rating, "rating"] = 0.0
        else:
            # Implicit feedback: each observed interaction gets rating 1
            df = data.assign(rating=1.0)

        # Pivot to matrix
        matrix = df.pivot_table(
            index="user_id",
            columns="item_id",
            values="rating",
            aggfunc="mean",
            fill_value=0.0,
        )
        self.user_item_matrix = matrix
        return matrix

    # -----------------------------------------------------------------------
    # Similarity computation
    # -----------------------------------------------------------------------

    @staticmethod
    def _cosine_similarity(matrix: np.ndarray) -> np.ndarray:
        """Compute cosine similarity between rows of a dense matrix.

        Parameters
        ----------
        matrix : np.ndarray
            2‑D array where each row is a vector.

        Returns
        -------
        np.ndarray
            Square similarity matrix.
        """
        # Normalize rows to unit length; add epsilon to avoid division by zero
        eps = np.finfo(float).eps
        norms = np.linalg.norm(matrix, axis=1, keepdims=True) + eps
        normalized = matrix / norms
        similarity = normalized @ normalized.T
        # Clip possible numeric errors outside [0,1]
        np.clip(similarity, 0.0, 1.0, out=similarity)
        return similarity

    def compute_user_similarity(self) -> pd.DataFrame:
        """Calculate cosine similarity between users from the rating matrix.

        Returns
        -------
        pd.DataFrame
            DataFrame indexed and column‑labeled by user_id containing similarity scores.

        Raises
        ------
        RuntimeError
            If the user‑item matrix has not been built yet.
        """
        if self.user_item_matrix.empty:
            raise RuntimeError("User‑item matrix is empty. Call build_user_item_matrix first.")

        # Convert to dense numpy array (could be large; for production use sparse structures)
        dense = self.user_item_matrix.values.astype(np.float64)
        sim_array = self._cosine_similarity(dense)
        sim_df = pd.DataFrame(
            sim_array,
            index=self.user_item_matrix.index,
            columns=self.user_item_matrix.index,
        )
        self.user_similarity = sim_df
        return sim_df

    # -----------------------------------------------------------------------
    # Recommendation
    # -----------------------------------------------------------------------

    def recommend_top_n(
        self,
        user_id: Union[int, str],
        n: int = 10,
        *,
        exclude_seen: bool = True,
    ) -> List[Tuple[Union[int, str], float]]:
        """Generate top‑N item recommendations for a given user.

        Parameters
        ----------
        user_id : int or str
            Identifier of the target user.
        n : int, optional
            Number of items to recommend, by default 10.
        exclude_seen : bool, optional
            Whether to filter out items the user has already interacted with,
            by default True.

        Returns
        -------
        List[Tuple[item_id, score]]
            Ranked list of recommended items with predicted scores.

        Raises
        ------
        KeyError
            If the user is not present in the matrix.
        RuntimeError
            If similarity matrix is not yet computed.
        """
        if user_id not in self.user_item_matrix.index:
            raise KeyError(f"User {user_id} not found in the rating matrix.")
        if self.user_similarity.empty:
            raise RuntimeError("User similarity not computed. Call compute_user_similarity first.")
        if n <= 0:
            raise ValueError("Parameter n must be a positive integer.")

        # Scores = weighted sum of neighbor ratings
        user_sim = self.user_similarity.loc[user_id]  # Series of similarities
        # Exclude the user itself from the aggregation
        user_sim = user_sim.drop(labels=user_id)

        # Compute weighted sum of neighbor ratings
        neighbor_ratings = self.user_item_matrix.loc[user_sim.index]
        weighted_ratings = neighbor_ratings.T @ user_sim.values
        # Normalisation by sum of similarities (avoid division by zero)
        sim_sum = np.abs(user_sim).sum()
        if sim_sum == 0:
            # No similar users - fall back to popularity
            scores = self.user_item_matrix.sum(axis=0)
        else:
            scores = weighted_ratings / sim_sum

        # Convert to Series with item ids as index
        scores_series = pd.Series(scores, index=self.user_item_matrix.columns)

        if exclude_seen:
            seen = self.user_item_matrix.loc[user_id]
            scores_series = scores_series[seen == 0]

        top_n = scores_series.nlargest(n)
        return list(zip(top_n.index.tolist(), top_n.values.tolist()))

    # -----------------------------------------------------------------------
    # Evaluation
    # -----------------------------------------------------------------------

    @staticmethod
    def _precision_at_k(
        true_items: Iterable[Union[int, str]],
        pred_items: List[Union[int, str]],
        k: int,
    ) -> float:
        """Precision@k for a single user."""
        if k == 0:
            return 0.0
        pred_k = set(pred_items[:k])
        true_set = set(true_items)
        return len(pred_k & true_set) / k

    @staticmethod
    def _recall_at_k(
        true_items: Iterable[Union[int, str]],
        pred_items: List[Union[int, str]],
        k: int,
    ) -> float:
        """Recall@k for a single user."""
        if not true_items:
            return 0.0
        pred_k = set(pred_items[:k])
        true_set = set(true_items)
        return len(pred_k & true_set) / len(true_set)

    @staticmethod
    def _average_precision(
        true_items: Iterable[Union[int, str]],
        pred_items: List[Union[int, str]],
        k: int,
    ) -> float:
        """Mean Average Precision@k for a single user."""
        true_set = set(true_items)
        if not true_set:
            return 0.0
        score = 0.0
        hit_count = 0
        for i, item in enumerate(pred_items[:k], start=1):
            if item in true_set:
                hit_count += 1
                score += hit_count / i
        return score / min(len(true_set), k)

    def evaluate(
        self,
        test_data: pd.DataFrame,
        k: int = 10,
    ) -> Dict[str, float]:
        """Evaluate the recommender on a test set.

        Parameters
        ----------
        test_data : pd.DataFrame
            Must contain ``user_id`` and ``item_id`` columns.
        k : int, optional
            Rank cutoff for metrics, by default 10.

        Returns
        -------
        dict
            Dictionary with ``precision``, ``recall`` and ``map`` values.

        Raises
        ------
        ValueError
            If test_data is malformed or k is non‑positive.
        RuntimeError
            If model is not ready for predictions.
        """
        if k <= 0:
            raise ValueError("k must be a positive integer.")
        _validate_dataframe(test_data)

        # Build ground‑truth mapping user -> set(items)
        truth: Dict[Union[int, str], set] = {}
        for uid, iid in zip(test_data["user_id"], test_data["item_id"]):
            truth.setdefault(uid, set()).add(iid)

        precisions, recalls, aps = [], [], []
        for uid, true_items in truth.items():
            try:
                preds = [iid for iid, _ in self.recommend_top_n(uid, n=k, exclude_seen=True)]
            except (KeyError, RuntimeError):
                # User not in training set or similarity not computed; skip
                continue

            precisions.append(self._precision_at_k(true_items, preds, k))
            recalls.append(self._recall_at_k(true_items, preds, k))
            aps.append(self._average_precision(true_items, preds, k))

        if not precisions:
            raise RuntimeError("No overlapping users between train and test data for evaluation.")

        return {
            "precision@k": float(np.mean(precisions)),
            "recall@k": float(np.mean(recalls)),
            "map@k": float(np.mean(aps)),
        }


# ---------------------------------------------------------------------------
# Example usage (can be removed or replaced in production)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Synthetic example
    import random

    # Generate a small random dataset
    random.seed(42)
    users = [f"U{i}" for i in range(1, 6)]
    items = [f"I{j}" for j in range(1, 11)]

    rows = []
    for u in users:
        rated_items = random.sample(items, k=5)
        for i in rated_items:
            rows.append({"user_id": u, "item_id": i, "rating": random.randint(1, 5)})

    df = pd.DataFrame(rows)

    # Initialise recommender
    cf = CollaborativeFiltering(min_rating=1)

    # Build matrix and compute similarity
    cf.build_user_item_matrix(df)
    cf.compute_user_similarity()

    # Recommend for a user
    user_to_recommend = users[0]
    print(f"Top recommendations for {user_to_recommend}:")
    for item, score in cf.recommend_top_n(user_to_recommend, n=5):
        print(f"  {item}: {score:.3f}")

    # Evaluation using a simple hold‑out split
    train_df = df.sample(frac=0.8, random_state=1)
    test_df = df.drop(train_df.index)
    cf_train = CollaborativeFiltering(min_rating=1)
    cf_train.build_user_item_matrix(train_df)
    cf_train.compute_user_similarity()
    metrics = cf_train.evaluate(test_df, k=5)
    print("\nEvaluation metrics on hold‑out set:")
    for metric, value in metrics.items():
        print(f"  {metric}: {value:.4f}")