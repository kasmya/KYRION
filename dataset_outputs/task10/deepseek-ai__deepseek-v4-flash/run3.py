import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Union


class CollaborativeFilteringRecommender:
    """
    A collaborative filtering recommender system using cosine similarity.

    Supports both user-based and item-based approaches. Requires a DataFrame with
    columns: 'user_id', 'item_id', 'rating'. Fits a model, then can produce top-N
    recommendations and evaluate against a test set.

    Parameters
    ----------
    method : str, default='user_based'
        Either 'user_based' or 'item_based'.
    k_neighbors : int, default=20
        Number of nearest neighbors to use when making predictions.
    min_similarity : float, default=0.0
        Minimum similarity threshold for a neighbor to be considered.
    """

    def __init__(
        self,
        method: str = 'user_based',
        k_neighbors: int = 20,
        min_similarity: float = 0.0
    ) -> None:
        if method not in ('user_based', 'item_based'):
            raise ValueError(
                f"method must be 'user_based' or 'item_based', got '{method}'"
            )
        if k_neighbors < 1:
            raise ValueError(f"k_neighbors must be >= 1, got {k_neighbors}")
        if not 0.0 <= min_similarity <= 1.0:
            raise ValueError(f"min_similarity must be in [0,1], got {min_similarity}")

        self.method = method
        self.k_neighbors = k_neighbors
        self.min_similarity = min_similarity

        # Fitted data
        self.user_mapping_: Dict[Union[str, int], int] = {}  # original user -> index
        self.item_mapping_: Dict[Union[str, int], int] = {}  # original item -> index
        self.reverse_user_mapping_: Dict[int, Union[str, int]] = {}
        self.reverse_item_mapping_: Dict[int, Union[str, int]] = {}
        self.matrix_: Optional[np.ndarray] = None  # user-item matrix (n_users x n_items)
        self.similarity_: Optional[np.ndarray] = None  # similarity matrix

    def fit(self, ratings_df: pd.DataFrame) -> 'CollaborativeFilteringRecommender':
        """
        Fit the recommender model from a DataFrame of ratings.

        Parameters
        ----------
        ratings_df : pd.DataFrame
            Must contain columns 'user_id', 'item_id', 'rating'.

        Returns
        -------
        self
        """
        required_columns = {'user_id', 'item_id', 'rating'}
        if not required_columns.issubset(ratings_df.columns):
            raise ValueError(
                f"ratings_df must contain columns {required_columns}, "
                f"got {list(ratings_df.columns)}"
            )
        if ratings_df.empty:
            raise ValueError("ratings_df is empty")

        # Drop rows with missing values (security / robustness)
        ratings_df = ratings_df.dropna(subset=['user_id', 'item_id', 'rating'])

        # Ensure ratings are numeric
        ratings_df['rating'] = pd.to_numeric(ratings_df['rating'], errors='coerce')
        ratings_df = ratings_df.dropna(subset=['rating'])

        # Create mappings
        unique_users = ratings_df['user_id'].unique()
        unique_items = ratings_df['item_id'].unique()

        self.user_mapping_ = {user: idx for idx, user in enumerate(unique_users)}
        self.item_mapping_ = {item: idx for idx, item in enumerate(unique_items)}
        self.reverse_user_mapping_ = {idx: user for user, idx in self.user_mapping_.items()}
        self.reverse_item_mapping_ = {idx: item for item, idx in self.item_mapping_.items()}

        n_users = len(self.user_mapping_)
        n_items = len(self.item_mapping_)

        # Build user-item matrix (dense). For large data this may be memory-heavy.
        # Alternative: use sparse representation but requires scipy.
        self.matrix_ = np.zeros((n_users, n_items), dtype=np.float64)

        # Fill matrix with ratings
        for _, row in ratings_df.iterrows():
            u = self.user_mapping_[row['user_id']]
            i = self.item_mapping_[row['item_id']]
            self.matrix_[u, i] = row['rating']

        # Compute similarity matrix
        self._compute_similarity()

        return self

    def _compute_similarity(self) -> None:
        """
        Compute cosine similarity matrix between users (if user_based) or items.
        """
        if self.method == 'user_based':
            # Shape: (n_users, n_users) – similarity between rows of self.matrix_
            norm = np.linalg.norm(self.matrix_, axis=1, keepdims=True)
            # Avoid division by zero: keep rows with zero norm (all ratings zero) as zero vectors
            norm[norm == 0] = 1  # prevents division by zero, similarity 0 for those
            normalized = self.matrix_ / norm
            self.similarity_ = normalized.dot(normalized.T)
        else:  # item_based
            # Shape: (n_items, n_items) – similarity between columns
            norm = np.linalg.norm(self.matrix_, axis=0, keepdims=True)
            norm[norm == 0] = 1
            normalized = self.matrix_ / norm
            self.similarity_ = normalized.T.dot(normalized)

    def predict(self, user_id: Union[str, int], item_id: Union[str, int]) -> float:
        """
        Predict rating for a given user and item.

        Parameters
        ----------
        user_id : str or int
        item_id : str or int

        Returns
        -------
        float
            Predicted rating.
        """
        if self.matrix_ is None or self.similarity_ is None:
            raise RuntimeError("Model has not been fitted yet.")

        try:
            u = self.user_mapping_[user_id]
            i = self.item_mapping_[item_id]
        except KeyError as e:
            raise ValueError(
                f"Unknown user or item: {e}. Ensure they are present in training data."
            ) from e

        if self.method == 'user_based':
            # Prediction: weighted average of other users' ratings for this item
            # Get similarity of user u to all users, remove self
            sims = self.similarity_[u, :].copy()
            sims[u] = 0.0  # exclude self

            # Filter by min_similarity
            mask = sims >= self.min_similarity
            sims = sims[mask]
            if np.sum(np.abs(sims)) == 0:
                return self.matrix_[u, :].mean()  # fallback: user's average rating

            # Corresponding ratings of other users for item i
            ratings = self.matrix_[mask, i]
            # Use only ratings that are nonzero? Actually zero means no rating, so ignore.
            # But if a user rated zero (unlikely), treat as rating. We consider non-zero non-missing?
            # In explicit ratings, zero might be missing or actual zero. We'll consider only non-zero as valid.
            # Alternatively use only users who have rated item i (ratings != 0). Ensure non-zero denominator.
            valid = ratings != 0
            if not np.any(valid):
                return self.matrix_[u, :].mean()

            sims = sims[valid]
            ratings = ratings[valid]
            # Weighted average
            pred = np.dot(sims, ratings) / np.sum(np.abs(sims))
            return float(pred)

        else:  # item_based
            # Prediction: weighted average of ratings given by user u to items similar to i
            # Get similarity of item i to all items, remove self
            sims = self.similarity_[i, :].copy()
            sims[i] = 0.0

            mask = sims >= self.min_similarity
            sims = sims[mask]
            if np.sum(np.abs(sims)) == 0:
                # fallback: average rating of item i by all users who rated it
                item_ratings = self.matrix_[:, i]
                non_zero = item_ratings[item_ratings != 0]
                return float(non_zero.mean()) if len(non_zero) > 0 else self.matrix_.mean()

            # Ratings given by user u to those similar items
            ratings = self.matrix_[u, mask]
            valid = ratings != 0
            if not np.any(valid):
                return float(self.matrix_[:, i][self.matrix_[:, i] != 0].mean()) if np.any(self.matrix_[:, i] != 0) else self.matrix_.mean()

            sims = sims[valid]
            ratings = ratings[valid]
            pred = np.dot(sims, ratings) / np.sum(np.abs(sims))
            return float(pred)

    def recommend(
        self,
        user_id: Union[str, int],
        top_n: int = 10,
        exclude_rated: bool = True
    ) -> List[Union[str, int]]:
        """
        Generate top-N item recommendations for a given user.

        Parameters
        ----------
        user_id : str or int
        top_n : int, default=10
            Number of recommendations to return.
        exclude_rated : bool, default=True
            If True, exclude items already rated by the user.

        Returns
        -------
        list of item IDs
        """
        if self.matrix_ is None or self.similarity_ is None:
            raise RuntimeError("Model has not been fitted yet.")

        if user_id not in self.user_mapping_:
            raise ValueError(f"User '{user_id}' not found in training data.")

        u = self.user_mapping_[user_id]
        n_items = self.matrix_.shape[1]

        predictions = []
        for i in range(n_items):
            # Skip items already rated if exclude_rated is True
            if exclude_rated and self.matrix_[u, i] != 0:
                continue
            pred = self.predict(
                self.reverse_user_mapping_[u],
                self.reverse_item_mapping_[i]
            )
            predictions.append((self.reverse_item_mapping_[i], pred))

        # Sort descending by predicted rating
        predictions.sort(key=lambda x: x[1], reverse=True)
        top_n = min(top_n, len(predictions))
        return [item for item, _ in predictions[:top_n]]

    def evaluate(
        self,
        test_df: pd.DataFrame,
        top_k: int = 10
    ) -> Dict[str, float]:
        """
        Evaluate the model on a test DataFrame.

        Computes RMSE, MAE for rating predictions, and Precision@k, Recall@k, MAP for
        top-K recommendations (treating ratings >= threshold as relevant). The threshold
        is set as the median rating in the training data, or 3.0 by default.

        Parameters
        ----------
        test_df : pd.DataFrame
            Test set with columns 'user_id', 'item_id', 'rating'.
        top_k : int, default=10
            Number of recommendations for precision/recall.

        Returns
        -------
        dict
            Dictionary with keys 'rmse', 'mae', 'precision_at_k', 'recall_at_k', 'map'.
        """
        if self.matrix_ is None:
            raise RuntimeError("Model has not been fitted yet.")

        # Threshold for relevance: median of training ratings, or 3.0 if none
        train_ratings = self.matrix_[self.matrix_ != 0]
        if len(train_ratings) > 0:
            threshold = float(np.median(train_ratings))
        else:
            threshold = 3.0

        # For each user in test, collect predictions and actuals
        user_groups = test_df.groupby('user_id')
        all_preds = []
        all_actuals = []
        precision_sum = 0.0
        recall_sum = 0.0
        ap_sum = 0.0
        n_users = 0

        for user_id, group in user_groups:
            if user_id not in self.user_mapping_:
                continue  # skip unseen users

            # Get ground truth items and ratings for this user
            actual_items = group['item_id'].tolist()
            actual_ratings = group['rating'].tolist()
            actual_dict = dict(zip(actual_items, actual_ratings))
            relevant_items = set(
                item for item, rating in actual_dict.items() if rating >= threshold
            )
            if not relevant_items:
                continue

            # Get predicted ratings for all items that were rated in test (or we can predict all)
            # But we only need predictions for these actual items for RMSE/MAE.
            # For precision/recall we need top-K recommendations.
            # Let's first compute RMSE/MAE per item.
            for item_id, actual_rating in actual_dict.items():
                if item_id not in self.item_mapping_:
                    continue
                try:
                    pred = self.predict(user_id, item_id)
                except ValueError:
                    continue
                all_preds.append(pred)
                all_actuals.append(actual_rating)

            # Compute top-K recommendations (exclude rated items? Usually we exclude them,
            # but for precision/recall we often consider all items. We'll exclude items
            # that user has already rated in training? The standard setting: for each user,
            # we remove from the recommendation list the items they have interacted with
            # during training. But here we are evaluating on test, so we should only
            # consider items not in training. Our recommend function by default excludes
            # rated (training) items. That's appropriate for evaluation.
            # However, the ground truth relevant items may include items that were already
            # in training? In a proper train/test split, test items are not in training.
            # We assume the test set contains only unseen items. So exclude_rated=True.
            try:
                recommendations = self.recommend(user_id, top_n=top_k, exclude_rated=True)
            except ValueError:
                continue

            # Precision and recall
            rec_set = set(recommendations)
            hits = rec_set & relevant_items
            prec = len(hits) / top_k if top_k > 0 else 0.0
            rec = len(hits) / len(relevant_items) if len(relevant_items) > 0 else 0.0
            precision_sum += prec
            recall_sum += rec

            # Average Precision (AP)
            # Order matters: we already have recommendations sorted by prediction.
            ap = 0.0
            hit_count = 0
            for idx, item in enumerate(recommendations):
                if item in relevant_items:
                    hit_count += 1
                    ap += hit_count / (idx + 1)
            if len(relevant_items) > 0:
                ap /= len(relevant_items)
            ap_sum += ap

            n_users += 1

        if n_users == 0:
            raise RuntimeError("No overlapping users between training and test set.")

        # RMSE/MAE
        if len(all_preds) == 0:
            raise RuntimeError("No overlapping items for rating prediction evaluation.")

        all_preds = np.array(all_preds)
        all_actuals = np.array(all_actuals)
        mse = np.mean((all_preds - all_actuals) ** 2)
        rmse = float(np.sqrt(mse))
        mae = float(np.mean(np.abs(all_preds - all_actuals)))

        precision_k = precision_sum / n_users
        recall_k = recall_sum / n_users
        map_k = ap_sum / n_users

        return {
            'rmse': rmse,
            'mae': mae,
            'precision_at_k': precision_k,
            'recall_at_k': recall_k,
            'map': map_k
        }