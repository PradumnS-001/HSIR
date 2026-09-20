import numpy as np
import pandas as pd

# Generate 20-day placeholder event window data (t=-10 to t=+10)
np.random.seed(42)
days = np.arange(-10, 11)
market_return = np.random.normal(0.0005, 0.01, len(days))
actual_return = np.random.normal(0.0005, 0.015, len(days))

# Add a simulated market shock at t=0 for the conflict event
actual_return[10] += 0.04

df = pd.DataFrame(
    {"Event_Day": days, "Market_Return": market_return, "Actual_Return": actual_return}
)

# Placeholder alpha and beta from the 60-day estimation window
alpha = 0.0001
beta = 1.1

# Calculate Expected Return, AR, and CAR
df["Expected_Return"] = alpha + (beta * df["Market_Return"])
df["Abnormal_Return"] = df["Actual_Return"] - df["Expected_Return"]
df["Cumulative_Abnormal_Return"] = df["Abnormal_Return"].cumsum()

print(
    df[
        ["Event_Day", "Actual_Return", "Abnormal_Return", "Cumulative_Abnormal_Return"]
    ].head(15)
)
