import os
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
supabase = create_client(url, key)

def sync_from_csv():
    # 1. Get Tournament ID
    query = supabase.table("tournaments").select("id").eq("name", "The Masters 2025").execute()
    if not query.data:
        print("Error: Tournament not found.")
        return
    t_id = query.data[0]['id']

    print("Reading rankings.csv...")
    # 2. Read only the columns we need by name (case-insensitive)
    # This looks for 'Ranking' and 'NAME' specifically
    df = pd.read_csv("rankings.csv")
    df.columns = df.columns.str.strip() # Remove any accidental spaces

# 1. Clean the headers: Turn "Ranking " into "RANKING"
    df.columns = df.columns.str.strip().str.upper()
    
    # 2. Debug: Print what columns Python actually sees (so we know if it worked)
    print(f"Columns found in CSV: {df.columns.tolist()}")
    
    # We map your CSV headers to our database headers
    # Make sure your CSV has a column exactly named 'Ranking' and 'NAME'
    df = df[['RANKING', 'NAME']].copy()
    df.columns = ['world_ranking', 'name']

    # 3. Data Cleaning (The 'nan' fix)
    df['world_ranking'] = pd.to_numeric(df['world_ranking'], errors='coerce')
    df = df.dropna(subset=['name', 'world_ranking'])
    
    # 4. Relative Tiers
    df = df.sort_values('world_ranking').reset_index(drop=True)
    def get_tier(index):
        if index < 10: return 1
        if index < 50: return 2
        return 3

    df['tier'] = df.index.map(get_tier)
    df['field_rank'] = df.index + 1

    print(f"Syncing {len(df)} golfers to Supabase...")
    for _, row in df.iterrows():
        # Update master golfers list
        g_resp = supabase.table("golfers").upsert({
            "name": row['name'], 
            "world_ranking": int(row['world_ranking'])
        }, on_conflict='name').execute()
        g_id = g_resp.data[0]['id']

        # Update specific tournament field
        supabase.table("tournament_field").upsert({
            "tournament_id": t_id,
            "golfer_id": g_id,
            "world_ranking": int(row['world_ranking']),
            "field_rank": row['field_rank'],
            "tier": row['tier']
        }, on_conflict='tournament_id,golfer_id').execute()

    print(f"Success! {len(df)} golfers are ready for the draft.")

if __name__ == "__main__":
    sync_from_csv()