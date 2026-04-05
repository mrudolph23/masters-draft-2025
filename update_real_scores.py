import requests
import pandas as pd
import os
import time
from dotenv import load_dotenv
from supabase import create_client

# 1. SETUP
load_dotenv()
supabase = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))

# CONFIGURATION
# Remember to update ?event=XXXX for the Masters!
ESPN_API_URL = "https://site.api.espn.com/apis/site/v2/sports/golf/leaderboard?tournamentId=401811940"

def clean_name(name):
    """Normalize names for matching"""
    if not name: return ""
    return name.lower().strip().replace(".", "").replace("'", "")

def update_scores():
    print(f"Fetching Live Data from ESPN...")
    
    try:
        data = requests.get(ESPN_API_URL).json()
        if 'events' not in data or not data['events']:
            print("No active tournament data found.")
            return
            
        event = data['events'][0]
        competition = event['competitions'][0]
        tournament_name = event['name']
        
        # --- NEW: CHECK CURRENT ROUND ---
        # 'period' tells us if it is Round 1, 2, 3, or 4
        current_round = competition['status']['period']
        print(f"Tournament: {tournament_name} | Current Round: {current_round}")
        
        competitors = competition['competitors']
    except Exception as e:
        print(f"Error fetching from ESPN: {e}")
        return

    # Database Setup
    t_res = supabase.table("tournaments").select("id").eq("name", "The Masters 2026").single().execute()
    t_id = t_res.data['id']
    
    db_golfers = supabase.table("tournament_field").select("golfer_id, golfers(name)").eq("tournament_id", t_id).execute()
    id_map = {clean_name(row['golfers']['name']): row['golfer_id'] for row in db_golfers.data}
    
    updates_count = 0
    
    for player in competitors:
        athlete = player.get('athlete', {})
        espn_name = clean_name(athlete.get('displayName', ''))
        
        if espn_name in id_map:
            g_id = id_map[espn_name]
            
            # 1. Get Real Scores
            linescores = player.get('linescores', [])
            
            def get_round_score(index):
                if index < len(linescores):
                    val = linescores[index].get('value', 0)
                    return int(float(val))
                return 0

            r1 = get_round_score(0)
            r2 = get_round_score(1)
            r3 = get_round_score(2)
            r4 = get_round_score(3)
            
            # 2. Check Status (CUT, WD, DQ)
            status_data = player.get('status', {})
            status_text = status_data.get('type', {}).get('shortDetail', 'Active')
            
            # Normalize status to uppercase for checking
            status_upper = status_text.upper()
            is_cut = "CUT" in status_upper or "W/D" in status_upper or "DQ" in status_upper
            
            # 3. APPLY THE "80 RULE"
            # If they missed the cut, we override their R3/R4 scores based on the day
            if is_cut:
                # If the tournament has reached Round 3, apply penalty for R3
                if current_round >= 3:
                    r3 = 80
                # If the tournament has reached Round 4, apply penalty for R4
                if current_round >= 4:
                    r4 = 80
            
            # 4. Calculate Total
            total_strokes = r1 + r2 + r3 + r4
            
            score_record = {
                "tournament_id": t_id,
                "golfer_id": g_id,
                "r1": r1,
                "r2": r2,
                "r3": r3,
                "r4": r4,
                "total_score": total_strokes,
                "status": status_text, # Keep the text so UI shows "CUT"
                "thru": status_text, 
                "updated_at": pd.Timestamp.now().isoformat()
            }
            
            supabase.table("player_scores").upsert(score_record, on_conflict="golfer_id, tournament_id").execute()
            updates_count += 1
            
    print(f"✅ Sync Complete: Updated {updates_count} golfers.")

if __name__ == "__main__":
    # Standard loop to run continuously
    print("🤖 Scraper Active. Ctrl+C to stop.")
    while True:
        try:
            update_scores()
        except Exception as e:
            print(f"Error: {e}")
        print("💤 Sleeping for 30 minutes...")
        time.sleep(1800)