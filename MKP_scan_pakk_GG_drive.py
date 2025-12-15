import streamlit as st
import pandas as pd
import gspread
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from datetime import datetime
import time
import pytz

# --- CONFIGURATION ---
SHEET_ID = '1Om9qwShA3hBQgKJPQNbJgDPInm9AQ2hY5Z8OuOpkF08'
SHEET_NAME = 'Data_Pack' 

# --- CSS STYLING ---
st.markdown("""
<style>
div.block-container { padding-top: 1rem; padding-bottom: 1rem; }
h1 { font-size: 1.8rem !important; margin-bottom: 0.5rem; }
.big-font { font-size: 20px !important; font-weight: bold; }
.success-box { padding: 10px; background-color: #d4edda; color: #155724; border-radius: 5px; margin-bottom: 10px; }
</style>
""", unsafe_allow_html=True)

# --- AUTHENTICATION ---
def get_credentials():
    try:
        if "oauth" in st.secrets:
            info = st.secrets["oauth"]
            return Credentials(None, refresh_token=info["refresh_token"], token_uri="https://oauth2.googleapis.com/token", client_id=info["client_id"], client_secret=info["client_secret"])
    except: return None

# --- GOOGLE SHEETS ---
def get_sheet_connection():
    creds = get_credentials()
    if creds:
        gc = gspread.authorize(creds)
        try: return gc.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
        except: return None
    return None

def save_data_to_sheet(user_id, tracking_id, barcode, status, qty, note=""):
    try:
        ws = get_sheet_connection()
        if ws:
            tz = pytz.timezone('Asia/Bangkok')
            ts = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
            # บันทึก Tracking ID ลงในช่อง Order ID เดิม
            ws.append_row([ts, user_id, tracking_id, barcode, status, qty, note])
            return True
    except: return False
    return False

@st.cache_data(ttl=10)
def load_data_from_sheet():
    try:
        ws = get_sheet_connection()
        if ws:
            data = ws.get_all_values()
            if len(data) > 1: return pd.DataFrame(data[1:], columns=data[0])
    except: pass
    return pd.DataFrame(columns=['Timestamp', 'User ID', 'Order ID', 'Barcode', 'Status', 'Qty', 'Note'])

# --- CALLBACKS FOR AUTO-SAVE ---
def on_scan_mode_a():
    """Mode 1: Barcode ค้างไว้ -> ยิง Tracking แล้วบันทึกเลย"""
    tracking = st.session_state.mkp_tracking_a
    barcode = st.session_state.get('locked_barcode', '')
    
    if tracking and barcode:
        success = save_data_to_sheet(st.session_state.user_id, tracking, barcode, "Normal", 1, "Mode A")
        if success:
            st.toast(f"✅ Saved: {tracking}", icon="📦")
            st.session_state.scan_history.insert(0, {"Time": datetime.now().strftime("%H:%M:%S"), "Tracking": tracking, "Item": barcode, "Mode": "1 Barcode -> Many Trackings"})
            # Clear Tracking input only
            st.session_state.mkp_tracking_a = ""
        else:
            st.toast("❌ Error Saving", icon="🔥")

def on_scan_mode_b():
    """Mode 2: ยิง Tracking -> ยิง Barcode -> บันทึก"""
    tracking = st.session_state.mkp_tracking_b
    barcode = st.session_state.mkp_barcode_b
    
    if tracking and barcode:
        success = save_data_to_sheet(st.session_state.user_id, tracking, barcode, "Normal", 1, "Mode B")
        if success:
            st.toast(f"✅ Saved: {tracking}", icon="📦")
            st.session_state.scan_history.insert(0, {"Time": datetime.now().strftime("%H:%M:%S"), "Tracking": tracking, "Item": barcode, "Mode": "1 Barcode -> 1 Tracking"})
            # Clear BOTH inputs
            st.session_state.mkp_tracking_b = ""
            st.session_state.mkp_barcode_b = ""
        else:
            st.toast("❌ Error Saving", icon="🔥")

# --- MAIN APP ---
st.title("📦 MKP Scan & Pack")

if 'user_id' not in st.session_state: st.session_state.user_id = ""
if 'scan_history' not in st.session_state: st.session_state.scan_history = []
if 'locked_barcode' not in st.session_state: st.session_state.locked_barcode = ""

# --- LOGIN ---
if not st.session_state.user_id:
    st.info("ระบุรหัสพนักงาน")
    u = st.text_input("User ID", key="login")
    if st.button("Start") and u: st.session_state.user_id = u; st.rerun()
else:
    with st.sidebar:
        st.write(f"👤 **{st.session_state.user_id}**")
        if st.button("Logout"): st.session_state.user_id = ""; st.rerun()

    tab1, tab2 = st.tabs(["📷 Scan Work", "📊 Dashboard"])

    with tab1:
        # เลือกโหมดการทำงาน
        scan_mode = st.radio(
            "เลือกรูปแบบงาน:",
            ["🚀 1. สินค้าเดียว -> หลาย Tracking", "📦 2. งานปกติ (1 Tracking : 1 Barcode)"],
            horizontal=True
        )
        st.divider()

        # ==========================================
        # MODE A: 1 Barcode -> Many Trackings
        # ==========================================
        if "1." in scan_mode:
            st.info("💡 วิธีใช้: สแกนสินค้าต้นแบบ 1 ครั้ง -> แล้วยิง Tracking รัวๆ")
            
            # Step 1: Set Master Barcode
            col_m1, col_m2 = st.columns([3, 1])
            with col_m1:
                if not st.session_state.locked_barcode:
                    master_bc = st.text_input("1. สแกนสินค้าต้นแบบ (Master Barcode)", key="master_bc_input")
                    if master_bc:
                        st.session_state.locked_barcode = master_bc
                        st.rerun()
                else:
                    st.success(f"🔒 สินค้าล็อคแล้ว: **{st.session_state.locked_barcode}**")
            with col_m2:
                if st.session_state.locked_barcode:
                    if st.button("❌ เปลี่ยนสินค้า"):
                        st.session_state.locked_barcode = ""
                        st.rerun()

            # Step 2: Scan Tracking Loop
            if st.session_state.locked_barcode:
                st.write("👇 **2. สแกน Tracking (บันทึกอัตโนมัติ)**")
                # ใช้ on_change เพื่อบันทึกทันทีที่ยิงเสร็จ
                st.text_input("ยิง Tracking ID ที่นี่...", key="mkp_tracking_a", on_change=on_scan_mode_a, help="ยิงปุ๊บ บันทึกปั๊บ")
                
                # --- แก้ไขจุด Error ตรงนี้ ---
                # เปลี่ยนจาก if st.button(...): func() เป็น st.button(..., on_click=func)
                st.button("💾 บันทึกมือ (กรณีไม่ Auto)", key="btn_save_a", on_click=on_scan_mode_a)

        # ==========================================
        # MODE B: 1 Tracking -> 1 Barcode
        # ==========================================
        else:
            st.info("💡 วิธีใช้: สแกน Tracking -> สแกนสินค้า -> ระบบบันทึกและเคลียร์ค่า")
            
            c1, c2 = st.columns(2)
            with c1:
                # ช่อง Tracking
                st.text_input("1. Tracking ID", key="mkp_tracking_b")
            with c2:
                # ช่อง Barcode (ใส่ Logic on_change ไว้ที่นี่ เพราะเป็นขั้นตอนสุดท้าย)
                st.text_input("2. Product Barcode", key="mkp_barcode_b", on_change=on_scan_mode_b)

            # --- แก้ไขจุด Error ตรงนี้ด้วย ---
            st.button("💾 บันทึก (Save)", key="btn_save_b", on_click=on_scan_mode_b)

        # --- HISTORY LOG ---
        if st.session_state.scan_history:
            st.divider()
            st.caption("ประวัติการทำงานล่าสุด")
            st.dataframe(pd.DataFrame(st.session_state.scan_history), use_container_width=True, hide_index=True)

    with tab2:
        if st.button("🔄 Refresh Data"): st.cache_data.clear(); st.rerun()
        df = load_data_from_sheet()
        if not df.empty:
            # เปลี่ยน Label ในกราฟให้ตรงกับ Tracking ID
            df.rename(columns={'Order ID': 'Tracking ID'}, inplace=True)
            st.write(f"Total Scans: {len(df)}")
            st.dataframe(df.tail(10), use_container_width=True) # โชว์ 10 รายการล่าสุด
