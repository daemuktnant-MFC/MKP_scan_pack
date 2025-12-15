import streamlit as st
import pandas as pd
import gspread
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from datetime import datetime, timedelta
import time
import pytz

# --- CONFIGURATION (อัปเดตตามที่คุณส่งมา) ---
SHEET_ID = '1Om9qwShA3hBQgKJPQNbJgDPInm9AQ2hY5Z8OuOpkF08'
SHEET_NAME = 'Data_Pack' 

# --- CSS STYLING ---
st.markdown("""
<style>
div.block-container { padding-top: 1rem; padding-bottom: 1rem; }
h1 { font-size: 1.8rem !important; margin-bottom: 0.5rem; }
[data-testid="stMetric"] { background-color: #FAFAFA; border-radius: 0.25rem; padding: 0.25rem 1rem !important; }
</style>
""", unsafe_allow_html=True)

# --- AUTHENTICATION FUNCTIONS ---
def get_credentials():
    try:
        if "oauth" in st.secrets:
            info = st.secrets["oauth"]
            creds = Credentials(
                None,
                refresh_token=info["refresh_token"],
                token_uri="https://oauth2.googleapis.com/token",
                client_id=info["client_id"],
                client_secret=info["client_secret"]
            )
            return creds
        else:
            st.error("❌ ไม่พบข้อมูล [oauth] ใน Secrets")
            return None
    except Exception as e:
        st.error(f"❌ Error Credentials: {e}")
        return None

# --- GOOGLE SHEETS FUNCTIONS ---
def get_sheet_connection():
    creds = get_credentials()
    if creds:
        gc = gspread.authorize(creds)
        try:
            sh = gc.open_by_key(SHEET_ID)
            worksheet = sh.worksheet(SHEET_NAME)
            return worksheet
        except gspread.WorksheetNotFound:
            st.error(f"❌ ไม่พบ Tab ชื่อ '{SHEET_NAME}' ใน Google Sheet")
            st.info("กรุณาตรวจสอบชื่อ Tab ด้านล่างของ Google Sheet ว่าชื่อ 'Data_Pack' ถูกต้องหรือไม่")
            return None
        except Exception as e:
            st.error(f"❌ ไม่สามารถเปิด Google Sheet ได้: {e}")
            return None
    return None

def save_data_to_sheet(user_id, order_id, barcode, status, qty, note=""):
    try:
        worksheet = get_sheet_connection()
        if worksheet:
            # เวลาไทย UTC+7
            tz = pytz.timezone('Asia/Bangkok')
            timestamp = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
            
            # เรียงลำดับข้อมูลให้ตรงกับ Header
            # Timestamp, User ID, Order ID, Barcode, Status, Qty, Note
            row_data = [timestamp, user_id, order_id, barcode, status, qty, note]
            
            worksheet.append_row(row_data)
            return True
    except Exception as e:
        st.error(f"Error Saving Data: {e}")
        return False
    return False

@st.cache_data(ttl=10) # ลด Cache เหลือ 10 วินาที เพื่อให้เห็นข้อมูลใหม่ไวขึ้น
def load_data_from_sheet():
    try:
        worksheet = get_sheet_connection()
        if worksheet:
            data = worksheet.get_all_values()
            if len(data) > 1:
                headers = data[0]
                rows = data[1:]
                df = pd.DataFrame(rows, columns=headers)
                return df
            else:
                return pd.DataFrame(columns=['Timestamp', 'User ID', 'Order ID', 'Barcode', 'Status', 'Qty', 'Note'])
    except Exception as e:
        st.error(f"Error Loading Data: {e}")
    return pd.DataFrame()

# --- MAIN APP ---
st.title("📦 MKP Scan & Pack")

# Session State Init
if 'user_id' not in st.session_state: st.session_state.user_id = ""
if 'scan_history' not in st.session_state: st.session_state.scan_history = []

# --- LOGIN SECTION ---
if not st.session_state.user_id:
    st.info("กรุณาระบุรหัสพนักงานก่อนเริ่มงาน")
    user_input = st.text_input("รหัสพนักงาน (User ID)", key="login_input")
    if st.button("เข้าสู่ระบบ") and user_input:
        st.session_state.user_id = user_input
        st.rerun()
else:
    # Sidebar
    with st.sidebar:
        st.write(f"👤 User: **{st.session_state.user_id}**")
        if st.button("Logout", type="secondary"):
            st.session_state.user_id = ""
            st.rerun()

    # Tabs
    tab1, tab2 = st.tabs(["📷 Scan & Pack", "📊 Dashboard"])

    # --- TAB 1: SCAN & PACK ---
    with tab1:
        st.subheader("บันทึกการแพ็คสินค้า")
        
        col1, col2 = st.columns(2)
        with col1:
            order_id = st.text_input("📦 Order ID", key="input_order").strip()
        with col2:
            barcode = st.text_input("🏷️ Product Barcode", key="input_barcode").strip()
            
        col_qty, col_status = st.columns(2)
        with col_qty:
            qty = st.number_input("จำนวน", min_value=1, value=1)
        with col_status:
            status_opt = st.selectbox("สถานะ", ["Normal", "Damaged", "Missing", "Wrong Item"])

        note = st.text_area("หมายเหตุ (ถ้ามี)", height=68)

        # ปุ่มบันทึก
        if st.button("💾 บันทึกข้อมูล (Save)", type="primary", use_container_width=True):
            if order_id and barcode:
                with st.spinner("กำลังบันทึกข้อมูลลง Google Sheets..."):
                    success = save_data_to_sheet(
                        st.session_state.user_id, 
                        order_id, 
                        barcode, 
                        status_opt, 
                        qty, 
                        note
                    )
                    
                    if success:
                        st.success(f"✅ บันทึก Order: {order_id} เรียบร้อย!")
                        # เก็บประวัติไว้โชว์ชั่วคราวใน session
                        st.session_state.scan_history.insert(0, {
                            "Time": datetime.now().strftime("%H:%M:%S"),
                            "Order": order_id,
                            "Item": barcode,
                            "Status": status_opt
                        })
                        time.sleep(1)
                    else:
                        st.error("เกิดข้อผิดพลาดในการบันทึก")
            else:
                st.warning("⚠️ กรุณากรอก Order ID และ Barcode")

        # History ล่าสุด (Local Session)
        if st.session_state.scan_history:
            st.divider()
            st.caption("ประวัติการสแกนล่าสุด (Session นี้)")
            st.dataframe(pd.DataFrame(st.session_state.scan_history), use_container_width=True, hide_index=True)

    # --- TAB 2: DASHBOARD ---
    with tab2:
        st.subheader("📦 ประวัติข้อมูลทั้งหมด (จาก Google Sheets)")
        
        if st.button("🔄 โหลดข้อมูลล่าสุด"):
            st.cache_data.clear()
            st.rerun()

        df = load_data_from_sheet()

        if not df.empty:
            # Filters
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                search_order = st.text_input("🔍 ค้นหา Order ID", key="search_dash")
            with col_f2:
                if 'User ID' in df.columns:
                    filter_user = st.multiselect("กรอง User", options=df['User ID'].unique())
                else:
                    filter_user = []

            # Apply Filters
            df_show = df.copy()
            if search_order and 'Order ID' in df_show.columns:
                df_show = df_show[df_show['Order ID'].astype(str).str.contains(search_order, case=False, na=False)]
            if filter_user and 'User ID' in df_show.columns:
                df_show = df_show[df_show['User ID'].isin(filter_user)]

            # Summary Metrics
            m1, m2, m3 = st.columns(3)
            m1.metric("Total Rows", len(df_show))
            if 'Order ID' in df_show.columns:
                m2.metric("Unique Orders", df_show['Order ID'].nunique())
            
            # Try to sum Qty
            try:
                if 'Qty' in df_show.columns:
                    total_qty = df_show['Qty'].astype(int).sum()
                    m3.metric("Total Items (Qty)", total_qty)
            except:
                m3.metric("Total Items", "N/A")

            st.dataframe(df_show, use_container_width=True, hide_index=True)
            
            # Download CSV
            csv = df_show.to_csv(index=False).encode('utf-8')
            st.download_button(
                "📥 Download CSV",
                csv,
                "mkp_data_pack.csv",
                "text/csv",
                key='download-csv'
            )
        else:
            st.info("ยังไม่มีข้อมูลใน Google Sheet")
