import streamlit as st
import pandas as pd
import gspread
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from datetime import datetime
import time
import pytz
import uuid
from PIL import Image
import io

# --- IMPORT LIBRARY กล้อง ---
try:
    from streamlit_back_camera_input import back_camera_input
    from pyzbar.pyzbar import decode
except ImportError:
    st.error("⚠️ กรุณาติดตั้ง library: streamlit-back-camera-input, pyzbar, Pillow")
    st.stop()

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

/* CSS Hack สำหรับกล้อง */
iframe[title="streamlit_back_camera_input.back_camera_input"] {
    min-height: 250px !important; 
    height: 100% !important;
}
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

# --- INIT SESSION STATE ---
def init_session_state():
    keys = {
        'user_id': "",
        'user_name': "",
        'staged_data': [],
        'locked_barcode': "",
        'scan_error': None,
        'play_sound': None,
        'reset_key': 0,
        'cam_counter': 0, # ตัวนับสำหรับรีเซ็ตกล้อง
        # Temp values for inputs
        'temp_tracking_b': "",
        'temp_barcode_b': ""
    }
    for k, v in keys.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session_state()

# --- HELPER: DECODE IMAGE ---
def process_camera_scan(image_input):
    """ฟังก์ชันช่วยแปลงภาพเป็น Text"""
    if image_input:
        try:
            img = Image.open(image_input)
            decoded_objects = decode(img)
            if decoded_objects:
                # คืนค่า Text ที่อ่านได้
                return decoded_objects[0].data.decode("utf-8")
        except Exception as e:
            st.error(f"Error decoding: {e}")
    return None

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

def logout_callback():
    st.session_state.user_id = ""
    st.session_state.user_name = ""
    st.session_state.staged_data = []
    st.session_state.locked_barcode = ""
    st.session_state.reset_key += 1 
    st.session_state.cam_counter += 1
    st.session_state.temp_tracking_b = ""
    st.session_state.temp_barcode_b = ""
    load_data_from_sheet.clear()

def save_callback():
    if not st.session_state.staged_data: return
    with st.spinner("Saving..."):
        if save_batch_to_sheet(st.session_state.staged_data[::-1]):
            st.success("✅ บันทึกสำเร็จ")
            st.session_state.staged_data = []
            st.session_state.scan_error = None
            st.session_state.locked_barcode = ""
            st.session_state.reset_key += 1
            st.session_state.cam_counter += 1
            load_data_from_sheet.clear()
            st.balloons()
            time.sleep(1)
        else:
            st.error("Save Failed")

# ================= MAIN APP =================
st.title("📦 MKP Scan & Pack (Pro + Camera)")
play_audio_feedback()

# --- 1. LOGIN SCREEN ---
if not st.session_state.user_id:
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        st.info("🔒 กรุณาสแกนรหัสพนักงาน")
        
        # Manual Input
        u_in = st.text_input("User ID (พิมพ์)", key="login_input")
        
        # Camera Input
        cam_key = f"cam_login_{st.session_state.cam_counter}"
        login_img = back_camera_input("แตะเพื่อเปิดกล้องสแกน", key=cam_key)
        
        # Logic Check
        final_user_id = None
        if u_in: 
            final_user_id = u_in
        elif login_img:
            # ถ้ามีภาพจากกล้อง ให้ถอดรหัส
            scanned_text = process_camera_scan(login_img)
            if scanned_text:
                final_user_id = scanned_text
        
        if st.button("เข้าสู่ระบบ (Login)", use_container_width=True) or (final_user_id and not u_in):
            # ถ้ามี ID จากช่องพิมพ์ หรือ จากกล้อง ให้ Login เลย
            if final_user_id:
                found, name = verify_user_login(final_user_id)
                if found:
                    st.session_state.user_id = final_user_id
                    st.session_state.user_name = name
                    st.session_state.cam_counter += 1 # Reset กล้อง
                    st.rerun()
                else:
                    st.error("❌ ไม่พบรหัสพนักงาน")
            else:
                st.warning("กรุณาระบุรหัสพนักงาน")
else:
    # --- 2. MAIN SCREEN ---
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
        col_null, col_out = st.columns([4, 1])
        with col_out:
            st.button("🚪 Logout", on_click=logout_callback, use_container_width=True)

    t1, t2 = st.tabs(["📝 Scan Work", "📊 History"])

    with t1:
        # === A. Vehicle Input ===
        st.markdown('<div class="vehicle-box">', unsafe_allow_html=True)
        c_v1, c_v2 = st.columns([1, 4])
        with c_v1: st.markdown("### 🚛")
        with c_v2:
            current_lp = st.text_input("ทะเบียนรถ (Vehicle ID)", 
                                     placeholder="ระบุทะเบียนรถ...", 
                                     key=f"lp_{st.session_state.reset_key}")
        st.markdown('</div>', unsafe_allow_html=True)

        if st.session_state.scan_error:
            st.error(st.session_state.scan_error)
            if st.button("ปิดแจ้งเตือน"): 
                st.session_state.scan_error = None; st.rerun()

        # === B. Scan Section ===
        mode = st.radio("รูปแบบงาน:", ["🚀 สินค้าเดียว -> หลาย Tracking", "📦 งานปกติ (จับคู่)"], horizontal=True)
        st.divider()

        if "สินค้าเดียว" in mode:
            # === MODE A: Master Product -> Multi Tracking ===
            c1, c2 = st.columns([3, 1])
            with c1:
                mbc_key_txt = f"mbc_txt_{st.session_state.reset_key}" 
                
                # Check locked
                if not st.session_state.locked_barcode:
                    # 1. Input Box
                    mbc = st.text_input("1. สแกนสินค้าต้นแบบ", key=mbc_key_txt)
                    
                    # 2. Camera Input
                    with st.expander("📷 เปิดกล้อง (สแกนสินค้า)"):
                         cam_key_A1 = f"cam_A1_{st.session_state.cam_counter}"
                         img_A1 = back_camera_input(key=cam_key_A1)
                    
                    # Logic
                    scanned_val = None
                    if mbc: scanned_val = mbc
                    elif img_A1: scanned_val = process_camera_scan(img_A1)

                    if scanned_val: 
                        st.session_state.locked_barcode = scanned_val
                        st.session_state.cam_counter += 1
                        st.rerun()
                else:
                    st.success(f"🔒 สินค้า: **{st.session_state.locked_barcode}**")
            with c2:
                if st.session_state.locked_barcode:
                    if st.button("เปลี่ยน"): 
                        st.session_state.locked_barcode = ""; st.rerun()
            
            if st.session_state.locked_barcode:
                # 3. Tracking Scanning Loop
                col_trk_inp, col_trk_cam = st.columns([3, 1])
                
                scan_val_A2 = None
                with col_trk_inp:
                    # Manual Input (Form)
                    with st.form("form_a", clear_on_submit=True):
                        val_a = st.text_input("2. ยิง Tracking ID")
                        submitted_a = st.form_submit_button("เพิ่มรายการ")
                        if submitted_a and val_a:
                            scan_val_A2 = val_a

                # Camera Input (Outside Form for instant scan)
                with col_trk_cam:
                     with st.popover("📷"): # ใช้ Popover เพื่อประหยัดพื้นที่
                        st.write("สแกน Tracking")
                        cam_key_A2 = f"cam_A2_{st.session_state.cam_counter}"
                        img_A2 = back_camera_input(key=cam_key_A2)
                        if img_A2:
                            scan_val_A2 = process_camera_scan(img_A2)

                # Process Result
                if scan_val_A2:
                    add_to_staging(scan_val_A2, st.session_state.locked_barcode, "Mode A", current_lp)
                    st.session_state.cam_counter += 1
                    st.rerun()

        else:
            # === MODE B: Tracking <-> Barcode ===
            
            # --- 1. Tracking Input ---
            st.markdown("**1. Tracking ID**")
            c_t1, c_t2 = st.columns([3, 1])
            with c_t1:
                # Show value if exists in temp
                def update_track(): st.session_state.temp_tracking_b = st.session_state.track_b_manual
                st.text_input("Scan/Key Tracking", key="track_b_manual", value=st.session_state.temp_tracking_b, on_change=update_track)
            with c_t2:
                with st.popover("📷 Track"):
                    cam_key_B1 = f"cam_B1_{st.session_state.cam_counter}"
                    img_B1 = back_camera_input(key=cam_key_B1)
                    if img_B1:
                         res = process_camera_scan(img_B1)
                         if res: 
                             st.session_state.temp_tracking_b = res
                             st.session_state.cam_counter += 1
                             st.rerun()

            # --- 2. Barcode Input ---
            st.markdown("**2. Product Barcode**")
            c_p1, c_p2 = st.columns([3, 1])
            with c_p1:
                 def update_prod(): st.session_state.temp_barcode_b = st.session_state.prod_b_manual
                 st.text_input("Scan/Key Barcode", key="prod_b_manual", value=st.session_state.temp_barcode_b, on_change=update_prod)
            with c_p2:
                with st.popover("📷 Prod"):
                    cam_key_B2 = f"cam_B2_{st.session_state.cam_counter}"
                    img_B2 = back_camera_input(key=cam_key_B2)
                    if img_B2:
                         res = process_camera_scan(img_B2)
                         if res: 
                             st.session_state.temp_barcode_b = res
                             st.session_state.cam_counter += 1
                             st.rerun()

            # --- Confirm Button ---
            if st.button("➕ เพิ่มรายการ (Mode B)", use_container_width=True, type="primary"):
                if st.session_state.temp_tracking_b and st.session_state.temp_barcode_b:
                    add_to_staging(st.session_state.temp_tracking_b, st.session_state.temp_barcode_b, "Mode B", current_lp)
                    # Clear Temps
                    st.session_state.temp_tracking_b = ""
                    st.session_state.temp_barcode_b = ""
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

    with t2:
        if st.button("🔄 Refresh"): 
            load_data_from_sheet.clear()
            st.rerun()
        df = load_data_from_sheet()
        if not df.empty:
            st.dataframe(df.tail(15), use_container_width=True)
