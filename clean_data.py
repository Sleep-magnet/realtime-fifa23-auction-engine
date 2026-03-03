import pandas as pd

# Load dataset
df = pd.read_csv("Fifa 23 Players Data.csv")

# Clean column names
df.columns = df.columns.str.strip()

# Rename columns
df.rename(columns={
    "Known As": "name",
    "Full Name": "full_name",
    "Overall": "rating",
    "Potential": "potential",
    "Value(in Euro)": "price",
    "Positions Played": "positions",
    "Best Position": "position",
    "Nationality": "nation",
    "Image Link": "image",
    "Age": "age"
}, inplace=True)

# Remove empty players
df = df[df["name"].notna()]
df = df[df["rating"].notna()]

# Remove duplicates
df.drop_duplicates(subset=["full_name"], inplace=True)

# ⭐ SET ALL PLAYER PRICES TO ZERO
df["price"] = 0

# Reset index
df.reset_index(drop=True, inplace=True)

df = df[df["rating"] >= 77]

df.to_csv("players_cleaned.csv", index=False)
print(df.tail(25))
print("✅ All player prices set to 0")
print("Total players:", len(df))