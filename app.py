import streamlit as st
import pandas as pd
import time
from supabase import create_client
from dotenv import load_dotenv
import os

# --- 1. SETUP & CONNECTION ---
st.set_page_config(page_title="Masters 2025", layout="wide")

try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
except FileNotFoundError:
    load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")

supabase = create_client(url, key)

# --- 2. HELPER FUNCTIONS ---
def get_tournament_id():
    # We use .execute() instead of .single() to prevent crashes
    res = supabase.table("tournaments").select("id").eq("name", "The Masters 2026").execute()
    
    if res.data: 
        # Just grab the very first ID in the list, even if there are multiples
        return res.data[0]['id'] 
        
    return None

def get_buddies(t_id):
    # Get list of all users for the login dropdown
    # We join draft_order just to make sure they are in the tournament
    res = supabase.table("profiles").select("nickname").execute()
    return sorted([row['nickname'] for row in res.data])

def get_draft_board(t_id):
    # Get all picks to display the grid
    res = supabase.table("picks").select("user_id, profiles(nickname), golfer_id, golfers(name)").eq("tournament_id", t_id).execute()
    if not res.data: return pd.DataFrame()
    
    data = []
    for row in res.data:
        data.append({
            "User": row['profiles']['nickname'],
            "Golfer": row['golfers']['name']
        })
    
    df = pd.DataFrame(data)
    # Add a "Round" column by counting picks per user
    df['Round'] = df.groupby('User').cumcount() + 1
    
    # Pivot: Rows = Round, Cols = User
    pivot_df = df.pivot(index='Round', columns='User', values='Golfer')
    return pivot_df

def get_leaderboard(t_id):
    # (Your existing Leaderboard Logic)
    picks_res = supabase.table("picks").select("user_id, profiles(nickname), golfers(id, name)").eq("tournament_id", t_id).execute()
    scores_res = supabase.table("player_scores").select("golfer_id, total_score, thru, status, r1, r2, r3, r4").eq("tournament_id", t_id).execute()
    
    if not picks_res.data: return pd.DataFrame() 

    picks_df = pd.json_normalize(picks_res.data)
    if 'profiles.nickname' not in picks_df.columns: picks_df['profiles.nickname'] = "Unknown"
    if 'golfers.name' not in picks_df.columns: picks_df['golfers.name'] = "Unknown Golfer"
    if 'golfers.id' not in picks_df.columns: picks_df['golfers.id'] = None

    picks_df = picks_df.rename(columns={'profiles.nickname': 'Team Captain', 'golfers.name': 'Golfer', 'golfers.id': 'golfer_id'})
    
    if not scores_res.data:
        for col in ['total_score', 'r1', 'r2', 'r3', 'r4']: picks_df[col] = 0
        picks_df['thru'] = '-'
        return picks_df

    scores_df = pd.DataFrame(scores_res.data)
    full_df = pd.merge(picks_df, scores_df, on='golfer_id', how='left')
    
    cols_to_fix = ['total_score', 'r1', 'r2', 'r3', 'r4']
    for col in cols_to_fix:
        if col not in full_df.columns: full_df[col] = 0
        full_df[col] = full_df[col].fillna(0).astype(int)
        
    full_df['thru'] = full_df['thru'].fillna('-')
    return full_df

# --- 3. MAIN APP UI ---

st.title("⛳ The Masters 2026")
t_id = get_tournament_id()

if not t_id:
    st.error("Tournament Setup Required.")
    st.stop()

# --- AUTHENTICATION LOGIC ---

# 1. Try to get the email (Works on Cloud, Fails on Local)
try:
    # On Streamlit Cloud, this returns the user's email
    user_email = st.experimental_user.email
except AttributeError:
    # On Localhost, this attribute doesn't exist, so we default to None
    user_email = None

# 2. MANUAL LOGIN (If Streamlit Cloud email isn't found)
if not user_email:
    st.sidebar.warning("⚠️ Authentication Required")
    
    # The Bouncer: Ask for a shared league password
    league_password = st.sidebar.text_input("Enter League Password:", type="password")
    
    # If they type the wrong password (or nothing), STOP the app completely
    if league_password != "80085":  # <-- Change "greenjacket" to whatever you want!
        st.error("Please enter the correct password in the sidebar to enter the Draft Room.")
        st.stop() # This is the emergency brake!
        
    # If they get the password right, let them select who they are
    st.sidebar.success("Password accepted!")
    all_buddies = get_buddies(t_id)
    
    selected_nickname = st.sidebar.selectbox("Who are you drafting for?", all_buddies)
    
    # Fetch profile based on the manual selection
    user_profile = supabase.table("profiles").select("*").eq("nickname", selected_nickname).single().execute()

else:
    # 3. REAL MODE (Cloud)
    st.sidebar.success(f"Logged in as: {user_email}")
    
    # Look up the email in your database
    user_profile = supabase.table("profiles").select("*").eq("email", user_email).execute()
    
    if not user_profile.data:
        st.error(f"🚫 ACCESS DENIED. The email '{user_email}' is not found in the player list. Please contact the Commissioner.")
        st.stop()
        
    selected_nickname = user_profile.data[0]['nickname']

# 4. Set Current User Variables
current_user_id = user_profile.data['id'] if user_profile.data else None
# If we used .execute() (list) vs .single() (dict), handle both safely:
if isinstance(user_profile.data, list):
     current_user_id = user_profile.data[0]['id']
     selected_nickname = user_profile.data[0]['nickname']
else:
     current_user_id = user_profile.data['id']
     selected_nickname = user_profile.data['nickname']

current_user_name = selected_nickname

st.sidebar.write(f"Welcome, **{current_user_name}**!")
st.sidebar.divider()
st.sidebar.write("Draft Rules:")
st.sidebar.caption("• 1 Golfer from Tier 1\n• 2 Golfers from Tier 2\n• 1 Golfer from Tier 3")

# ... (Rest of Tabs and Draft Logic) ...

# CRITICAL UPDATE IN DRAFT LOGIC:
# Change the permission check to use 'current_user_name' instead of 'selected_user'

# Find this line in your Tab 1 logic:
# if selected_user == picker_name:

# Change it to:
# if current_user_name == picker_name:


# TABS
tab_draft, tab_board = st.tabs(["📝 Draft Room", "🏆 Live Leaderboard"])

# --- TAB 1: DRAFT ROOM ---
with tab_draft:
    # 1. SHOW THE BIG BOARD (Draft History)
    st.subheader("Draft Board")
    board_df = get_draft_board(t_id)
    if not board_df.empty:
        st.dataframe(board_df, use_container_width=True)
    else:
        st.write("Draft hasn't started yet.")
    
    st.divider()

    # 2. GET CURRENT STATUS
    status = supabase.table("draft_status").select("*").eq("tournament_id", t_id).execute()
    current_pick = status.data[0]['current_pick_number'] if status.data else 1
    
    draft_order = supabase.table("draft_order").select("user_id, profiles(nickname)").eq("tournament_id", t_id).eq("position", current_pick).execute()
    
    if draft_order.data:
        picker_name = draft_order.data[0]['profiles']['nickname']
        picker_id = draft_order.data[0]['user_id']
        
        # 3. ON THE CLOCK DISPLAY
        col1, col2 = st.columns([2, 3])
        col1.info(f"👉 **Pick #{current_pick}**")
        
        # 4. PERMISSION CHECK (The "Traffic Cop")
        if current_user_name == picker_name:
            col2.success(f"**IT IS YOUR TURN, {picker_name.upper()}!**")
            
            # --- SHOW DRAFT CONTROLS (Only for the correct user) ---
            
            # (Your Existing Flexible Draft Logic)
            my_picks_res = supabase.table("picks").select("golfer_id").eq("tournament_id", t_id).eq("user_id", picker_id).execute()
            my_picked_ids = [p['golfer_id'] for p in my_picks_res.data]
            field_res = supabase.table("tournament_field").select("golfer_id, tier, golfers(name, world_ranking)").eq("tournament_id", t_id).execute()
            golfer_tier_map = {row['golfer_id']: row['tier'] for row in field_res.data}
            
            t1_count = sum(1 for pid in my_picked_ids if golfer_tier_map.get(pid) == 1)
            t2_count = sum(1 for pid in my_picked_ids if golfer_tier_map.get(pid) == 2)
            t3_count = sum(1 for pid in my_picked_ids if golfer_tier_map.get(pid) == 3)
            
            st.write(f"**Your Roster:** T1: {t1_count}/1 | T2: {t2_count}/2 | T3: {t3_count}/1")
            
            allowed_tiers = []
            if t1_count < 1: allowed_tiers.append(1)
            if t2_count < 2: allowed_tiers.append(2)
            if t3_count < 1: allowed_tiers.append(3)
            
            if allowed_tiers:
                tier_labels = {1: "Tier 1 (Rank 1-10)", 2: "Tier 2 (Rank 11-50)", 3: "Tier 3 (Rank 51+)"}
                options = [tier_labels[t] for t in allowed_tiers]
                selected_label = st.radio("Filter by Tier:", options, horizontal=True)
                selected_tier = [k for k, v in tier_labels.items() if v == selected_label][0]
                
                all_picked_res = supabase.table("picks").select("golfer_id").eq("tournament_id", t_id).execute()
                globally_picked_ids = [p['golfer_id'] for p in all_picked_res.data]
                
                available_golfers = []
                for row in field_res.data:
                    if row['tier'] == selected_tier and row['golfer_id'] not in globally_picked_ids:
                        available_golfers.append(f"{row['golfers']['name']} (Rank: {row['golfers']['world_ranking']})")
                
                if available_golfers:
                    selection = st.selectbox("Select Golfer:", available_golfers)
                    if st.button("Confirm Pick"):
                        g_name = selection.split(" (Rank")[0]
                        g_id = next(item['golfer_id'] for item in field_res.data if item['golfers']['name'] == g_name)
                        
                        supabase.table("picks").insert({"tournament_id": t_id, "user_id": picker_id, "golfer_id": g_id}).execute()
                        supabase.table("draft_status").update({"current_pick_number": current_pick + 1}).eq("tournament_id", t_id).execute()
                        st.rerun()
                else:
                    st.warning(f"No golfers left in Tier {selected_tier}!")
            else:
                st.error("Roster Full!")
                
        else:
            # --- HIDE CONTROLS (If you are not the picker) ---
            col2.warning(f"Waiting for **{picker_name}** to pick...")
            st.caption("Controls are hidden because it is not your turn.")
            
            # Auto-refresh so they see when the pick is made
            time.sleep(5)
            st.rerun()

    else:
        st.balloons()
        st.success("🎉 **DRAFT COMPLETE!**")

# --- TAB 2: LIVE LEADERBOARD (Your existing code) ---
with tab_board:
    st.header("🏆 Live Team Standings")
    if st.button("🔄 Refresh Scores"): st.rerun()
    
    df = get_leaderboard(t_id)
    if not df.empty:
        team_ranks = df.groupby('Team Captain')['total_score'].sum().sort_values(ascending=True)
        for captain, team_total in team_ranks.items():
            with st.container():
                c1, c2 = st.columns([3, 1])
                rank = list(team_ranks.index).index(captain) + 1
                c1.subheader(f"#{rank} {captain}")
                c2.markdown(f"<h3 style='text-align: right;'>{team_total}</h3>", unsafe_allow_html=True)
                
                team_df = df[df['Team Captain'] == captain].copy()
                display_df = team_df[['Golfer', 'r1', 'r2', 'r3', 'r4', 'total_score', 'thru']]
                display_df.columns = ['Golfer', 'R1', 'R2', 'R3', 'R4', 'Tot', 'Thru']
                display_df = display_df.replace(0, "-")
                st.dataframe(display_df, use_container_width=True, hide_index=True)
                st.divider()
    else:
        st.info("No teams drafted yet.")