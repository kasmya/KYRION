import numpy as np
import pandas as pd
from typing import Dict, List, Tuple
from scipy import spatial
from functools import cached_property
import logging
import os

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RecommendationSystem:
    """
    A Collaborative Filtering-based Recommendation System.

    Attributes:
    - user_item_matrix (pd.DataFrame): User-Item Interaction Matrix
    - num_users (int): Number of Unique Users
    - num_items (int): Number of Unique Items
    """

    def __init__(self, user_item_data: pd.DataFrame, user_id_col: str = "user_id", item_id_col: str = "item_id", rating_col: str = "rating"):
        """
        Initialize the Recommendation System.

        Args:
        - user_item_data (pd.DataFrame): Data containing user-item interactions
        - user_id_col (str): Column name for user IDs in the data
        - item_id_col (str): Column name for item IDs in the data
        - rating_col (str): Column name for ratings in the data

        Raises:
        - ValueError: If required columns are not present in the data
        """
        if not all(col in user_item_data.columns for col in [user_id_col, item_id_col, rating_col]):
            raise ValueError("Data must contain user_id, item_id, and rating columns")

        self.user_id_col = user_id_col
        self.item_id_col = item_id_col
        self.rating_col = rating_col
        self.user_item_data = user_item_data

    @cached_property
    def user_item_matrix(self) -> pd.DataFrame:
        """
        Construct the User-Item Matrix.

        Returns:
        - pd.DataFrame: Matrix with users as rows and items as columns
        """
        matrix = self.user_item_data.pivot(index=self.user_id_col, columns=self.item_id_col, values=self.rating_col)
        return matrix.fillna(0)  # Assuming 0 as no interaction

    @cached_property
    def num_users(self) -> int:
        """Return the number of unique users."""
        return len(self.user_item_matrix.index)

    @cached_property
    def num_items(self) -> int:
        """Return the number of unique items."""
        return len(self.user_item_matrix.columns)

    def cosine_similarity(self, vector1: np.ndarray, vector2: np.ndarray) -> float:
        """
        Compute Cosine Similarity between two vectors.

        Args:
        - vector1 (np.ndarray): First vector
        - vector2 (np.ndarray): Second vector

        Returns:
        - float: Cosine Similarity value
        """
        try:
            return 1 - spatial.distance.cosine(vector1, vector2)
        except Exception as e:
            logger.error(f"Error computing cosine similarity: {e}")
            return 0.0  # Default to 0 on error

    def get_user_similarity(self, user_id1: int, user_id2: int) -> float:
        """
        Calculate Similarity between two users.

        Args:
        - user_id1 (int): ID of the first user
        - user_id2 (int): ID of the second user

        Returns:
        - float: Similarity value between the two users

        Raises:
        - ValueError: If either user ID is not found
        """
        if user_id1 not in self.user_item_matrix.index or user_id2 not in self.user_item_matrix.index:
            raise ValueError("One or both user IDs not found in the data")

        vector1 = self.user_item_matrix.loc[user_id1].values
        vector2 = self.user_item_matrix.loc[user_id2].values
        return self.cosine_similarity(vector1, vector2)

    def get_top_n_recommendations(self, user_id: int, n: int = 5) -> List[Tuple[int, float]]:
        """
        Generate Top-N Recommendations for a given user.

        Args:
        - user_id (int): ID of the user
        - n (int): Number of recommendations to generate

        Returns:
        - List[Tuple[int, float]]: List of (item_id, predicted_rating) tuples

        Raises:
        - ValueError: If the user ID is not found
        """
        if user_id not in self.user_item_matrix.index:
            raise ValueError("User ID not found in the data")

        # Simplified approach for demonstration; 
        # consider more advanced methods like matrix factorization for large datasets
        similarities = {}
        for other_user in self.user_item_matrix.index:
            if other_user != user_id:
                similarity = self.get_user_similarity(user_id, other_user)
                similarities[other_user] = similarity

        # Sort users by similarity
        sorted_users = sorted(similarities, key=similarities.get, reverse=True)

        # Generate recommendations based on similar users' interactions
        recommended_items = []
        for user in sorted_users:
            user_vector = self.user_item_matrix.loc[user]
            for item, rating in user_vector.items():
                if rating > 0 and self.user_item_matrix.loc[user_id, item] == 0:  # Item not interacted with
                    # Simple prediction: use the similar user's rating as a placeholder
                    # In practice, use a more sophisticated prediction method
                    predicted_rating = rating * similarities[user]
                    recommended_items.append((item, predicted_rating))
                    if len(recommended_items) >= n:
                        break
            if len(recommended_items) >= n:
                break

        # Sort recommendations by predicted rating
        recommended_items.sort(key=lambda x: x[1], reverse=True)
        return recommended_items[:n]

    def evaluate(self, test_data: pd.DataFrame, metric: str = "mae") -> float:
        """
        Evaluate the Recommendation System using a test dataset.

        Args:
        - test_data (pd.DataFrame): Test data with actual ratings
        - metric (str): Evaluation metric ("mae" for Mean Absolute Error)

        Returns:
        - float: Evaluation metric value

        Raises:
        - ValueError: If the metric is not supported
        """
        if metric not in ["mae"]:  # Currently only supporting MAE
            raise ValueError("Only 'mae' metric is supported at this time")

        predictions = []
        actuals = []
        for index, row in test_data.iterrows():
            user_id, item_id, actual_rating = row[self.user_id_col], row[self.item_id_col], row[self.rating_col]
            # For simplicity, assuming prediction is the average rating of similar users for the item
            # Implement a proper prediction method based on your approach (e.g., collaborative filtering)
            predicted_rating = self.user_item_matrix[item_id].mean()  # Placeholder for actual prediction logic
            predictions.append(predicted_rating)
            actuals.append(actual_rating)

        if metric == "mae":
            return np.mean(np.abs(np.array(predictions) - np.array(actuals)))

# Example Usage
if __name__ == "__main__":
    # Sample Data
    data = {
        "user_id": [1, 1, 1, 2, 2, 3, 3, 3, 3],
        "item_id": [101, 102, 103, 101, 103, 101, 102, 103, 104],
        "rating": [4, 3, 0, 5, 4, 1, 2, 3, 0]  # 0 indicates no rating (not interacted)
    }
    df = pd.DataFrame(data)

    test_data = pd.DataFrame({
        "user_id": [1, 2, 3],
        "item_id": [104, 102, 101],
        "rating": [0, 4, 5]  # Example actual ratings for testing
    })

    rs = RecommendationSystem(df)
    print(f"User-Item Matrix Shape: {rs.user_item_matrix.shape}")
    
    # Example: Get similarity between two users
    user1, user2 = 1, 2
    similarity = rs.get_user_similarity(user1, user2)
    print(f"Similarity between User {user1} and {user2}: {similarity:.2f}")

    # Generate Recommendations
    user_id = 1
    n_recs = 2
    recommendations = rs.get_top_n_recommendations(user_id, n_recs)
    print(f"Top {n_recs} Recommendations for User {user_id}: {recommendations}")

    # Evaluate (Simplified for Demo)
    mae = rs.evaluate(test_data)
    print(f"MAE on Test Data: {mae:.2f}")