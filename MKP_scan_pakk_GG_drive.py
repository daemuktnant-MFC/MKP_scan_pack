import streamlit as st
import pandas as pd
import gspread
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from datetime import datetime
import time
import pytz
import uuid

# --- PAGE CONFIG ---
st.set_page_config(page_title="MKP Scan & Pack", page_icon="📦", layout="wide")

# --- CONFIGURATION ---
SHEET_ID = '1Om9qwShA3hBQgKJPQNbJgDPInm9AQ2hY5Z8OuOpkF08'
DATA_SHEET_NAME = 'Data_Pack'    
USER_SHEET_NAME = 'User_MKP'     

# --- CSS STYLING ---
st.markdown("""
<style>
div.block-container { padding-top: 1rem; padding-bottom: 2rem; }
.user-header {
    background-color: #f0f2f6;
    padding: 15px;
    border-radius: 10px;
    margin-bottom: 20px;
    border: 1px solid #dce4ef;
}
.vehicle-box {
    background-color: #e8f5e9; 
    padding: 15px;
    border-radius: 10px;
    border: 1px solid #c8e6c9;
    margin-bottom: 10px;
}
.big-font { font-size: 20px !important; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- GOOGLE SERVICES ---
def get_credentials():
    try:
        if "oauth" in st.secrets:
            info = st.secrets["oauth"]
            return Credentials(None, refresh_token=info["refresh_token"], token_uri="https://oauth2.googleapis.com/token", client_id=info["client_id"], client_secret=info["client_secret"])
    except: return None

def get_sheet_connection(sheet_name):
    creds = get_credentials()
    if creds:
        gc = gspread.authorize(creds)
        try: return gc.open_by_key(SHEET_ID).worksheet(sheet_name)
        except: return None
    return None

# --- CORE FUNCTIONS ---
def verify_user_login(user_id):
    try:
        ws = get_sheet_connection(USER_SHEET_NAME)
        if ws:
            all_records = ws.get_all_values()
            if not all_records: return False, None
            headers = all_records[0]
            target_id = str(user_id).strip()
            
            name_col_idx = 2 # Default C
            for i, h in enumerate(headers):
                if "name" in str(h).lower() or "ชื่อ" in str(h).lower():
                    name_col_idx = i; break

            for row in all_records:
                while len(row) <= max(1, name_col_idx): row.append("")
                if str(row[1]).strip() == target_id:
                    u_name = str(row[name_col_idx]).strip()
                    return True, u_name if u_name else "พนักงาน"
            return False, None
    except: return False, None
    return False, None

def save_batch_to_sheet(data_list):
    try:
        ws = get_sheet_connection(DATA_SHEET_NAME)
        if ws:
            rows = []
            tz = pytz.timezone('Asia/Bangkok')
            ts = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
            for item in data_list:
                rows.append([ts, item['user_id'], item['user_name'], item['tracking'], item['barcode'], "Normal", 1, item['mode'], item['license_plate']])
            ws.append_rows(rows)
            return True
    except: return False
    return False

@st.cache_data(ttl=30)
def load_data_from_sheet():
    try:
        ws = get_sheet_connection(DATA_SHEET_NAME)
        if ws:
            data = ws.get_all_values()
            if len(data) > 1:
                df = pd.DataFrame(data[1:], columns=data[0])
                df.columns = df.columns.str.strip()
                return df
    except: pass
    return pd.DataFrame()

# --- INIT SESSION STATE (LOGIC จาก CODE ตัวอย่าง) ---
def init_session_state():
    keys = {
        'user_id': "",
        'user_name': "",
        'staged_data': [],
        'locked_barcode': "",
        'scan_error': None,
        'play_sound': None,
        'reset_key': 0  # ตัวแปรสำคัญสำหรับแก้ Error Reset Widget
    }
    for k, v in keys.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session_state()

# --- SOUND ---
def play_audio_feedback():
    if st.session_state.play_sound == 'success':
        st.audio("https://www.soundjay.com/buttons/sounds/button-16.mp3", format="audio/mp3", autoplay=True)
    elif st.session_state.play_sound == 'error':
        st.audio("https://www.soundjay.com/buttons/sounds/button-10.mp3", format="audio/mp3", autoplay=True)
    st.session_state.play_sound = None

# --- LOGIC ---
def check_duplicate(tracking):
    for item in st.session_state.staged_data:
        if str(item['tracking']).strip() == str(tracking).strip():
            return True, f"⚠️ ซ้ำในรายการรอ! ({tracking})"
    df = load_data_from_sheet()
    if not df.empty:
        cols = df.columns
        t_col = next((c for c in cols if c in ['Tracking ID', 'Order ID', 'Tracking']), None)
        if t_col:
            if str(tracking).strip() in df[t_col].astype(str).str.strip().values:
                return True, f"⛔ เคยบันทึกไปแล้ว! ({tracking})"
    return False, ""

def add_to_staging(tracking, barcode, mode, license_plate):
    st.session_state.scan_error = None
    if not tracking or not barcode: return

    is_dup, msg = check_duplicate(tracking)
    if is_dup:
        st.session_state.scan_error = msg
        st.session_state.play_sound = 'error'
        st.toast(msg, icon="🚫")
        return

    if not license_plate:
        st.toast("⚠️ กรุณาระบุทะเบียนรถ", icon="🚛")

    new_item = {
        "id": str(uuid.uuid4()),
        "user_id": st.session_state.user_id,
        "user_name": st.session_state.user_name,
        "license_plate": license_plate,
        "tracking": tracking,
        "barcode": barcode,
        "mode": mode,
        "time_scan": datetime.now().strftime("%H:%M:%S")
    }
    st.session_state.staged_data.insert(0, new_item)
    st.session_state.play_sound = 'success'
    st.toast(f"📥 เพิ่ม: {tracking}", icon="➕")

def delete_staging(item_id):
    st.session_state.staged_data = [d for d in st.session_state.staged_data if d['id'] != item_id]

# --- CALLBACK FUNCTIONS (ปลอดภัยกว่าเขียนในปุ่มโดยตรง) ---
def logout_callback():
    """ฟังก์ชัน Logout ที่ปลอดภัย 100%"""
    st.session_state.user_id = ""
    st.session_state.user_name = ""
    st.session_state.staged_data = []
    st.session_state.locked_barcode = ""
    # การเพิ่มค่า reset_key จะทำให้ widget ถูกสร้างใหม่เป็นค่าว่างเอง (ไม่ต้องสั่ง = "")
    st.session_state.reset_key += 1 
    load_data_from_sheet.clear()

def save_callback():
    """ฟังก์ชัน Save"""
    if not st.session_state.staged_data: return
    
    with st.spinner("Saving..."):
        if save_batch_to_sheet(st.session_state.staged_data[::-1]):
            st.success("✅ บันทึกสำเร็จ")
            st.session_state.staged_data = []
            st.session_state.scan_error = None
            st.session_state.locked_barcode = ""
            # เพิ่มค่า reset_key เพื่อเคลียร์ช่องทะเบียนรถและอื่นๆ
            st.session_state.reset_key += 1
            load_data_from_sheet.clear()
            st.balloons()
            time.sleep(1)
        else:
            st.error("Save Failed")

# ================= MAIN APP =================
st.title("📦 MKP Scan & Pack (Pro)")
play_audio_feedback()

# --- 1. LOGIN SCREEN ---
if not st.session_state.user_id:
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        st.info("🔒 กรุณาสแกนรหัสพนักงาน")
        u_in = st.text_input("User ID", key="login_input")
        if st.button("เข้าสู่ระบบ (Login)", use_container_width=True):
            if u_in:
                found, name = verify_user_login(u_in)
                if found:
                    st.session_state.user_id = u_in
                    st.session_state.user_name = name
                    st.rerun()
                else:
                    st.error("❌ ไม่พบรหัสพนักงาน")
else:
    # --- 2. MAIN SCREEN (No Sidebar) ---
    
    # 2.1 Header Profile & Logout
    with st.container():
        st.markdown(f"""
        <div class="user-header">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <span style="font-size:1.1rem; font-weight:bold;">👤 {st.session_state.user_name}</span>
                    <span style="color:gray; font-size:0.9rem;"> (ID: {st.session_state.user_id})</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        # ปุ่ม Logout วางขวาบน แยกออกมาเพื่อให้กดง่าย
        col_null, col_out = st.columns([4, 1])
        with col_out:
            st.button("🚪 Logout", on_click=logout_callback, use_container_width=True)

    # 2.2 Tabs
    t1, t2 = st.tabs(["📝 Scan Work", "📊 History"])

    with t1:
        # === A. Vehicle Input (วางบนสุด) ===
        st.markdown('<div class="vehicle-box">', unsafe_allow_html=True)
        c_v1, c_v2 = st.columns([1, 4])
        with c_v1:
            st.markdown("### 🚛")
        with c_v2:
            # [KEY SOLUTION] ใช้ key ที่เปลี่ยนไปเรื่อยๆ (Dynamic Key)
            # เมื่อ reset_key เปลี่ยน Streamlit จะมองว่าเป็น Widget ใหม่ที่ยังไม่มีค่า -> เท่ากับล้างค่า
            current_lp = st.text_input("ทะเบียนรถ (Vehicle ID)", 
                                     placeholder="ระบุทะเบียนรถ...", 
                                     key=f"lp_{st.session_state.reset_key}")
        st.markdown('</div>', unsafe_allow_html=True)

        # Error Message
        if st.session_state.scan_error:
            st.error(st.session_state.scan_error)
            if st.button("ปิดแจ้งเตือน"): 
                st.session_state.scan_error = None
                st.rerun()

        # === B. Scan Section ===
        mode = st.radio("รูปแบบงาน:", ["🚀 สินค้าเดียว -> หลาย Tracking", "📦 งานปกติ (จับคู่)"], horizontal=True)
        st.divider()

        if "สินค้าเดียว" in mode:
            # Mode A
            c1, c2 = st.columns([3, 1])
            with c1:
                # ใช้ Dynamic Key กับ Master Barcode ด้วย
                mbc_key = f"mbc_{st.session_state.reset_key}" 
                if not st.session_state.locked_barcode:
                    mbc = st.text_input("1. สแกนสินค้าต้นแบบ", key=mbc_key)
                    if mbc: 
                        st.session_state.locked_barcode = mbc
                        st.rerun()
                else:
                    st.success(f"🔒 สินค้า: **{st.session_state.locked_barcode}**")
            with c2:
                if st.session_state.locked_barcode:
                    if st.button("เปลี่ยน"): 
                        st.session_state.locked_barcode = ""
                        st.rerun()
            
            if st.session_state.locked_barcode:
                # Form สำหรับ Tracking ID
                with st.form("form_a", clear_on_submit=True):
                    val_a = st.text_input("2. ยิง Tracking ID")
                    submitted_a = st.form_submit_button("เพิ่มรายการ")
                    if submitted_a and val_a:
                        add_to_staging(val_a, st.session_state.locked_barcode, "Mode A", current_lp)
                        st.rerun()

        else:
            # Mode B (Pair)
            with st.form("form_b", clear_on_submit=True):
                c1, c2 = st.columns(2)
                with c1: t_b = st.text_input("1. Tracking ID")
                with c2: b_b = st.text_input("2. Product Barcode")
                submitted_b = st.form_submit_button("เพิ่มรายการ")
                
                if submitted_b:
                    if t_b and b_b:
                        add_to_staging(t_b, b_b, "Mode B", current_lp)
                        st.rerun()
                    else:
                        st.warning("กรุณาสแกนให้ครบทั้ง 2 ช่อง")

        # === C. Staging Table ===
        st.markdown("---")
        cnt = len(st.session_state.staged_data)
        
        c_h1, c_h2 = st.columns([3, 1])
        with c_h1: st.subheader(f"📋 รายการรอบันทึก ({cnt})")
        with c_h2:
            if cnt > 0:
                # ปุ่ม Save ใช้ Callback
                st.button(f"☁️ ยืนยันบันทึก ({cnt})", type="primary", use_container_width=True, on_click=save_callback)

        if cnt > 0:
            with st.container(border=True):
                cols = st.columns([1, 2, 3, 3, 1])
                headers = ["เวลา", "ทะเบียน", "Tracking", "Barcode", "ลบ"]
                for col, h in zip(cols, headers): col.markdown(f"**{h}**")
                st.divider()
                
                for item in st.session_state.staged_data:
                    c1, c2, c3, c4, c5 = st.columns([1, 2, 3, 3, 1])
                    c1.caption(item['time_scan'])
                    c2.caption(item['license_plate'])
                    c3.write(item['tracking'])
                    c4.write(item['barcode'])
                    c5.button("❌", key=f"d_{item['id']}", on_click=delete_staging, args=(item['id'],))

    with t2: # History Tab
        if st.button("🔄 Refresh"): 
            load_data_from_sheet.clear()
            st.rerun()
        df = load_data_from_sheet()
        if not df.empty:
            st.dataframe(df.tail(15), use_container_width=True)
