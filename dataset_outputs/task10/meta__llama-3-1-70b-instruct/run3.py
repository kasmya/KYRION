import numpy as np
import pandas as pd
from scipy import spatial
from typing import Dict, List, Tuple

class RecommendationSystem:
    def __init__(self, user_item_matrix: pd.DataFrame):
        """
        Initialize the recommendation system with a user-item matrix.

        Args:
        - user_item_matrix (pd.DataFrame): A matrix where rows represent users and columns represent items.
        """
        self.user_item_matrix = user_item_matrix

    def compute_similarity(self, user1: str, user2: str) -> float:
        """
        Compute the cosine similarity between two users.

        Args:
        - user1 (str): The ID of the first user.
        - user2 (str): The ID of the second user.

        Returns:
        - float: The cosine similarity between the two users.

        Raises:
        - ValueError: If either user is not found in the user-item matrix.
        """
        try:
            user1_vector = self.user_item_matrix.loc[user1].values
            user2_vector = self.user_item_matrix.loc[user2].values
            return 1 - spatial.distance.cosine(user1_vector, user2_vector)
        except KeyError as e:
            raise ValueError("User not found in the user-item matrix") from e

    def get_top_n_recommendations(self, user: str, n: int = 10) -> List[Tuple[str, float]]:
        """
        Get the top-N recommendations for a given user.

        Args:
        - user (str): The ID of the user.
        - n (int, optional): The number of recommendations to return. Defaults to 10.

        Returns:
        - List[Tuple[str, float]]: A list of tuples containing the item ID and the predicted rating.

        Raises:
        - ValueError: If the user is not found in the user-item matrix.
        """
        try:
            similarities = {}
            for other_user in self.user_item_matrix.index:
                if other_user != user:
                    similarity = self.compute_similarity(user, other_user)
                    similarities[other_user] = similarity

            sorted_similarities = sorted(similarities.items(), key=lambda x: x[1], reverse=True)
            top_n_similar_users = [x[0] for x in sorted_similarities[:n]]

            recommendations = []
            for item in self.user_item_matrix.columns:
                predicted_rating = 0
                for similar_user in top_n_similar_users:
                    rating = self.user_item_matrix.loc[similar_user, item]
                    if not np.isnan(rating):
                        predicted_rating += rating * similarities[similar_user]
                if predicted_rating > 0:
                    recommendations.append((item, predicted_rating))

            return sorted(recommendations, key=lambda x: x[1], reverse=True)
        except KeyError as e:
            raise ValueError("User not found in the user-item matrix") from e

    def evaluate(self, test_data: pd.DataFrame, n: int = 10) -> Dict[str, float]:
        """
        Evaluate the recommendation system using the test data.

        Args:
        - test_data (pd.DataFrame): A matrix where rows represent users and columns represent items.
        - n (int, optional): The number of recommendations to consider. Defaults to 10.

        Returns:
        - Dict[str, float]: A dictionary containing the precision, recall, and F1 score.
        """
        precision = 0
        recall = 0
        f1 = 0
        count = 0

        for user in test_data.index:
            recommendations = self.get_top_n_recommendations(user, n)
            recommended_items = [x[0] for x in recommendations]
            actual_items = test_data.loc[user, :][test_data.loc[user, :] > 0].index.tolist()

            true_positives = len(set(recommended_items) & set(actual_items))
            false_positives = len(set(recommended_items) - set(actual_items))
            false_negatives = len(set(actual_items) - set(recommended_items))

            precision += true_positives / (true_positives + false_positives)
            recall += true_positives / (true_positives + false_negatives)
            f1 += 2 * true_positives / (2 * true_positives + false_positives + false_negatives)
            count += 1

        precision /= count
        recall /= count
        f1 /= count

        return {"precision": precision, "recall": recall, "f1": f1}

# Example usage:
if __name__ == "__main__":
    user_item_matrix = pd.DataFrame({
        "item1": [5, 3, 0, 1],
        "item2": [4, 0, 0, 1],
        "item3": [1, 1, 0, 5],
        "item4": [1, 0, 0, 4],
        "item5": [0, 1, 5, 4]
    }, index=["user1", "user2", "user3", "user4"])

    recommendation_system = RecommendationSystem(user_item_matrix)
    recommendations = recommendation_system.get_top_n_recommendations("user1")
    print(recommendations)

    test_data = pd.DataFrame({
        "item1": [5, 3, 0, 1],
        "item2": [4, 0, 0, 1],
        "item3": [1, 1, 0, 5],
        "item4": [1, 0, 0, 4],
        "item5": [0, 1, 5, 4]
    }, index=["user1", "user2", "user3", "user4"])

    evaluation_metrics = recommendation_system.evaluate(test_data)
    print(evaluation_metrics)