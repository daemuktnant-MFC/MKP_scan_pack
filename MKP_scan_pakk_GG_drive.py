import streamlit as st
import pandas as pd
import gspread
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from datetime import datetime
import time
import pytz
import uuid  # ใช้สำหรับสร้าง ID อ้างอิงเวลาลบรายการ

# --- CONFIGURATION ---
SHEET_ID = '1Om9qwShA3hBQgKJPQNbJgDPInm9AQ2hY5Z8OuOpkF08'
SHEET_NAME = 'Data_Pack' 

# --- CSS STYLING ---
st.markdown("""
<style>
div.block-container { padding-top: 1rem; padding-bottom: 1rem; }
h1 { font-size: 1.8rem !important; margin-bottom: 0.5rem; }
.big-font { font-size: 20px !important; font-weight: bold; }
/* ปรับแต่งตารางรายการรอบันทึก */
.st-key-staging_container {
    border: 1px solid #ddd;
    border-radius: 10px;
    padding: 10px;
    background-color: #f9f9f9;
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
    """บันทึกข้อมูลทีละหลายแถว (Batch Save)"""
    try:
        ws = get_sheet_connection()
        if ws:
            # เตรียมข้อมูลสำหรับ append_rows (List of Lists)
            rows_to_add = []
            tz = pytz.timezone('Asia/Bangkok')
            ts = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
            
            for item in data_list:
                # Format: [Timestamp, User ID, Tracking ID, Barcode, Status, Qty, Note]
                row = [ts, item['user_id'], item['tracking'], item['barcode'], "Normal", 1, item['mode']]
                rows_to_add.append(row)
            
            ws.append_rows(rows_to_add)
            return True
    except Exception as e:
        st.error(f"Error: {e}")
        return False
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

# --- SESSION STATE MANAGEMENT ---
if 'user_id' not in st.session_state: st.session_state.user_id = ""
if 'staged_data' not in st.session_state: st.session_state.staged_data = [] # เก็บข้อมูลรอบันทึก
if 'locked_barcode' not in st.session_state: st.session_state.locked_barcode = ""

# --- CALLBACKS ---

def add_to_staging(tracking, barcode, mode):
    """เพิ่มข้อมูลลงรายการพัก (ยังไม่ลง Google Sheet)"""
    new_item = {
        "id": str(uuid.uuid4()), # สร้าง ID ไม่ซ้ำเพื่อใช้ตอนลบ
        "user_id": st.session_state.user_id,
        "tracking": tracking,
        "barcode": barcode,
        "mode": mode,
        "time_scan": datetime.now().strftime("%H:%M:%S")
    }
    # เพิ่มรายการใหม่ไปไว้บนสุด
    st.session_state.staged_data.insert(0, new_item)
    st.toast(f"📥 เพิ่มรายการ: {tracking}", icon="plus")

def delete_from_staging(item_id):
    """ลบรายการออกจาก Staging"""
    st.session_state.staged_data = [d for d in st.session_state.staged_data if d['id'] != item_id]
    st.toast("ลบรายการแล้ว", icon="🗑️")

def on_scan_mode_a():
    """Mode A: Scan Tracking -> Add to Staging"""
    tracking = st.session_state.mkp_tracking_a
    barcode = st.session_state.get('locked_barcode', '')
    if tracking and barcode:
        add_to_staging(tracking, barcode, "Mode A")
        st.session_state.mkp_tracking_a = "" # Clear input

def on_scan_mode_b():
    """Mode B: Scan Both -> Add to Staging"""
    tracking = st.session_state.mkp_tracking_b
    barcode = st.session_state.mkp_barcode_b
    if tracking and barcode:
        add_to_staging(tracking, barcode, "Mode B")
        st.session_state.mkp_tracking_b = ""
        st.session_state.mkp_barcode_b = ""

def confirm_save_all():
    """บันทึกทุกรายการลง Google Sheets"""
    if not st.session_state.staged_data:
        st.warning("ไม่มีรายการให้บันทึก")
        return

    with st.spinner(f"กำลังบันทึก {len(st.session_state.staged_data)} รายการ..."):
        # ส่งข้อมูลไปบันทึก (เรียงจากเก่าไปใหม่ เพื่อให้ Timestamp ใน Excel ถูกต้อง)
        # staged_data เราเก็บแบบ ใหม่->เก่า เพื่อโชว์ใน App แต่ตอนบันทึกควรบันทึกแบบ เก่า->ใหม่
        data_to_save = st.session_state.staged_data[::-1] 
        
        success = save_batch_to_sheet(data_to_save)
        
        if success:
            st.success("✅ บันทึกข้อมูลลง Google Sheet เรียบร้อย!")
            st.session_state.staged_data = [] # ล้างค่าทั้งหมด
            st.balloons()
            time.sleep(1)
            st.rerun()
        else:
            st.error("❌ บันทึกไม่สำเร็จ กรุณาลองใหม่")

# --- MAIN APP ---
st.title("📦 MKP Scan & Pack (Batch Save)")

# --- LOGIN ---
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
        # เลือกโหมดการทำงาน
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

        # === STAGING TABLE AREA (ส่วนที่ปรับปรุงใหม่) ===
        st.markdown("---")
        count_waiting = len(st.session_state.staged_data)
        
        # Header ของตาราง
        col_h1, col_h2 = st.columns([3, 1])
        with col_h1:
            st.subheader(f"📋 รายการรอบันทึก ({count_waiting})")
        with col_h2:
            # ปุ่มบันทึกใหญ่ๆ
            if count_waiting > 0:
                st.button(f"☁️ ยืนยันบันทึก ({count_waiting})", type="primary", use_container_width=True, on_click=confirm_save_all)

        if count_waiting > 0:
            # แสดงรายการแบบ Loop สร้าง Container
            with st.container(border=True):
                # หัวตาราง
                h1, h2, h3, h4 = st.columns([1, 3, 3, 1])
                h1.markdown("**เวลา**")
                h2.markdown("**Tracking ID**")
                h3.markdown("**Barcode**")
                h4.markdown("**ลบ**")
                st.divider()
                
                # Loop Data
                for item in st.session_state.staged_data:
                    c1, c2, c3, c4 = st.columns([1, 3, 3, 1])
                    c1.caption(item['time_scan'])
                    c2.write(item['tracking'])
                    c3.write(item['barcode'])
                    # ปุ่มลบแต่ละบรรทัด
                    c4.button("❌", key=f"del_{item['id']}", on_click=delete_from_staging, args=(item['id'],))
        else:
            st.caption("ยังไม่มีรายการสแกน... (สแกนเพื่อเพิ่มรายการ)")

    with tab2:
        if st.button("🔄 Refresh Data"): st.cache_data.clear(); st.rerun()
        df = load_data_from_sheet()
        if not df.empty:
            df.rename(columns={'Order ID': 'Tracking ID'}, inplace=True)
            st.write(f"Total Saved: {len(df)}")
            st.dataframe(df.tail(10), use_container_width=True)
