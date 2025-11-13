import streamlit as st
import pandas as pd
import io
from datetime import datetime
from streamlit.connections import SQLConnection
from streamlit_qrcode_scanner import qrcode_scanner
import uuid
import pytz

# --- (CSS สำหรับ Mobile Layout - เหมือนเดิม) ---
st.markdown("""
<style>
/* 1. Base Layout (เหมือนเดิม) */
div.block-container {
    padding-top: 1rem; padding-bottom: 1rem;
    padding-left: 1rem; padding-right: 1rem;
}
/* 2. Headers (เหมือนเดิม) */
h1 { font-size: 1.8rem !important; margin-bottom: 0.5rem; }
h3 { font-size: 1.15rem !important; margin-top: 1rem; margin-bottom: 0.5rem; }
/* 3. Metric (เหมือนเดิม) */
[data-testid="stMetric"] {
    padding-top: 0 !important; background-color: #FAFAFA;
    border-radius: 0.5rem; padding: 0.5rem 1rem !important;
}
[data-testid="stMetricValue"] { font-size: 1.8rem !important; }
[data-testid="stMetricLabel"] { font-size: 0.9rem !important; }

/* 4. Staging Card Container (กรอบของแต่ละรายการ) */
[data-testid="stVerticalBlock"] > [data-testid="stContainer"] {
    border: 1px solid #BBBBBB !important; 
    border-radius: 0.5rem;
    padding: 0.5rem 0.75rem !important; 
    margin-bottom: 0.5rem; 
}
/* 5. Code Box (Tracking/Barcode) ในการ์ด */
.stCode { 
    font-size: 0.75rem !important; 
    padding: 0.4em !important; 
}
/* 6. ปุ่ม "ลบ" (❌) ในการ์ด */
div[data-testid="stHorizontalBlock"] > div:nth-child(2) .stButton button {
    font-size: 0.8rem !important; 
    padding: 0.4em 0.5em !important; 
    height: 2.8em !important; 
}
</style>
""", unsafe_allow_html=True)
# --- จบ Custom CSS ---


# --- 1. ตั้งค่าหน้าจอและเชื่อมต่อ Supabase ---
st.set_page_config(page_title="Box Scanner", layout="wide")
st.title("📦 App สแกน Tracking")

@st.cache_resource
def init_supabase_connection():
    return st.connection("supabase", type=SQLConnection)

supabase_conn = init_supabase_connection()

# --- 2. สร้าง Session State (ปรับปรุงสำหรับ Logic ใหม่) ---
if "current_user" not in st.session_state:
    st.session_state.current_user = ""
if "scan_count" not in st.session_state:
    st.session_state.scan_count = 0 # (ใหม่) จะใช้เป็น "ยอดสะสม" ที่บันทึกไปแล้ว
if "temp_barcode" not in st.session_state:
    st.session_state.temp_barcode = "" # นี่คือ Barcode ที่จะใช้สำหรับทุก Tracking
if "staged_scans" not in st.session_state:
    st.session_state.staged_scans = [] # รายการ Tracking ที่รอการบันทึก
if "show_duplicate_tracking_error" not in st.session_state:
    st.session_state.show_duplicate_tracking_error = False # ธงสำหรับแจ้งเตือน Tracking ซ้ำ
if "last_scanned_tracking" not in st.session_state:
    st.session_state.last_scanned_tracking = "" # สำหรับแสดงข้อความ Error ว่า Tracking ไหนซ้ำ

# --- 3. สร้างฟังก์ชันสำหรับปุ่ม (Callbacks) (ปรับปรุง) ---

def delete_item(item_id_to_delete):
    """ลบรายการเดียวออกจาก Staging list"""
    st.session_state.staged_scans = [
        item for item in st.session_state.staged_scans 
        if item["id"] != item_id_to_delete
    ]

def clear_barcode_and_staging():
    """(ใหม่) ล้าง Barcode ที่ล็อคไว้ และล้าง Staging list ทั้งหมด"""
    st.session_state.temp_barcode = ""
    st.session_state.staged_scans = []
    st.session_state.show_duplicate_tracking_error = False
    st.session_state.last_scanned_tracking = ""
    st.rerun()

def save_all_to_db():
    """บันทึก Staging list ทั้งหมดลง Database"""
    if not st.session_state.staged_scans:
        st.warning("ไม่มีข้อมูลในรายการให้บันทึก")
        return
    if not st.session_state.current_user:
         st.error("ไม่พบชื่อผู้ใช้งาน! กรุณาป้อนชื่อผู้ใช้งาน")
         return
    if not st.session_state.temp_barcode:
         st.error("ไม่พบ Barcode! (เกิดข้อผิดพลาด) กรุณาล้างและสแกนใหม่")
         return
         
    try:
        data_to_insert = []
        THAI_TZ = pytz.timezone("Asia/Bangkok")
        current_time = datetime.now(THAI_TZ)
        
        # วนลูปสร้าง list ของ dicts ที่จะ insert
        for item in st.session_state.staged_scans:
            data_to_insert.append({
                "user_id": st.session_state.current_user,
                "tracking_code": item["tracking"],
                "product_barcode": item["barcode"], # Barcode จะมาจาก item ใน list
                "created_at": current_time.replace(tzinfo=None) 
            })
        
        # แปลงเป็น DataFrame และ Insert ลง SQL
        df_to_insert = pd.DataFrame(data_to_insert)
        df_to_insert.to_sql(
            "scans", 
            con=supabase_conn.engine, 
            if_exists="append", 
            index=False
        )
        
        # เคลียร์ค่าหลังจากบันทึกสำเร็จ
        saved_count = len(st.session_state.staged_scans)
        st.session_state.scan_count += saved_count # เพิ่มยอดสะสม

        # --- 🟢 (แก้ไข) เคลียร์ค่าทั้งหมด ---
        st.session_state.staged_scans = []
        st.session_state.temp_barcode = "" 
        st.session_state.show_duplicate_tracking_error = False
        st.session_state.last_scanned_tracking = ""
        st.session_state.current_user = "" # <-- 🟢 (แก้ไข) เพิ่มบรรทัดนี้เพื่อล้างค่า User
        # --- 🟢 สิ้นสุด 🟢 ---
        
        st.success(f"บันทึกข้อมูลทั้ง {saved_count} รายการ สำเร็จ!")
        
        # ❌ (แก้ไข) ลบ st.rerun() ออก เพราะ on_click จะ Rerun ให้อัตโนมัติ
        # st.rerun() 
        
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการบันทึก: {e}")

# --- 4. แบ่งหน้าจอด้วย Tabs ---
tab1, tab2 = st.tabs(["📷 สแกนกล่อง", "📊 ดูข้อมูลและดาวน์โหลด"])

# --- TAB 1: หน้าสแกน (แก้ไข Logic การ Rerun) ---
# --- TAB 1: หน้าสแกน (ปรับ Logic เหลือปุ่มฉุกเฉินปุ่มเดียว) ---
with tab1:
    #st.header("บันทึกการสแกน")

    # --- ส่วนที่ 1: แสดงผล (Display Area) ---
    col_user_display, col_metric = st.columns([3, 2])
    
    with col_user_display:
        st.subheader("1. ผู้ใช้งาน (User)")
        if st.session_state.current_user:
            # (คงเดิม) แสดง User ที่ล็อค และปุ่มล้างหลัก
            st.code(st.session_state.current_user)
            st.button("❌ เปลี่ยน User (และเริ่มใหม่)", on_click=clear_all_and_restart)
        else:
            st.info("...รอล็อค User...")
    
    with col_metric:
        st.metric("Tracking ที่สแกน (รอบนี้)", len(st.session_state.staged_scans))

    st.divider()

    # --- ส่วนที่ 2: Logic การสแกน (State Machine 3 ขั้นตอน) ---
    scan_value = None 

    # --- 2A: State 1: ยังไม่มี User (บังคับสแกน User ก่อน) ---
    if not st.session_state.current_user:
        st.subheader("ขั้นตอนที่ 1: สแกน 'ชื่อผู้ใช้งาน'")
        st.info("กรุณาสแกน QR Code/Barcode ของ 'ชื่อผู้ใช้งาน'...")
        
        if st.session_state.show_duplicate_tracking_error:
            st.session_state.show_duplicate_tracking_error = False

        scan_value = qrcode_scanner(key="scanner_user") 
        
        if scan_value:
            st.session_state.current_user = scan_value
            st.success(f"User: {scan_value} ถูกล็อคแล้ว")
            # (ไม่ต้อง rerun)

    # --- 2B: State 2: มี User, ไม่มี Barcode (บังคับสแกน Barcode) ---
    elif not st.session_state.temp_barcode:
        st.subheader("ขั้นตอนที่ 2: สแกน Barcode สินค้า")
        st.info("สแกน Barcode สินค้าที่จะใช้...")
        
        scan_value = qrcode_scanner(key="scanner_barcode")
        
        if scan_value:
            if scan_value == st.session_state.current_user:
                st.warning("⚠️ นั่นคือ User! กรุณาสแกน Barcode สินค้า", icon="⚠️")
            else:
                st.session_state.temp_barcode = scan_value
                st.success(f"Barcode: {scan_value} ถูกล็อคแล้ว")
                # (ไม่ต้อง rerun)

    # --- 2C: State 3: มี User และ Barcode (พร้อมสแกน Tracking) ---
    else:
        # --- 🟢 (แก้ไข) ลบปุ่ม "เปลี่ยน Barcode" ออก ---
        st.subheader("2. Barcode ที่ล็อคอยู่")
        st.code(st.session_state.temp_barcode)
        # st.button("❌ เปลี่ยน/ล้าง Barcode นี้ (และเริ่มใหม่)", on_click=clear_barcode_and_staging) # <-- ❌ ลบปุ่มนี้ออก
        st.divider()
        # --- 🟢 สิ้นสุด 🟢 ---
        
        st.subheader("ขั้นตอนที่ 3: สแกน Tracking Number")

        if st.session_state.show_duplicate_tracking_error:
            st.error(f"⚠️ สแกนซ้ำ! Tracking '{st.session_state.last_scanned_tracking}' มีอยู่ในรายการแล้ว", icon="⚠️")
        else:
            st.info("สแกน Tracking Number ทีละกล่อง...")

        scan_value = qrcode_scanner(key="scanner_tracking")

        if scan_value:
            if scan_value == st.session_state.temp_barcode:
                st.warning("⚠️ นั่นคือ Barcode เดิม! กรุณาสแกน Tracking Number", icon="⚠️")
                st.session_state.show_duplicate_tracking_error = False
            elif scan_value == st.session_state.current_user:
                st.warning("⚠️ นั่นคือ User! กรุณาสแกน Tracking Number", icon="⚠️")
                st.session_state.show_duplicate_tracking_error = False
            elif any(item["tracking"] == scan_value for item in st.session_state.staged_scans):
                st.session_state.show_duplicate_tracking_error = True
                st.session_state.last_scanned_tracking = scan_value 
            else:
                st.session_state.staged_scans.append({
                    "id": str(uuid.uuid4()),
                    "tracking": scan_value,
                    "barcode": st.session_state.temp_barcode 
                })
                st.session_state.show_duplicate_tracking_error = False
                st.success(f"เพิ่ม Tracking: {scan_value} สำเร็จ!")
                # (ไม่ต้อง rerun)

    st.divider()

    # --- ส่วนที่ 3: ปุ่มบันทึก และ รายการที่กำลังสแกน ---
    st.button("💾 บันทึกทั้งหมด (และเริ่มใหม่)",
              type="primary",
              use_container_width=True,
              on_click=save_all_to_db,
              disabled=(not st.session_state.staged_scans or not st.session_state.temp_barcode or not st.session_state.current_user)
             )

    st.subheader(f"3. รายการที่กำลังสแกน ({len(st.session_state.staged_scans)} รายการ)")
    
    # (ส่วนที่เหลือของ tab1 เหมือนเดิม)
    if not st.session_state.staged_scans:
        if st.session_state.temp_barcode:
            st.info(f"ยังไม่มีรายการสแกน... (Barcode ที่ใช้คือ: {st.session_state.temp_barcode})")
        elif st.session_state.current_user:
            st.info(f"ยังไม่มีรายการสแกน... (User คือ: {st.session_state.current_user})")
        else:
             st.info("ยังไม่มีรายการสแกน...")
    else:
        for item in reversed(st.session_state.staged_scans): 
            with st.container(border=True):
                st.caption(f"Barcode: {item['barcode']}")
                st.caption("Tracking:")
                
                col_code, col_del = st.columns([4, 1]) 
                with col_code:
                    st.code(item["tracking"]) 
                with col_del:
                    st.button("❌ ลบ", 
                              key=f"del_{item['id']}", 
                              on_click=delete_item, 
                              args=(item['id'],),
                              use_container_width=True
                             )

# --- TAB 2: หน้าดูข้อมูลและดาวน์โหลด (เหมือนเดิม) ---
with tab2:
    st.header("ค้นหาและดาวน์โหลดข้อมูล")
    
    with st.expander("ตัวกรองข้อมูล (Filter)", expanded=True):
        col_f1, col_col2 = st.columns(2)
        with col_f1:
            filter_user = st.text_input("กรองตาม User (เว้นว่างเพื่อแสดงทั้งหมด)")
        with col_col2:
            filter_date = st.date_input("กรองตามวันที่", value=None) 
            
    # (ใหม่) แสดงยอดสะสมที่บันทึกไปในรอบนี้
    st.metric("กล่องที่บันทึกไปแล้ว (รอบนี้)", st.session_state.scan_count)
    st.divider()

    try:
        query = "SELECT * FROM scans"
        filters = []
        params = {}
        if filter_user:
            filters.append("user_id = :user")
            params["user"] = filter_user
        if filter_date:
            # (ปรับ) แก้ไขการ Query วันที่สำหรับ Supabase/Postgres
            filters.append("DATE(created_at AT TIME ZONE 'Asia/Bangkok') = :date")
            params["date"] = filter_date
            
        if filters:
            query += " WHERE " + " AND ".join(filters)
        
        query += " ORDER BY created_at DESC"
        data_df = supabase_conn.query(query, params=params)
        
        if not data_df.empty:
            st.dataframe(data_df, use_container_width=True)
            
            @st.cache_data
            def convert_df_to_csv(df_to_convert):
                # (ปรับ) บังคับ Encoding เป็น utf-8-sig เพื่อกันภาษาไทยเพี้ยนใน Excel
                return df_to_convert.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
            
            csv_data = convert_df_to_csv(data_df)
            
            st.download_button(
                label="📥 Download ข้อมูลเป็น CSV",
                data=csv_data,
                file_name=f"scan_export_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )
        else:
            st.info("ไม่พบข้อมูลตามเงื่อนไขที่เลือก")
            
    except Exception as e:
        # (ปรับ) ใช้ st.error แทน st.error เพื่อให้ชัดเจน
        st.error(f"เกิดข้อผิดพลาดในการดึงข้อมูล: {e}")
