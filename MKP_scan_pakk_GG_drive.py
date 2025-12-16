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
                row = [ts, item['user_id'], item['tracking'], item['barcode'], "Normal", 1, item['mode']]
                rows_to_add.append(row)
            ws.append_rows(rows_to_add)
            return True
    except Exception as e:
        st.error(f"Error: {e}")
        return False
    return False

# --- แก้ไข 1: เพิ่มฟังก์ชัน Clear Cache ---
@st.cache_data(ttl=30) 
def load_data_from_sheet():
    try:
        ws = get_sheet_connection()
        if ws:
            data = ws.get_all_values()
            if len(data) > 1:
                df = pd.DataFrame(data[1:], columns=data[0])
                # --- แก้ไข 2: ตัดช่องว่างชื่อหัวตารางออก (Trim Headers) ---
                df.columns = df.columns.str.strip()
                return df
    except: pass
    return pd.DataFrame()

# --- SESSION STATE ---
if 'user_id' not in st.session_state: st.session_state.user_id = ""
if 'staged_data' not in st.session_state: st.session_state.staged_data = [] 
if 'locked_barcode' not in st.session_state: st.session_state.locked_barcode = ""
if 'scan_error' not in st.session_state: st.session_state.scan_error = None 

# --- DUPLICATE CHECK FUNCTION ---
def check_duplicate(tracking):
    """
    return: (bool_is_duplicate, str_message)
    """
    # 1. เช็คใน Staging (รายการที่รอบันทึก)
    for item in st.session_state.staged_data:
        if str(item['tracking']).strip() == str(tracking).strip():
            return True, f"⚠️ ซ้ำในรายการรอ! ({tracking})"

    # 2. เช็คใน Google Sheet (Database)
    df = load_data_from_sheet()
    if not df.empty:
        # พยายามหา Column ที่เก็บ Tracking ID
        target_col = None
        # รายชื่อ Column ที่เป็นไปได้
        possible_cols = ['Tracking ID', 'Order ID', 'Tracking', 'tracking_id', 'order_id']
        
        for col in df.columns:
            if col in possible_cols:
                target_col = col
                break
        
        if target_col:
            # แปลงเป็น String และ Trim ช่องว่างเพื่อความชัวร์
            all_trackings = df[target_col].astype(str).str.strip().values
            if str(tracking).strip() in all_trackings:
                return True, f"⛔ เคยบันทึกไปแล้ว! ({tracking})"
        else:
            # กรณีหา Column ไม่เจอ ให้แจ้งเตือนเล็กน้อย (Optional debug)
            # st.toast(f"หา Column Tracking ไม่เจอใน Sheet: {list(df.columns)}", icon="❓")
            pass

    return False, ""

# --- CALLBACKS ---
def add_to_staging(tracking, barcode, mode):
    st.session_state.scan_error = None
    
    # Trim ค่าก่อนเช็ค
    tracking = tracking.strip()
    barcode = barcode.strip()

    is_dup, msg = check_duplicate(tracking)
    
    if is_dup:
        st.session_state.scan_error = msg 
        st.toast(msg, icon="🚫") 
        return 
        
    new_item = {
        "id": str(uuid.uuid4()), 
        "user_id": st.session_state.user_id,
        "tracking": tracking,
        "barcode": barcode,
        "mode": mode,
        "time_scan": datetime.now().strftime("%H:%M:%S")
    }
    st.session_state.staged_data.insert(0, new_item)
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
            
            # --- แก้ไข 3: สั่งล้าง Cache ทันที เพื่อให้การเช็คซ้ำครั้งต่อไปเป็นข้อมูลล่าสุด ---
            load_data_from_sheet.clear()
            
            st.balloons()
            time.sleep(1)
            st.rerun()
        else:
            st.error("❌ บันทึกไม่สำเร็จ กรุณาลองใหม่")

# --- MAIN APP ---
st.title("📦 MKP Scan & Pack (Pro)")

if not st.session_state.user_id:
    st.info("ระบุรหัสพนักงาน")
    u = st.text_input("User ID", key="login")
    if st.button("Start") and u: st.session_state.user_id = u; st.rerun()
else:
    with st.sidebar:
        st.write(f"👤 **{st.session_state.user_id}**")
        if st.button("Logout"): 
            st.session_state.user_id = ""
            st.session_state.staged_data = []
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
            st.info("💡 Mode A: สแกนสินค้าต้นแบบ 1 ครั้ง -> ยิง Tracking รัวๆ -> กดบันทึกทีเดียว")
            
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
            st.info("💡 Mode B: สแกนคู่ (Tracking + Barcode) -> เพิ่มลงรายการ -> กดบันทึกทีเดียว")
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
                h1, h2, h3, h4 = st.columns([1, 3, 3, 1])
                h1.markdown("**เวลา**")
                h2.markdown("**Tracking ID**")
                h3.markdown("**Barcode**")
                h4.markdown("**ลบ**")
                st.divider()
                
                for item in st.session_state.staged_data:
                    c1, c2, c3, c4 = st.columns([1, 3, 3, 1])
                    c1.caption(item['time_scan'])
                    c2.write(item['tracking'])
                    c3.write(item['barcode'])
                    c4.button("❌", key=f"del_{item['id']}", on_click=delete_from_staging, args=(item['id'],))
        else:
            st.caption("ยังไม่มีรายการสแกน... (สแกนเพื่อเพิ่มรายการ)")

    with tab2:
        if st.button("🔄 Refresh Data"): 
            load_data_from_sheet.clear() # Clear Cache ปุ่ม Refresh ด้วย
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
