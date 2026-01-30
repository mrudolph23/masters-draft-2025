import streamlit as st
import pandas as pd
import os
import time
from dotenv import load_dotenv
from supabase import create_client

# 1. Setup Connection
# This block allows the app to work both Locally AND on the Cloud
try:
    # Try to get secrets from the Cloud's secure vault first
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
except FileNotFoundError:
    # If not on the cloud, look for the local .env file
    load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")

supabase = create_client(url, key)

st.set_page_config(page_title="Masters Draft 2025", layout="wide")
st.title("⛳ The Masters 2025 Draft")

# --- HELPER FUNCTIONS ---

def get_tournament_id():
    # Hardcoded for now, but you could make this dynamic later
    res = supabase.table("tournaments").select("id").eq("name", "The Masters 2025").single().execute()
    return res.data['id']

def get_current_state(t_id):
    # 1. Get the current pick number
    status = supabase.table("draft_status").select("*").eq("tournament_id", t_id).single().execute()
    current_pick_num = status.data['current_pick_number']
    
    # 2. Who owns this pick slot?
    order = supabase.table("draft_order").select("user_id, position, profiles(nickname)").eq("tournament_id", t_id).eq("position", current_pick_num).single().execute()
    
    if not order.data:
        return None, None, None # Draft is over
        
    picker_name = order.data['profiles']['nickname']
    picker_id = order.data['user_id']
    return current_pick_num, picker_name, picker_id

def get_available_golfers(t_id, tier):
    # 1. Get IDs of golfers who have ALREADY been picked
    picked_res = supabase.table("picks").select("golfer_id").eq("tournament_id", t_id).execute()
    picked_ids = [row['golfer_id'] for row in picked_res.data]
    
    # 2. Get golfers in the field for this tier
    # We ask for:
    # - golfer_id (from tournament_field)
    # - tier (from tournament_field)
    # - world_ranking (from tournament_field - this is likely the one we want)
    # - golfers (the joined table) -> name
    response = supabase.table("tournament_field").select(
        "golfer_id, tier, world_ranking, golfers(name)"
    ).eq("tournament_id", t_id).eq("tier", tier).execute()
    
    golfers = []
    for row in response.data:
        # ONLY add them if they are NOT in the picked list
        if row['golfer_id'] not in picked_ids:
            
            # SAFE DATA EXTRACTION
            # We use .get() so the app doesn't crash if a field is missing
            g_name = row['golfers']['name'] if row['golfers'] else "Unknown"
            g_rank = row.get('world_ranking', 999) # Default to 999 if missing
            
            golfers.append({
                "id": row['golfer_id'],
                "name": g_name,
                "rank": g_rank,
                "display": f"{g_name} (Rank: {g_rank})"
            })
            
    # Sort by Rank
    df = pd.DataFrame(golfers)
    if not df.empty:
        df = df.sort_values('rank')
    return df

def submit_pick(t_id, user_id, golfer_id, golfer_name, pick_num):
    # A. Record the pick
    supabase.table("picks").insert({
        "tournament_id": t_id,
        "user_id": user_id,
        "golfer_id": golfer_id
    }).execute()
    
    # B. Move to next pick
    supabase.table("draft_status").update({"current_pick_number": pick_num + 1}).eq("tournament_id", t_id).execute()
    
    # C. Celebration and Reload
    st.toast(f"✅ Pick Confirmed: {golfer_name}!")
    time.sleep(1) # Pause so they see the success message
    st.rerun()

# --- MAIN APP UI ---

try:
    t_id = get_tournament_id()
    pick_num, picker_name, picker_id = get_current_state(t_id)

    # HEADER SECTION
    if pick_num:
        col1, col2 = st.columns([1, 3])
        with col1:
            st.metric("Current Pick", f"#{pick_num}")
        with col2:
            st.info(f"👉 **It is {picker_name}'s Turn!**")
            
        st.divider()
        
        # DRAFTING SECTION
        st.subheader(f"Select a Golfer for {picker_name}")
        
        # We use tabs to organize by Tier
        tab1, tab2, tab3 = st.tabs(["Tier 1 (Top 10)", "Tier 2 (Next 40)", "Tier 3 (Field)"])
        
        # We create a reusable function to render the input box inside any tab
        def render_draft_tab(tier_num):
            df = get_available_golfers(t_id, tier_num)
            if df.empty:
                st.write("No golfers left in this tier!")
                return
            
            # The Dropdown
            # We use a unique key per tab so Streamlit doesn't get confused
            selected_golfer_name = st.selectbox(
                f"Choose a Tier {tier_num} Golfer:", 
                df['display'], 
                key=f"select_t{tier_num}"
            )
            
            # Find the ID of the selected golfer
            # (We look up the row where 'display' matches the selection)
            selected_row = df[df['display'] == selected_golfer_name].iloc[0]
            
            # The 'Big Green Button'
            if st.button(f"Draft {selected_row['name']}", key=f"btn_t{tier_num}", type="primary"):
                submit_pick(t_id, picker_id, selected_row['id'], selected_row['name'], pick_num)

        with tab1:
            render_draft_tab(1)
        with tab2:
            render_draft_tab(2)
        with tab3:
            render_draft_tab(3)

    else:
        st.balloons()
        st.success("🎉 The Draft is Complete!")
        st.write("Check the 'Teams' page to see the final rosters.")

except Exception as e:
    st.error(f"Something went wrong: {e}")
    # Helpful debug tip for you:
    st.write("Check your database tables to make sure 'The Masters 2025' exists and draft_status is set to 1.")

# --- ADD THIS TO THE BOTTOM OF YOUR MAIN APP ---

st.divider()
st.subheader("📊 Current Rosters")

def get_rosters(t_id):
    # Fetch all picks made so far
    # We join: picks -> profiles (Who picked) AND picks -> golfers (Who they picked)
    response = supabase.table("picks").select(
        "user_id, profiles(nickname), golfers(name, world_ranking)"
    ).eq("tournament_id", t_id).execute()
    
    data = []
    for row in response.data:
        data.append({
            "Team Captain": row['profiles']['nickname'],
            "Golfer": row['golfers']['name'],
            "Rank": row['golfers']['world_ranking']
        })
        
    return pd.DataFrame(data)

# Load and Display the Rosters
roster_df = get_rosters(t_id)

if not roster_df.empty:
    # We pivot the table so each Buddy is a column
    # This makes it look like a real draft board
    
    # 1. Create a "Round" column for each team
    roster_df['Pick #'] = roster_df.groupby('Team Captain').cumcount() + 1
    
    # 2. Pivot: Columns = Captains, Values = Golfers
    pivot_df = roster_df.pivot(index='Pick #', columns='Team Captain', values='Golfer')
    
    st.dataframe(pivot_df, use_container_width=True)
else:
    st.write("Waiting for the first pick...")