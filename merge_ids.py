import pandas as pd

def extract_player_ids():
    print("🚀 Booting up the Database Upgrader...")

    # Load your main dataset
    df = pd.read_csv('players_cleaned.csv')

    # The Ultimate Trick: Extract ID directly from the image URL
    print("🔍 Extracting hidden EA Player IDs from image links...")
    df['player_id'] = df['image'].str.extract(r'players/(\d+)/(\d+)/').apply(
        lambda x: x[0] + x[1] if pd.notnull(x[0]) else None, axis=1
    )
    
    # Format cleanly as integers
    df['player_id'] = pd.to_numeric(df['player_id'], errors='coerce').astype('Int64')

    # Save the new file
    df.to_csv('players_cleaned_with_ids.csv', index=False)
    
    print(f"🎉 BOOM! Successfully added player_id to {df['player_id'].notnull().sum()} out of {len(df)} players.")
    print("✅ Saved as 'players_cleaned_with_ids.csv'")

if __name__ == "__main__":
    extract_player_ids()