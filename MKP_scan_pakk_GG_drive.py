import streamlit as st
import pandas as pd
import gspread
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from datetime import datetime
import time
import pytz
import uuid

# --- CONFIGURATION ---
SHEET_ID = '1Om9qwShA3hBQgKJPQNbJgDPInm9AQ2hY5Z8OuOpkF08'
SHEET_NAME = 'Data_Pack' 

# --- CSS STYLING ---
st.markdown("""
<style>
div.block-container { padding-top: 1rem; padding-bottom: 1rem; }
h1 { font-size: 1.8rem !important; margin-bottom: 0.5rem; }
.big-font { font-size: 20px !important; font-weight: bold; }
/* กล่องแจ้งเตือน Error */
.error-box {
    padding: 1rem;
    background-color: #ffcccc;
    color: #cc0000;
    border-radius: 8px;
    border: 1px solid #cc0000;
    margin-bottom: 1rem;
    font-weight: bold;
    text-align: center;
    font-size: 1.2rem;
}
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

def save_batch_to_sheet(data_list):
    try:
        ws = get_sheet_connection()
        if ws:
            rows_to_add = []
            tz = pytz.timezone('Asia/Bangkok')
            ts = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
            for item in data_list:
                # เพิ่ม License Plate ลงใน Column สุดท้าย
                row = [ts, item['user_id'], item['tracking'], item['barcode'], "Normal", 1, item['mode'], item['license_plate']]
                rows_to_add.append(row)
            ws.append_rows(rows_to_add)
            return True
    except Exception as e:
        st.error(f"Error: {e}")
        return False
    return False

@st.cache_data(ttl=30) 
def load_data_from_sheet():
    try:
        ws = get_sheet_connection()
        if ws:
            data = ws.get_all_values()
            if len(data) > 1:
                df = pd.DataFrame(data[1:], columns=data[0])
                df.columns = df.columns.str.strip()
                return df
    except: pass
    return pd.DataFrame()

# --- SESSION STATE ---
if 'user_id' not in st.session_state: st.session_state.user_id = ""
if 'license_plate' not in st.session_state: st.session_state.license_plate = "" # เก็บทะเบียนรถ
if 'staged_data' not in st.session_state: st.session_state.staged_data = [] 
if 'locked_barcode' not in st.session_state: st.session_state.locked_barcode = ""
if 'scan_error' not in st.session_state: st.session_state.scan_error = None 
if 'play_sound' not in st.session_state: st.session_state.play_sound = None # State สำหรับเล่นเสียง

# --- SOUND SYSTEM ---
def play_audio_feedback():
    """ฟังก์ชันเล่นเสียง (ซ่อน Player ไว้)"""
    if st.session_state.play_sound == 'success':
        # เสียง Beep สั้น
        sound_url = "https://www.soundjay.com/buttons/sounds/button-16.mp3"
        st.audio(sound_url, format="audio/mp3", autoplay=True)
    elif st.session_state.play_sound == 'error':
        # เสียง Buzzer เตือนภัย
        sound_url = "https://www.soundjay.com/buttons/sounds/button-10.mp3"
        st.audio(sound_url, format="audio/mp3", autoplay=True)
    
    # Reset เพื่อไม่ให้เล่นซ้ำตอน Refresh หน้า
    st.session_state.play_sound = None

# --- DUPLICATE CHECK FUNCTION ---
def check_duplicate(tracking):
    for item in st.session_state.staged_data:
        if str(item['tracking']).strip() == str(tracking).strip():
            return True, f"⚠️ ซ้ำในรายการรอ! ({tracking})"

    df = load_data_from_sheet()
    if not df.empty:
        target_col = None
        possible_cols = ['Tracking ID', 'Order ID', 'Tracking', 'tracking_id', 'order_id']
        for col in df.columns:
            if col in possible_cols:
                target_col = col; break
        
        if target_col:
            all_trackings = df[target_col].astype(str).str.strip().values
            if str(tracking).strip() in all_trackings:
                return True, f"⛔ เคยบันทึกไปแล้ว! ({tracking})"
    return False, ""

# --- CALLBACKS ---
def add_to_staging(tracking, barcode, mode):
    st.session_state.scan_error = None
    tracking = tracking.strip()
    barcode = barcode.strip()

    is_dup, msg = check_duplicate(tracking)
    
    if is_dup:
        st.session_state.scan_error = msg 
        st.session_state.play_sound = 'error' # 🔊 Trigger Error Sound
        st.toast(msg, icon="🚫") 
        return 
    
    # ถ้าทะเบียนรถว่าง ให้แจ้งเตือน (แต่ไม่บล็อกการทำงาน หรือจะบล็อกก็ได้)
    if not st.session_state.license_plate:
        st.toast("⚠️ อย่าลืมระบุทะเบียนรถ!", icon="🚛")

    new_item = {
        "id": str(uuid.uuid4()), 
        "user_id": st.session_state.user_id,
        "license_plate": st.session_state.license_plate, # บันทึกทะเบียนรถ
        "tracking": tracking,
        "barcode": barcode,
        "mode": mode,
        "time_scan": datetime.now().strftime("%H:%M:%S")
    }
    st.session_state.staged_data.insert(0, new_item)
    st.session_state.play_sound = 'success' # 🔊 Trigger Success Sound
    st.toast(f"📥 เพิ่มรายการ: {tracking}", icon="➕")

def delete_from_staging(item_id):
    st.session_state.staged_data = [d for d in st.session_state.staged_data if d['id'] != item_id]
    st.toast("ลบรายการแล้ว", icon="🗑️")

def on_scan_mode_a():
    tracking = st.session_state.mkp_tracking_a.strip()
    barcode = st.session_state.get('locked_barcode', '').strip()
    if tracking and barcode:
        add_to_staging(tracking, barcode, "Mode A")
        st.session_state.mkp_tracking_a = "" 

def on_scan_mode_b():
    tracking = st.session_state.mkp_tracking_b.strip()
    barcode = st.session_state.mkp_barcode_b.strip()
    if tracking and barcode:
        add_to_staging(tracking, barcode, "Mode B")
        st.session_state.mkp_tracking_b = ""
        st.session_state.mkp_barcode_b = ""

def confirm_save_all():
    if not st.session_state.staged_data:
        st.warning("ไม่มีรายการให้บันทึก")
        return

    with st.spinner(f"กำลังบันทึก {len(st.session_state.staged_data)} รายการ..."):
        data_to_save = st.session_state.staged_data[::-1] 
        success = save_batch_to_sheet(data_to_save)
        
        if success:
            st.success("✅ บันทึกข้อมูลลง Google Sheet เรียบร้อย!")
            st.session_state.staged_data = [] 
            st.session_state.scan_error = None 
            load_data_from_sheet.clear()
            st.balloons()
            time.sleep(1)
            st.rerun()
        else:
            st.error("❌ บันทึกไม่สำเร็จ กรุณาลองใหม่")

# --- MAIN APP ---
st.title("📦 MKP Scan & Pack (Pro)")

# เรียกฟังก์ชันเล่นเสียง (ทำงานแบบ Background)
play_audio_feedback()

if not st.session_state.user_id:
    st.info("ระบุรหัสพนักงาน")
    u = st.text_input("User ID", key="login")
    if st.button("Start") and u: st.session_state.user_id = u; st.rerun()
else:
    # --- SIDEBAR: Login Info & Vehicle ---
    with st.sidebar:
        st.write(f"👤 **{st.session_state.user_id}**")
        st.markdown("---")
        
        # 🚛 ส่วน Scan ทะเบียนรถ (Global Setting)
        st.subheader("🚛 ข้อมูลรถขนส่ง")
        st.text_input("ทะเบียนรถ (Vehicle ID)", key="license_plate", help="ระบุทะเบียนรถเพื่องานรอบนี้")
        if st.session_state.license_plate:
            st.success(f"รถ: {st.session_state.license_plate}")
        else:
            st.warning("ยังไม่ระบุทะเบียนรถ")
            
        st.markdown("---")
        if st.button("Logout"): 
            st.session_state.user_id = ""
            st.session_state.staged_data = []
            st.session_state.license_plate = ""
            st.rerun()

    tab1, tab2 = st.tabs(["📷 Scan Work", "📊 Dashboard"])

    with tab1:
        if st.session_state.scan_error:
            st.markdown(f'<div class="error-box">{st.session_state.scan_error}</div>', unsafe_allow_html=True)
            if st.button("ปิดแจ้งเตือน"): 
                st.session_state.scan_error = None
                st.rerun()

        scan_mode = st.radio(
            "เลือกรูปแบบงาน:",
            ["🚀 1. สินค้าเดียว -> หลาย Tracking", "📦 2. งานปกติ (1 Tracking : 1 Barcode)"],
            horizontal=True
        )
        st.divider()

        # === SCAN INPUT AREA ===
        if "1." in scan_mode:
            st.info("💡 Mode A: สแกนสินค้าต้นแบบ 1 ครั้ง -> ยิง Tracking รัวๆ")
            
            c1, c2 = st.columns([3, 1])
            with c1:
                if not st.session_state.locked_barcode:
                    bc = st.text_input("1. สแกนสินค้าต้นแบบ", key="master_bc_input")
                    if bc: st.session_state.locked_barcode = bc; st.rerun()
                else:
                    st.success(f"🔒 สินค้า: **{st.session_state.locked_barcode}**")
            with c2:
                if st.session_state.locked_barcode:
                    if st.button("เปลี่ยนสินค้า"): st.session_state.locked_barcode = ""; st.rerun()

            if st.session_state.locked_barcode:
                st.text_input("2. ยิง Tracking ID (เพิ่มลงรายการ)", key="mkp_tracking_a", on_change=on_scan_mode_a)
                st.button("เพิ่มรายการ (Manual)", on_click=on_scan_mode_a)

        else:
            st.info("💡 Mode B: สแกนคู่ (Tracking + Barcode)")
            c1, c2 = st.columns(2)
            with c1: st.text_input("1. Tracking ID", key="mkp_tracking_b")
            with c2: st.text_input("2. Product Barcode", key="mkp_barcode_b", on_change=on_scan_mode_b)
            st.button("เพิ่มรายการ", on_click=on_scan_mode_b)

        # === STAGING TABLE AREA ===
        st.markdown("---")
        count_waiting = len(st.session_state.staged_data)
        
        col_h1, col_h2 = st.columns([3, 1])
        with col_h1:
            st.subheader(f"📋 รายการรอบันทึก ({count_waiting})")
        with col_h2:
            if count_waiting > 0:
                st.button(f"☁️ ยืนยันบันทึก ({count_waiting})", type="primary", use_container_width=True, on_click=confirm_save_all)

        if count_waiting > 0:
            with st.container(border=True):
                # ปรับ Header เพิ่มทะเบียนรถให้เห็นด้วย
                h1, h2, h3, h4, h5 = st.columns([1, 2, 3, 3, 1])
                h1.markdown("**เวลา**")
                h2.markdown("**ทะเบียนรถ**")
                h3.markdown("**Tracking**")
                h4.markdown("**Barcode**")
                h5.markdown("**ลบ**")
                st.divider()
                
                for item in st.session_state.staged_data:
                    c1, c2, c3, c4, c5 = st.columns([1, 2, 3, 3, 1])
                    c1.caption(item['time_scan'])
                    c2.caption(item['license_plate']) # แสดงทะเบียนรถ
                    c3.write(item['tracking'])
                    c4.write(item['barcode'])
                    c5.button("❌", key=f"del_{item['id']}", on_click=delete_from_staging, args=(item['id'],))
        else:
            st.caption("ยังไม่มีรายการสแกน... (สแกนเพื่อเพิ่มรายการ)")

    with tab2:
        if st.button("🔄 Refresh Data"): 
            load_data_from_sheet.clear()
            st.rerun()
            
        df = load_data_from_sheet()
        if not df.empty:
            display_cols = df.columns.tolist()
            if 'Order ID' in display_cols: 
                df.rename(columns={'Order ID': 'Tracking ID'}, inplace=True)
            elif 'Tracking' in display_cols:
                df.rename(columns={'Tracking': 'Tracking ID'}, inplace=True)
                
            st.write(f"Total Saved: {len(df)}")
            st.dataframe(df.tail(15), use_container_width=True)
