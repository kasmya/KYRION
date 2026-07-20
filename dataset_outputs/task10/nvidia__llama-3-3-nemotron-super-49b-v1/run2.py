import numpy as np
import pandas as pd
from typing import Dict, List, Tuple
from scipy import spatial
from collections import defaultdict

class CollaborativeFilteringRecommender:
    """
    A collaborative filtering-based recommendation system.

    Attributes:
    - user_item_matrix (pd.DataFrame): User-item interaction matrix.
    - num_users (int): Number of unique users.
    - num_items (int): Number of unique items.
    """

    def __init__(self, user_item_data: pd.DataFrame):
        """
        Initialize the recommender system with user-item interaction data.

        Args:
        - user_item_data (pd.DataFrame): DataFrame with 'user_id', 'item_id', and 'rating' columns.
        """
        if not isinstance(user_item_data, pd.DataFrame):
            raise TypeError("Input must be a pandas DataFrame")
        required_columns = {'user_id', 'item_id', 'rating'}
        if not required_columns.issubset(user_item_data.columns):
            raise ValueError("DataFrame must contain 'user_id', 'item_id', and 'rating' columns")

        self.user_item_matrix = self._construct_user_item_matrix(user_item_data)
        self.num_users, self.num_items = self.user_item_matrix.shape

    @staticmethod
    def _construct_user_item_matrix(user_item_data: pd.DataFrame) -> pd.DataFrame:
        """
        Construct a user-item matrix from interaction data.

        Args:
        - user_item_data (pd.DataFrame): DataFrame with 'user_id', 'item_id', and 'rating' columns.

        Returns:
        - pd.DataFrame: User-item matrix with users as rows and items as columns.
        """
        return user_item_data.pivot(index="user_id", columns="item_id", values="rating")

    def compute_similarity(self, user_id1: int, user_id2: int) -> float:
        """
        Compute cosine similarity between two users' rating vectors.

        Args:
        - user_id1 (int): ID of the first user.
        - user_id2 (int): ID of the second user.

        Returns:
        - float: Cosine similarity between the two users.

        Raises:
        - ValueError: If either user ID is out of range.
        """
        if user_id1 < 0 or user_id1 >= self.num_users or user_id2 < 0 or user_id2 >= self.num_users:
            raise ValueError("User ID out of range")

        vector1 = self.user_item_matrix.iloc[user_id1]
        vector2 = self.user_item_matrix.iloc[user_id2]
        return 1 - spatial.distance.cosine(vector1, vector2)

    def get_top_n_recommendations(self, user_id: int, n: int = 5) -> List[Tuple[int, float]]:
        """
        Generate top-N item recommendations for a given user.

        Args:
        - user_id (int): ID of the user for whom to generate recommendations.
        - n (int, optional): Number of recommendations to return. Defaults to 5.

        Returns:
        - List[Tuple[int, float]]: List of tuples containing recommended item IDs and their predicted ratings.

        Raises:
        - ValueError: If user ID is out of range.
        """
        if user_id < 0 or user_id >= self.num_users:
            raise ValueError("User ID out of range")

        # Compute similarities with all other users
        similarities = {i: self.compute_similarity(user_id, i) for i in range(self.num_users) if i != user_id}

        # Select top-N similar users
        top_n_similar_users = sorted(similarities, key=similarities.get, reverse=True)[:n]

        # Generate recommendations based on top-N similar users
        recommendations = defaultdict(float)
        for similar_user in top_n_similar_users:
            for item, rating in self.user_item_matrix.iloc[similar_user].items():
                if pd.isnull(rating):  # Only consider rated items
                    continue
                if pd.isnull(self.user_item_matrix.iloc[user_id][item]):  # Ignore already rated items
                    recommendations[item] += rating * similarities[similar_user]

        # Normalize predicted ratings
        total_similarity = sum(similarities[u] for u in top_n_similar_users)
        recommendations = [(item, rating / total_similarity) for item, rating in recommendations.items()]

        return sorted(recommendations, key=lambda x: x[1], reverse=True)[:n]

    def evaluate(self, test_data: pd.DataFrame, metric: str = "mae") -> float:
        """
        Evaluate the recommendation system using a specified metric.

        Args:
        - test_data (pd.DataFrame): DataFrame with 'user_id', 'item_id', and 'rating' columns for testing.
        - metric (str, optional): Evaluation metric ('mae' or 'rmse'). Defaults to "mae".

        Returns:
        - float: Evaluation metric value.

        Raises:
        - ValueError: If metric is not 'mae' or 'rmse'.
        """
        if metric not in ["mae", "rmse"]:
            raise ValueError("Invalid metric. Supported metrics are 'mae' and 'rmse'.")

        predicted_ratings = []
        actual_ratings = []
        for _, row in test_data.iterrows():
            user_id = row["user_id"]
            item_id = row["item_id"]
            actual_rating = row["rating"]

            # Simulate recommendation generation for the test user-item pair
            similar_users = [i for i in range(self.num_users) if i != user_id]
            predicted_rating = 0
            total_similarity = 0
            for similar_user in similar_users:
                similarity = self.compute_similarity(user_id, similar_user)
                if pd.notnull(self.user_item_matrix.iloc[similar_user][item_id]):
                    predicted_rating += self.user_item_matrix.iloc[similar_user][item_id] * similarity
                    total_similarity += similarity
            predicted_rating /= total_similarity if total_similarity != 0 else 1  # Avoid division by zero

            predicted_ratings.append(predicted_rating)
            actual_ratings.append(actual_rating)

        if metric == "mae":
            return np.mean(np.abs(np.array(predicted_ratings) - np.array(actual_ratings)))
        elif metric == "rmse":
            return np.sqrt(np.mean((np.array(predicted_ratings) - np.array(actual_ratings)) ** 2))


# Example usage
if __name__ == "__main__":
    # Sample user-item interaction data
    user_item_data = pd.DataFrame({
        "user_id": [0, 0, 0, 1, 1, 2, 2, 2],
        "item_id": [0, 1, 2, 0, 2, 1, 2, 3],
        "rating": [4, 5, 3, 4, 5, 1, 2, 4]
    })

    # Initialize the recommender system
    recommender = CollaborativeFilteringRecommender(user_item_data)

    # Generate recommendations for user 0
    recommendations = recommender.get_top_n_recommendations(0, n=3)
    print("Recommendations for user 0:", recommendations)

    # Evaluate the recommendation system
    test_data = pd.DataFrame({
        "user_id": [0, 1, 2],
        "item_id": [3, 1, 0],
        "rating": [0, 4, 3]  # Actual ratings for test cases (simulated)
    })
    evaluation_metric = recommender.evaluate(test_data, metric="mae")
    print("Evaluation Metric (MAE):", evaluation_metric)