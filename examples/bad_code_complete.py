# This code has many issues across all categories

password = "admin123"  # Hardcoded secret

import os
import sys
import math  # Unused import

def get_user_data(user_id):
    query = "SELECT * FROM users WHERE id = " + user_id  # SQL injection
    result = eval(query)  # Dangerous
    return result

def calculate():  # Long function
    result = 0
    for i in range(100):
        for j in range(100):
            result += i * j
            if result > 1000:
                return result
                print("This won't run")  # Unreachable
    return result

# TODO: Implement this function
# def process_data():
#     pass

# FIXME: This has a bug
def buggy_function():
    return 42
