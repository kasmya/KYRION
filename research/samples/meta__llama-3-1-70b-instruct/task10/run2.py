import numpy as np
import pandas as pd
from typing import Dict, List, Tuple
from scipy import spatial

class RecommendationSystem:
    def __init__(self, user_item_matrix: pd.DataFrame):
        """
        Initialize the recommendation system with a user-item matrix.

        Args:
        user_item_matrix (pd.DataFrame): A DataFrame where rows are users, columns are items, and values are ratings.
        """
        self.user_item_matrix = user_item_matrix

    def compute_similarity(self, user1: str, user2: str) -> float:
        """
        Compute the cosine similarity between two users.

        Args:
        user1 (str): The ID of the first user.
        user2 (str): The ID of the second user.

        Returns:
        float: The cosine similarity between the two users.
        """
        try:
            ratings1 = self.user_item_matrix.loc[user1].values
            ratings2 = self.user_item_matrix.loc[user2].values
            similarity = 1 - spatial.distance.cosine(ratings1, ratings2)
            return similarity
        except KeyError:
            raise ValueError("Both users must be present in the user-item matrix")

    def get_top_n_recommendations(self, user: str, n: int = 10) -> List[Tuple[str, float]]:
        """
        Get the top-N item recommendations for a given user.

        Args:
        user (str): The ID of the user.
        n (int, optional): The number of recommendations to return. Defaults to 10.

        Returns:
        List[Tuple[str, float]]: A list of tuples, where each tuple contains an item ID and its predicted rating.
        """
        try:
            similarities = {}
            for other_user in self.user_item_matrix.index:
                if other_user != user:
                    similarity = self.compute_similarity(user, other_user)
                    similarities[other_user] = similarity

            item_recommendations = {}
            for item in self.user_item_matrix.columns:
                predicted_rating = 0
                for other_user, similarity in similarities.items():
                    rating = self.user_item_matrix.loc[other_user, item]
                    predicted_rating += rating * similarity
                item_recommendations[item] = predicted_rating

            top_n_recommendations = sorted(item_recommendations.items(), key=lambda x: x[1], reverse=True)[:n]
            return top_n_recommendations
        except KeyError:
            raise ValueError("The user must be present in the user-item matrix")

    def evaluate(self, test_set: pd.DataFrame) -> Dict[str, float]:
        """
        Evaluate the recommendation system using precision, recall, and F1-score.

        Args:
        test_set (pd.DataFrame): A DataFrame containing the true ratings for a subset of users and items.

        Returns:
        Dict[str, float]: A dictionary containing the precision, recall, and F1-score of the recommendation system.
        """
        try:
            precision = 0
            recall = 0
            f1_score = 0
            for user in test_set.index:
                top_n_recommendations = self.get_top_n_recommendations(user, n=len(test_set.columns))
                recommended_items = [item for item, _ in top_n_recommendations]
                true_items = test_set.loc[user].loc[lambda x: x > 0].index
                precision += len(set(recommended_items) & set(true_items)) / len(recommended_items)
                recall += len(set(recommended_items) & set(true_items)) / len(true_items)
                f1_score += 2 * (precision * recall) / (precision + recall)
            precision /= len(test_set.index)
            recall /= len(test_set.index)
            f1_score /= len(test_set.index)
            return {"precision": precision, "recall": recall, "f1_score": f1_score}
        except KeyError:
            raise ValueError("The test set must be a subset of the user-item matrix")


# Example usage
user_item_matrix = pd.DataFrame({
    "User1": [1, 2, 0, 0, 5],
    "User2": [2, 0, 3, 4, 0],
    "User3": [0, 1, 2, 3, 0],
    "User4": [4, 3, 2, 1, 0]
}, index=["Item1", "Item2", "Item3", "Item4", "Item5"])

recommendation_system = RecommendationSystem(user_item_matrix)

similarities = {}
for user1 in user_item_matrix.index:
    for user2 in user_item_matrix.index:
        if user1 != user2:
            similarity = recommendation_system.compute_similarity(user1, user2)
            similarities[(user1, user2)] = similarity
print(similarities)

top_n_recommendations = recommendation_system.get_top_n_recommendations("User1")
print(top_n_recommendations)

test_set = pd.DataFrame({
    "User1": [1, 2, 0, 0],
    "User2": [2, 0, 3, 4]
}, index=["Item1", "Item2", "Item3", "Item4"])
evaluation_metrics = recommendation_system.evaluate(test_set)
print(evaluation_metrics)