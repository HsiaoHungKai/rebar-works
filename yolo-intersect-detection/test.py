import numpy as np
import math
from functools import reduce
from math import sin, cos, atan2, pi
from rebar_object_detection import get_circular_outlier_indices

def norm_angle(angle, mpi=pi):
    angle = angle % (2 * mpi)
    return angle if abs(angle) <= mpi else angle - (1 if angle >= 0 else -1) * 2 * mpi

def circular_mean(angles):
    x_sum, y_sum = reduce(lambda tup, ang: (tup[0] + cos(ang), tup[1] + sin(ang)), angles, (0, 0))
    if x_sum == 0 and y_sum == 0:
        return None
    return atan2(y_sum, x_sum)

def circular_interquartiles_value(angles):
    mean = circular_mean(angles)
    deltas = tuple(sorted([norm_angle(a - mean) for a in angles]))
    nb = len(deltas)
    nq1, nq3, direct = nb // 4, nb - nb // 4, (nb % 4) // 2
    q1 = deltas[nq1] if direct else (deltas[nq1 - 1] + deltas[nq1]) / 2
    q3 = deltas[nq3 - 1] if direct else (deltas[nq3 - 1] + deltas[nq3]) / 2
    return q3 - q1

def circular_outliers(angles, coef=1.5, values=True):
    mean = circular_mean(angles)
    maxdelta = coef * circular_interquartiles_value(angles)
    deltas = [norm_angle(a - mean) for a in angles]
    return [z[0] if values else i for i, z in enumerate(zip(angles, deltas)) if abs(z[1]) > maxdelta]

def remove_axial_outliers(original_angles, coef=1.5):
    doubled_angles = [2 * a for a in original_angles]
    outlier_indices = circular_outliers(doubled_angles, coef=coef, values=False)
    clean_angles = [original_angles[i] for i in range(len(original_angles)) if i not in outlier_indices]
    return clean_angles

print(3.13 % math.pi)

# Generate 5 random numbers between 3.1 and pi
pos_range = np.random.uniform(3.1, math.pi, size=5)

# Generate 5 random numbers between -pi and -3.1
neg_range = np.random.uniform(-math.pi, -3.1, size=5)

# Combine into one array
random_array = np.concatenate((pos_range, neg_range))
random_array = np.append(random_array, [0.5, 0.4, -0.45, 0])  # Adding some non-outlier values for testing



print("Random Array:", random_array)
print(get_circular_outlier_indices(random_array, coef=1.5))

# print(remove_axial_outliers(random_array, coef=1.5))


