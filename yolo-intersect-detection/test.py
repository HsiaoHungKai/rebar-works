import numpy as np
import math
from rebar_object_detection import get_circular_outlier_indices

# Generate 5 random numbers between 3.1 and pi
pos_range = np.random.uniform(3.1, math.pi, size=5)

# Generate 5 random numbers between -pi and -3.1
neg_range = np.random.uniform(-math.pi, -3.1, size=5)

# Combine into one array
random_array = np.concatenate((pos_range, neg_range))
# Adding some outlier and non-outlier values for testing
random_array = np.append(random_array, [0.5, 0.4, -0.45, 0])  

print("Radians:", random_array)
for i in get_circular_outlier_indices(random_array, coef=1.5):
    print("Outliers: ", random_array[i])



