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
DATA_SHEET_NAME = 'Data_Pack'    
USER_SHEET_NAME = 'User_MKP'     

# --- CSS STYLING (ปรับแต่งใหม่สำหรับหน้าจอหลัก) ---
st.markdown("""
<style>
div.block-container { padding-top: 2rem; padding-bottom: 2rem; }
h1 { font-size: 1.8rem !important; margin-bottom: 0.5rem; }
.big-font { font-size: 20px !important; font-weight: bold; }
/* กล่อง User Info ด้านบน */
.user-header {
    background-color: #f0f2f6;
    padding: 15px;
    border-radius: 10px;
    margin-bottom: 20px;
    border: 1px solid #dce4ef;
}
/* กล่องทะเบียนรถ */
.vehicle-box {
    background-color: #e8f5e9; 
    padding: 15px;
    border-radius: 10px;
    border: 1px solid #c8e6c9;
    margin-bottom: 20px;
}
/* กล่อง Error */
.error-box {
    padding: 1rem;
    background-color: #ffcccc;
    color: #cc0000;
    border-radius: 8px;
    border: 1px solid #cc0000;
    margin-bottom: 1rem;
    font-weight: bold;
    text-align: center;
}
</style>
""", unsafe_allow_html=True)

# --- GOOGLE SHEETS & AUTH ---
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

# --- HELPER FUNCTIONS ---
def verify_user_login(user_id):
    """เช็ค User และดึงชื่อ (Logic เดิม)"""
    try:
        ws = get_sheet_connection(USER_SHEET_NAME)
        if ws:
            all_records = ws.get_all_values()
            if not all_records: return False, None
            
            headers = all_records[0]
            target_id = str(user_id).strip()
            
            # หา Column Name
            name_col_idx = -1
            for i, h in enumerate(headers):
                if "name" in str(h).lower() or "ชื่อ" in str(h).lower():
                    name_col_idx = i; break
            if name_col_idx == -1: name_col_idx = 2 # Default C

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

# --- STATE MANAGEMENT ---
if 'user_id' not in st.session_state: st.session_state.user_id = ""
if 'user_name' not in st.session_state: st.session_state.user_name = ""
if 'staged_data' not in st.session_state: st.session_state.staged_data = []
if 'locked_barcode' not in st.session_state: st.session_state.locked_barcode = ""
if 'scan_error' not in st.session_state: st.session_state.scan_error = None
if 'play_sound' not in st.session_state: st.session_state.play_sound = None

# [สำคัญ] ตัวแปรสำหรับ Reset Input (ใช้แก้ Error)
if 'reset_key_lp' not in st.session_state: st.session_state.reset_key_lp = 0
if 'reset_key_scan' not in st.session_state: st.session_state.reset_key_scan = 0

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
        # หา Column
        cols = df.columns
        t_col = next((c for c in cols if c in ['Tracking ID', 'Order ID', 'Tracking']), None)
        if t_col:
            if str(tracking).strip() in df[t_col].astype(str).str.strip().values:
                return True, f"⛔ เคยบันทึกไปแล้ว! ({tracking})"
    return False, ""

def add_to_staging(tracking, barcode, mode, license_plate):
    st.session_state.scan_error = None
    if not tracking or not barcode: return

    # Check Dup
    is_dup, msg = check_duplicate(tracking)
    if is_dup:
        st.session_state.scan_error = msg
        st.session_state.play_sound = 'error'
        st.toast(msg, icon="🚫")
        return

    # Check LP
    if not license_plate:
        st.toast("⚠️ กรุณาระบุทะเบียนรถก่อนบันทึก", icon="🚛")
        # ไม่ Block แต่เตือน

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

# --- ACTION FUNCTIONS ---
def action_logout():
    st.session_state.user_id = ""
    st.session_state.user_name = ""
    st.session_state.staged_data = []
    st.session_state.locked_barcode = ""
    st.session_state.reset_key_lp = 0 # Reset ตัวนับ
    load_data_from_sheet.clear()
    # ไม่ต้อง st.rerun() ที่นี่ เดี๋ยวปุ่มมันจัดการเอง

def action_confirm_save():
    if not st.session_state.staged_data: return
    
    with st.spinner("Saving..."):
        # Save
        if save_batch_to_sheet(st.session_state.staged_data[::-1]):
            st.success("✅ บันทึกสำเร็จ")
            st.session_state.staged_data = []
            st.session_state.scan_error = None
            st.session_state.locked_barcode = ""
            
            # [แก้ Error] เพิ่มค่า Reset Key เพื่อล้างช่อง Input อัตโนมัติในรอบหน้า
            st.session_state.reset_key_lp += 1
            st.session_state.reset_key_scan += 1
            
            load_data_from_sheet.clear()
            st.balloons()
            time.sleep(1)
            st.rerun()
        else:
            st.error("Save Failed")

# ================= MAIN APP =================
st.title("📦 MKP Scan & Pack (Pro)")
play_audio_feedback()

# --- 1. หน้า Login ---
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
                    st.error("ไม่พบรหัสพนักงาน")
else:
    # --- 2. หน้าหลัก (Logged In) ---
    
    # Header: User Info & Logout (ใช้ Columns แทน Sidebar)
    # ใส่ใน Container สีเทาอ่อนให้ดูเป็น Header
    with st.container():
        st.markdown(f"""
        <div class="user-header">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <span style="font-size:1.2rem; font-weight:bold;">👤 {st.session_state.user_name}</span><br>
                    <span style="color:gray; font-size:0.9rem;">ID: {st.session_state.user_id}</span>
                </div>
                </div>
        </div>
        """, unsafe_allow_html=True)
        
        # ปุ่ม Logout วางขวาบน
        col_h1, col_h2 = st.columns([3, 1])
        with col_h2:
            st.button("🚪 Logout", on_click=action_logout, use_container_width=True)

    # Tabs
    t1, t2 = st.tabs(["📝 Scan Work", "📊 History"])

    with t1:
        # === A. Vehicle Input (วางบนสุดตามขอ) ===
        st.markdown('<div class="vehicle-box">', unsafe_allow_html=True)
        c_v1, c_v2 = st.columns([1, 4])
        with c_v1:
            st.markdown("### 🚛")
        with c_v2:
            # ใช้ Dynamic Key (lp_{reset_key}) ทำให้ล้างค่าได้โดยไม่ Error 100%
            lp_key = f"lp_{st.session_state.reset_key_lp}"
            current_lp = st.text_input("ทะเบียนรถ (Vehicle ID)", 
                                     placeholder="ระบุทะเบียนรถ...", 
                                     key=lp_key)
        st.markdown('</div>', unsafe_allow_html=True)

        # Error Show
        if st.session_state.scan_error:
            st.markdown(f'<div class="error-box">{st.session_state.scan_error}</div>', unsafe_allow_html=True)
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
                # Master Barcode
                mbc_key = f"mbc_{st.session_state.reset_key_scan}" # Reset ได้เมื่อจบงาน
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
                # Tracking Input (Auto Clear Logic by key change logic handled manually or via rerun)
                # เพื่อความง่าย ใช้ key เดิมแต่ submit แล้ว clear manual ไม่ได้เพราะ error
                # ใช้เทคนิค: form_submit หรือ session_state callback
                
                # Callback สำหรับ Mode A
                def submit_mode_a():
                    # ดึงค่าจาก widget โดยใช้ key ปัจจุบัน
                    val = st.session_state[f"trk_a_{st.session_state.reset_key_scan}"]
                    if val:
                        add_to_staging(val, st.session_state.locked_barcode, "Mode A", current_lp)
                        # "Hack" เล็กๆ: เพิ่ม reset_key_scan เฉพาะเลขย่อยเพื่อล้างช่องนี้ช่องเดียว? 
                        # ไม่ได้ เดี๋ยว master barcode หาย
                        # ดังนั้นใน Streamlit 1.30+ วิธีที่ดีคือ st.session_state[key] = "" ทำไม่ได้
                        # งั้นใช้ st.session_state.trk_a_temp เพื่อเก็บค่า แล้ว rerun
                        pass
                
                # ใช้ form เพื่อให้กด Enter แล้วส่งค่า แล้วค่อยเคลียร์
                with st.form("form_a", clear_on_submit=True):
                    val_a = st.text_input("2. ยิง Tracking ID", key="input_a")
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
                st.button(f"☁️ ยืนยันบันทึก ({cnt})", type="primary", use_container_width=True, on_click=action_confirm_save)

        if cnt > 0:
            with st.container(border=True):
                # Header
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
