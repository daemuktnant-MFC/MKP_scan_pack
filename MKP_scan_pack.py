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
DATA_SHEET_NAME = 'Data_Pack'    # Tab เก็บข้อมูลงาน
USER_SHEET_NAME = 'User_MKP'     # Tab เก็บรายชื่อพนักงาน

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
/* ไฮไลท์ทะเบียนรถ */
.license-plate-box {
    padding: 10px;
    background-color: #e3f2fd;
    border-left: 5px solid #2196f3;
    border-radius: 5px;
    margin-bottom: 15px;
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

# --- GOOGLE SHEETS CONNECTION ---
def get_sheet_connection(sheet_name):
    creds = get_credentials()
    if creds:
        gc = gspread.authorize(creds)
        try: return gc.open_by_key(SHEET_ID).worksheet(sheet_name)
        except: return None
    return None

def verify_user_login(user_id):
    """
    ตรวจสอบ User ID (Col B) และดึง User Name (โดยหาจาก Header 'Name' หรือ Col C)
    Return: (bool_found, str_user_name)
    """
    try:
        ws = get_sheet_connection(USER_SHEET_NAME)
        if ws:
            all_records = ws.get_all_values()
            
            if not all_records:
                st.error("❌ ไม่พบข้อมูลใน Sheet User_MKP")
                return False, None

            headers = all_records[0] 
            target_id = str(user_id).strip()

            # หา Index ของคอลัมน์ "Name" หรือ "ชื่อ"
            name_col_idx = -1
            for i, h in enumerate(headers):
                h_str = str(h).lower()
                if "name" in h_str or "ชื่อ" in h_str:
                    name_col_idx = i
                    break
            
            # ถ้าหาไม่เจอ ให้ใช้ Index 2 (Column C)
            if name_col_idx == -1: name_col_idx = 2 

            # วนลูปหา User ID ใน Column B (Index 1)
            for row in all_records:
                while len(row) <= max(1, name_col_idx): row.append("")
                current_id = str(row[1]).strip()
                if current_id == target_id:
                    user_name = str(row[name_col_idx]).strip()
                    if not user_name: user_name = "ไม่ระบุชื่อ"
                    return True, user_name
            return False, None
        else:
            st.error(f"❌ ไม่พบ Tab ชื่อ '{USER_SHEET_NAME}'")
            return False, None
    except Exception as e:
        st.error(f"Error checking user: {e}")
        return False, None

def save_batch_to_sheet(data_list):
    try:
        ws = get_sheet_connection(DATA_SHEET_NAME)
        if ws:
            rows_to_add = []
            tz = pytz.timezone('Asia/Bangkok')
            ts = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
            for item in data_list:
                row = [
                    ts, 
                    item['user_id'], 
                    item['user_name'], 
                    item['tracking'], 
                    item['barcode'], 
                    "Normal", 
                    1, 
                    item['mode'], 
                    item['license_plate']
                ]
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
        ws = get_sheet_connection(DATA_SHEET_NAME)
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
if 'user_name' not in st.session_state: st.session_state.user_name = "" 
if 'staged_data' not in st.session_state: st.session_state.staged_data = [] 
if 'locked_barcode' not in st.session_state: st.session_state.locked_barcode = ""
if 'scan_error' not in st.session_state: st.session_state.scan_error = None 
if 'play_sound' not in st.session_state: st.session_state.play_sound = None 

# [NEW] ตัวแปรสำหรับ Reset Input (วิธีแก้ Error 100%)
if 'form_reset_key' not in st.session_state: st.session_state.form_reset_key = 0

# --- SOUND SYSTEM ---
def play_audio_feedback():
    if st.session_state.play_sound == 'success':
        st.audio("https://www.soundjay.com/buttons/sounds/button-16.mp3", format="audio/mp3", autoplay=True)
    elif st.session_state.play_sound == 'error':
        st.audio("https://www.soundjay.com/buttons/sounds/button-10.mp3", format="audio/mp3", autoplay=True)
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

    # ดึงค่าทะเบียนรถจาก Key ปัจจุบัน
    current_lp_key = f"license_{st.session_state.form_reset_key}"
    current_lp = st.session_state.get(current_lp_key, "")

    is_dup, msg = check_duplicate(tracking)
    
    if is_dup:
        st.session_state.scan_error = msg 
        st.session_state.play_sound = 'error' 
        st.toast(msg, icon="🚫") 
        return 
    
    if not current_lp:
        st.toast("⚠️ ยังไม่ระบุทะเบียนรถ!", icon="🚛")

    new_item = {
        "id": str(uuid.uuid4()), 
        "user_id": st.session_state.user_id,
        "user_name": st.session_state.user_name, 
        "license_plate": current_lp,  # ใช้ค่าที่ดึงมา
        "tracking": tracking,
        "barcode": barcode,
        "mode": mode,
        "time_scan": datetime.now().strftime("%H:%M:%S")
    }
    st.session_state.staged_data.insert(0, new_item)
    st.session_state.play_sound = 'success' 
    st.toast(f"📥 เพิ่มรายการ: {tracking}", icon="➕")

def delete_from_staging(item_id):
    st.session_state.staged_data = [d for d in st.session_state.staged_data if d['id'] != item_id]
    st.toast("ลบรายการแล้ว", icon="🗑️")

def on_scan_mode_a():
    # ดึง Key ปัจจุบัน
    tracking_key = f"mkp_tracking_a_{st.session_state.form_reset_key}"
    tracking = st.session_state.get(tracking_key, "").strip()
    barcode = st.session_state.get('locked_barcode', '').strip()
    
    if tracking and barcode:
        add_to_staging(tracking, barcode, "Mode A")
        # ไม่ต้อง Clear tracking ที่นี่ เพราะเราใช้ dynamic key ในการเคลียร์ทีหลัง 
        # (หรือถ้าจะเคลียร์เฉพาะช่องนี้ ก็ทำได้ แต่ Code เดิมใช้วิธีเปลี่ยน key จะง่ายกว่าตอน Reset ใหญ่)
        # แต่เพื่อ UX ที่ดีใน Mode A (ยิงรัว) เราอาจจะอยากเคลียร์แค่ช่อง Tracking
        # งั้นใช้เทคนิคพิเศษ: Clear เฉพาะช่องนี้
        # st.session_state[tracking_key] = "" # วิธีนี้เสี่ยง Error
        # ดังนั้นใน Mode A เรายอมให้ Error หายโดยใช้ form_reset_key ไม่ได้ถ้าเรายิงรัว
        # *แก้ปัญหา:* ใช้ Widget Callback Clear
        pass 

# เนื่องจาก Mode A ต้องยิงรัว เราจะใช้วิธี Clear Manual สำหรับ Mode A
# ส่วน License Plate จะ Clear เมื่อกด Save All เท่านั้น

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
            st.session_state.locked_barcode = "" 
            
            # [KEY FIX] เปลี่ยน Key เพื่อล้างค่า Input ทะเบียนรถและอื่นๆ ทันที
            st.session_state.form_reset_key += 1 
            
            load_data_from_sheet.clear()
            st.balloons()
            time.sleep(1)
            st.rerun()
        else:
            st.error("❌ บันทึกไม่สำเร็จ กรุณาลองใหม่")

def logout_user():
    st.session_state.user_id = ""
    st.session_state.user_name = ""
    st.session_state.staged_data = []
    st.session_state.locked_barcode = ""
    st.session_state.scan_error = None
    st.session_state.form_reset_key = 0 # Reset key
    load_data_from_sheet.clear()

# --- MAIN APP ---
st.title("📦 MKP Scan & Pack (Pro)")
play_audio_feedback()

# --- LOGIN SECTION ---
if not st.session_state.user_id:
    st.info("🔒 กรุณาสแกนรหัสพนักงาน")
    u_input = st.text_input("User ID", key="login")
    
    if st.button("Start / Login"):
        if u_input:
            with st.spinner("🔍 กำลังตรวจสอบสิทธิ์..."):
                found, name = verify_user_login(u_input)
                if found:
                    st.session_state.user_id = u_input
                    st.session_state.user_name = name 
                    st.toast(f"สวัสดีคุณ {name}", icon="✅")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error(f"❌ ไม่พบรหัส: '{u_input}' ในระบบ")
                    st.warning("ตรวจสอบ Sheet: User_MKP")
        else:
            st.warning("กรุณากรอกรหัสพนักงาน")

else:
    if not st.session_state.user_name:
         st.warning("⚠️ ข้อมูลชื่อยังไม่โหลด กรุณา Logout แล้ว Login ใหม่")

    # --- SIDEBAR ---
    with st.sidebar:
        st.subheader("ข้อมูลพนักงาน")
        st.info(f"👤 **{st.session_state.user_name}**")
        st.caption(f"ID: {st.session_state.user_id}")
        st.markdown("---")
        st.button("Logout", use_container_width=True, on_click=logout_user)

    # --- MAIN CONTENT ---
    tab1, tab2 = st.tabs(["📷 Scan Work", "📊 Dashboard"])

    with tab1:
        # === 🚛 Vehicle Input (Dynamic Key) ===
        st.markdown('<div class="license-plate-box">', unsafe_allow_html=True)
        col_lp1, col_lp2 = st.columns([1, 3])
        with col_lp1:
            st.markdown("### 🚛")
        with col_lp2:
            # ใช้ Key ที่เปลี่ยนไปเรื่อยๆ เพื่อ Reset ค่า
            lp_key = f"license_{st.session_state.form_reset_key}"
            st.text_input("ระบุทะเบียนรถ (Vehicle ID)", key=lp_key, 
                          placeholder="เช่น 1กข-1234 (กรอกครั้งเดียวใช้จนกว่าจะกดบันทึก)",
                          help="ทะเบียนรถจะถูกล้างค่าหลังจากกดบันทึกงาน")
        st.markdown('</div>', unsafe_allow_html=True)

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
                # Master Barcode ใช้ key แยก เพราะอาจจะไม่ต้อง reset บ่อย หรือ reset พร้อมกันก็ได้
                # ถ้าอยากให้ reset พร้อมกัน ใช้ form_reset_key ได้
                bc_key = f"master_bc_{st.session_state.form_reset_key}"
                if not st.session_state.locked_barcode:
                    # ถ้ายังไม่มีค่า ให้แสดง Input
                    def on_master_bc_change():
                         # Callback เพื่อเก็บค่า
                         val = st.session_state[bc_key]
                         if val: st.session_state.locked_barcode = val
                    
                    st.text_input("1. สแกนสินค้าต้นแบบ", key=bc_key, on_change=on_master_bc_change)
                else:
                    st.success(f"🔒 สินค้า: **{st.session_state.locked_barcode}**")
            with c2:
                if st.session_state.locked_barcode:
                    if st.button("เปลี่ยนสินค้า"): st.session_state.locked_barcode = ""; st.rerun()

            if st.session_state.locked_barcode:
                # Tracking input ต้อง Clear ตัวเองเมื่อยิงเสร็จ (Auto-clear)
                # เราใช้ st.session_state[key] = "" ได้ เพราะเราจะทำให้มัน rerun ทันที
                # แต่เพื่อความปลอดภัย ใช้ Logic Key แยกสำหรับ Tracking ที่ต้องยิงรัวๆ
                
                # Logic เฉพาะสำหรับ Mode A (ยิงรัว)
                if 'mode_a_counter' not in st.session_state: st.session_state.mode_a_counter = 0
                
                def on_track_a_submit():
                    # Callback
                    key = f"track_a_{st.session_state.mode_a_counter}"
                    val = st.session_state[key]
                    if val:
                        add_to_staging(val, st.session_state.locked_barcode, "Mode A")
                        st.session_state.mode_a_counter += 1 # เปลี่ยน Key เพื่อ Clear ช่อง
                
                track_key = f"track_a_{st.session_state.mode_a_counter}"
                st.text_input("2. ยิง Tracking ID (เพิ่มลงรายการ)", key=track_key, on_change=on_track_a_submit)
                st.button("เพิ่มรายการ (Manual)", on_click=on_track_a_submit)

        else:
            st.info("💡 Mode B: สแกนคู่ (Tracking + Barcode)")
            # Mode B ใช้ Logic คล้าย Mode A คือ Clear หลังยิงเสร็จ
            if 'mode_b_counter' not in st.session_state: st.session_state.mode_b_counter = 0
            
            c1, c2 = st.columns(2)
            
            # เราต้องเก็บค่า Tracking ไว้ชั่วคราวก่อนยิง Barcode
            if 'temp_tracking_b' not in st.session_state: st.session_state.temp_tracking_b = ""
            
            def on_track_b_change():
                key = f"track_b_{st.session_state.mode_b_counter}"
                st.session_state.temp_tracking_b = st.session_state[key]

            def on_barcode_b_submit():
                key_bc = f"bc_b_{st.session_state.mode_b_counter}"
                bc_val = st.session_state[key_bc]
                
                # Tracking ต้องเอามาจาก temp หรือ input
                # แต่ input tracking อาจจะหายไปแล้วถ้าเรา refresh? ไม่หายถ้า key เดิม
                # ใช้ค่าจาก temp_tracking_b ที่เก็บไว้
                track_val = st.session_state.temp_tracking_b
                
                if track_val and bc_val:
                    add_to_staging(track_val, bc_val, "Mode B")
                    st.session_state.mode_b_counter += 1 # Clear ทั้งคู่
                    st.session_state.temp_tracking_b = "" # Reset temp
            
            with c1: 
                # Tracking Input
                track_key = f"track_b_{st.session_state.mode_b_counter}"
                # ถ้ามีค่า temp ให้แสดง (Optional) แต่ปกติ input จะค้างอยู่
                st.text_input("1. Tracking ID", key=track_key, on_change=on_track_b_change)
                
            with c2: 
                # Barcode Input
                bc_key = f"bc_b_{st.session_state.mode_b_counter}"
                st.text_input("2. Product Barcode", key=bc_key, on_change=on_barcode_b_submit)

            st.button("เพิ่มรายการ", on_click=on_barcode_b_submit)

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
                    c2.caption(item['license_plate']) 
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
