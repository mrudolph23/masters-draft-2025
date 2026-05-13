import streamlit as st
import pandas as pd
import time
from supabase import create_client
from dotenv import load_dotenv
import os

# --- 1. SETUP & CONNECTION ---
st.set_page_config(page_title="PGA Championship 2026", layout="wide")

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
    res = supabase.table("tournaments").select("id").eq("name", "PGA Championship 2026").execute()
    if res.data: 
        return res.data[0]['id'] 
    return None

def get_buddies(t_id):
    res = supabase.table("profiles").select("nickname").execute()
    return sorted([row['nickname'] for row in res.data])

def get_full_draft_order(t_id):
    res = supabase.table("draft_order").select("position, profiles(nickname)").eq("tournament_id", t_id).order("position").execute()
    if not res.data: 
        return pd.DataFrame()
        
    data = [{"Pick": row['position'], "Manager": row['profiles']['nickname']} for row in res.data]
    return pd.DataFrame(data)

def get_draft_board(t_id):
    res = supabase.table("picks").select("user_id, profiles(nickname), golfer_id, golfers(name)").eq("tournament_id", t_id).execute()
    if not res.data: return pd.DataFrame()
    
    data = []
    for row in res.data:
        data.append({
            "User": row['profiles']['nickname'],
            "Golfer": row['golfers']['name']
        })
    
    df = pd.DataFrame(data)
    df['Round'] = df.groupby('User').cumcount() + 1
    pivot_df = df.pivot(index='Round', columns='User', values='Golfer')
    return pivot_df

def get_leaderboard(t_id):
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

st.title("⛳ PGA Championship 2026")
t_id = get_tournament_id()

if not t_id:
    st.error("Tournament Setup Required.")
    st.stop()

# --- AUTHENTICATION LOGIC ---
if "logged_in_user" not in st.session_state:
    st.session_state.logged_in_user = None

if not st.session_state.logged_in_user:
    st.sidebar.warning("⚠️ Authentication Required")
    entered_email = st.sidebar.text_input("Enter your Email Address:")
    
    if not entered_email:
        st.stop()
        
    clean_email = entered_email.strip().lower()
    user_profile = supabase.table("profiles").select("*").eq("email", clean_email).execute()
    
    if not user_profile.data:
        st.sidebar.error("Email not found in the league directory. Check your spelling.")
        st.stop()
        
    if st.sidebar.button("Log In"):
        st.session_state.logged_in_user = user_profile.data[0]
        st.rerun() 
        
    st.stop()

# --- IF THEY ARE LOGGED IN ---
current_user = st.session_state.logged_in_user
current_user_id = current_user['id']
current_user_name = current_user['nickname']

st.sidebar.success(f"Logged in as: {current_user_name}")

if st.sidebar.button("Log Out"):
    st.session_state.logged_in_user = None
    st.rerun()

st.sidebar.divider()
st.sidebar.write(f"Welcome, **{current_user_name}**!")

with st.sidebar.expander("📋 Full Draft Order", expanded=False):
    order_df = get_full_draft_order(t_id)
    if not order_df.empty:
        st.dataframe(order_df, use_container_width=True, hide_index=True)
    else:
        st.write("Draft order not set.")

st.sidebar.write("Draft Rules:")
st.sidebar.caption("Draft Anyone You Can Get Your Hands On")

# TABS
tab_draft, tab_board = st.tabs(["📝 Draft Room", "🏆 Live Leaderboard"])

# --- TAB 1: DRAFT ROOM ---
with tab_draft:
    st.subheader("Draft Board")
    board_df = get_draft_board(t_id)
    if not board_df.empty:
        st.dataframe(board_df, use_container_width=True)
    else:
        st.write("Draft hasn't started yet.")
    
    st.divider()

    status = supabase.table("draft_status").select("*").eq("tournament_id", t_id).execute()
    current_pick = status.data[0]['current_pick_number'] if status.data else 1
    
    draft_order = supabase.table("draft_order").select("user_id, profiles(nickname)").eq("tournament_id", t_id).eq("position", current_pick).execute()
    
    if draft_order.data:
        picker_name = draft_order.data[0]['profiles']['nickname']
        picker_id = draft_order.data[0]['user_id']
        
        col1, col2 = st.columns([2, 3])
        col1.info(f"👉 **Pick #{current_pick}**")
        
        if current_user_name == picker_name:
            col2.success(f"**IT IS YOUR TURN, {picker_name.upper()}!**")
            st.subheader("🏆 Best Player Available")

            picks_res = supabase.table("picks").select("golfer_id").eq("tournament_id", t_id).execute()
            drafted_ids = [pick['golfer_id'] for pick in picks_res.data]

            field_res = supabase.table("tournament_field").select(
                "golfer_id, golfers(name, owgr_rank)"
            ).eq("tournament_id", t_id).execute()

            available_golfers = []
            for row in field_res.data:
                g_id = row['golfer_id']
                if g_id not in drafted_ids:
                    name = row['golfers']['name']
                    rank = row['golfers']['owgr_rank']
                    sort_rank = rank if rank is not None else 999 
                    
                    available_golfers.append({
                        "id": g_id,
                        "name": name,
                        "rank": rank,
                        "sort_rank": sort_rank
                    })

            available_golfers = sorted(available_golfers, key=lambda x: x['sort_rank'])

            display_options = {
                g['id']: f"({g['rank'] if g['rank'] else 'UR'}) {g['name']}"
                for g in available_golfers
            }

            selected_golfer_id = st.selectbox(
                "On the Clock:",
                options=list(display_options.keys()),
                format_func=lambda x: display_options[x]
            )

            if st.button("🚨 DRAFT PLAYER 🚨", use_container_width=True):
                record = {
                    "tournament_id": t_id,
                    "user_id": picker_id,
                    "golfer_id": selected_golfer_id
                }
                supabase.table("picks").insert(record).execute()
                supabase.table("draft_status").update({"current_pick_number": current_pick + 1}).eq("tournament_id", t_id).execute()
                
                st.success(f"Pick locked in!")
                st.rerun()

        else:
            col2.warning(f"Waiting for **{picker_name}** to pick...")
            st.caption("Controls are hidden because it is not your turn.")
            time.sleep(5)
            st.rerun()

    else:
        st.balloons()
        st.success("🎉 **DRAFT COMPLETE!**")

# --- TAB 2: LIVE LEADERBOARD ---
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