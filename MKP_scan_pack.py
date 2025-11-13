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
st.title("📦 App สแกน Tracking") # (ชื่่อตามไฟล์ที่คุณให้มา)

@st.cache_resource
def init_supabase_connection():
    return st.connection("supabase", type=SQLConnection)

supabase_conn = init_supabase_connection()

# --- 2. สร้าง Session State (เหมือนเดิม) ---
if "current_user" not in st.session_state:
    st.session_state.current_user = ""
if "scan_count" not in st.session_state:
    st.session_state.scan_count = 0
if "temp_tracking" not in st.session_state:
    st.session_state.temp_tracking = ""
if "temp_barcode" not in st.session_state:
    st.session_state.temp_barcode = ""
if "staged_scans" not in st.session_state:
    st.session_state.staged_scans = []
if "show_dialog_for" not in st.session_state:
    st.session_state.show_dialog_for = None 
if "show_scan_error_message" not in st.session_state:
    st.session_state.show_scan_error_message = False

# --- 3. สร้างฟังก์ชันสำหรับปุ่ม (Callbacks) (เหมือนเดิม) ---
def delete_item(item_id_to_delete):
    st.session_state.staged_scans = [
        item for item in st.session_state.staged_scans 
        if item["id"] != item_id_to_delete
    ]

def add_and_clear_staging():
    if st.session_state.temp_tracking and st.session_state.temp_barcode:
        st.session_state.staged_scans.append({
            "id": str(uuid.uuid4()),
            "tracking": st.session_state.temp_tracking,
            "barcode": st.session_state.temp_barcode
        })
        st.session_state.temp_tracking = ""
        st.session_state.temp_barcode = ""
        st.session_state.show_dialog_for = None 
    st.rerun() 

def save_all_to_db():
    if not st.session_state.staged_scans:
        st.warning("ไม่มีข้อมูลในรายการให้บันทึก")
        return
    try:
        data_to_insert = []
        THAI_TZ = pytz.timezone("Asia/Bangkok")
        current_time = datetime.now(THAI_TZ)
        
        for item in st.session_state.staged_scans:
            data_to_insert.append({
                "user_id": st.session_state.current_user,
                "tracking_code": item["tracking"],
                "product_barcode": item["barcode"],
                "created_at": current_time.replace(tzinfo=None) 
            })
        
        df_to_insert = pd.DataFrame(data_to_insert)
        df_to_insert.to_sql(
            "scans", 
            con=supabase_conn.engine, 
            if_exists="append", 
            index=False
        )
        
        saved_count = len(st.session_state.staged_scans)
        st.session_state.scan_count += saved_count
        st.session_state.staged_scans = []
        st.session_state.current_user = "" 
        st.success(f"บันทึกข้อมูลทั้ง {saved_count} รายการ สำเร็จ!")
        st.rerun() 
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการบันทึก: {e}")

# --- 🟢 (แก้ไข) Dialog Function (สลับ Logic) 🟢 ---
@st.dialog("✅ สแกนสำเร็จ")
def show_confirmation_dialog(is_tracking):
    # (is_tracking=False คือ Barcode, is_tracking=True คือ Tracking)
    code_type = "Tracking Number" if is_tracking else "Barcode สินค้า"
    code_value = st.session_state.temp_tracking if is_tracking else st.session_state.temp_barcode
    
    st.info(f"ยืนยัน {code_type} ที่สแกนได้:")
    st.code(code_value)
    
    if is_tracking:
        # (นี่คือการสแกนครั้งที่ 2 - Tracking)
        st.success("Tracking ถูกสแกนและยืนยันแล้ว!")
        st.warning("ข้อมูลจะถูกเพิ่มลงในรายการทันที")
        if st.button("ปิด (และเพิ่มลงในรายการ)"):
            add_and_clear_staging()
    else: 
        # (นี่คือการสแกนครั้งที่ 1 - Barcode)
        st.warning("ขั้นต่อไป: กด 'ปิด' แล้วสแกน Tracking")
        if st.button("ปิด (และเตรียมสแกน Tracking)"):
            st.session_state.show_dialog_for = None
            st.rerun()
# --- 🟢 สิ้นสุดการแก้ไข 🟢 ---

# --- 4. แบ่งหน้าจอด้วย Tabs ---
tab1, tab2 = st.tabs(["📷 สแกนกล่อง", "📊 ดูข้อมูลและดาวน์โหลด"])

# --- TAB 1: หน้าสแกน (ปรับ Layout) ---
with tab1:
    st.header("บันทึกการสแกน")

    # --- 🟢 (แก้ไข) Logic แสดง "กล่อง Error" 🟢 ---
    if st.session_state.get("show_scan_error_message", False):
        st.error("⚠️ สแกนซ้ำ! กรุณาสแกน Tracking", icon="⚠️") # (เปลี่ยนข้อความ)
    # --- 🟢 สิ้นสุด 🟢 ---

    col_user, col_metric = st.columns([3, 2]) 
    with col_user:
        st.text_input("ชื่อผู้ใช้งาน (User):", key="current_user") 
    with col_metric:
        st.metric("กล่องใน DB (รอบนี้)", st.session_state.scan_count)

    if not st.session_state.current_user:
        st.warning("ป้อนชื่อผู้ใช้งานก่อนเริ่มสแกน")
    else:
        
        if st.session_state.show_dialog_for == 'tracking':
             show_confirmation_dialog(is_tracking=True)
        elif st.session_state.show_dialog_for == 'barcode':
             show_confirmation_dialog(is_tracking=False)
             
        st.subheader("1. สแกนที่นี่ (Scan Here)")
        
        if st.session_state.show_dialog_for is None:
            
            # --- 🟢 (แก้ไข) สลับ Logic ข้อความแนะนำ 🟢 ---
            if not st.session_state.temp_barcode:
                st.info("ขั้นตอนที่ 1: สแกน Barcode...")
            elif not st.session_state.temp_tracking:
                 if not st.session_state.show_scan_error_message:
                     st.success("ขั้นตอนที่ 2: สแกน Tracking...")
            # --- 🟢 สิ้นสุดการแก้ไข 🟢 ---
            else:
                 st.success("สำเร็จ! เริ่มสแกน Barcode กล่องถัดไป")
                 st.session_state.temp_barcode = "" # (เปลี่ยน) ล้าง Barcode
                 st.rerun() 

            scan_value = qrcode_scanner(key="main_scanner")

            if scan_value:
                # --- 🟢 (แก้ไข) สลับ Logic การสแกนทั้งหมด 🟢 ---
                
                # Logic 1: สแกน Barcode (ครั้งแรก)
                if not st.session_state.temp_barcode:
                    st.session_state.temp_barcode = scan_value
                    st.session_state.show_dialog_for = 'barcode' 
                    st.rerun() 
                
                # Logic 2: สแกน Tracking (ครั้งที่ 2)
                elif st.session_state.temp_barcode and not st.session_state.temp_tracking:
                    # (เปลี่ยน) ตรวจสอบว่าสแกน Barcode ซ้ำหรือไม่
                    if scan_value != st.session_state.temp_barcode: 
                        # (ถูกต้อง) นี่คือ Tracking
                        st.session_state.temp_tracking = scan_value
                        st.session_state.show_dialog_for = 'tracking' 
                        st.session_state.show_scan_error_message = False # ล้างธง Error
                        st.rerun() 
                    
                    else:
                        # (สแกนซ้ำ) นี่คือ Barcode เดิม
                        st.session_state.show_scan_error_message = True # 1. ตั้งธง
                        st.rerun() # 2. บังคับ rerun
                        
                elif st.session_state.temp_barcode and st.session_state.temp_tracking:
                    st.warning("รอสักครู่ (ระบบกำลังเพิ่มรายการ) หรือเริ่มสแกน Barcode ถัดไปได้เลย")
                # --- 🟢 สิ้นสุดการแก้ไข 🟢 ---
        
        else:
            st.info(f"... กด 'ปิด' ใน Popup ยืนยัน {st.session_state.show_dialog_for.capitalize()} ...")

        st.subheader("2. ข้อมูลที่กำลังสแกน")
        
        col_t, col_b = st.columns(2)
        with col_t:
            st.text_input("Tracking", value=st.session_state.temp_tracking, 
                          disabled=True, label_visibility="collapsed")
            st.caption("Tracking ที่สแกนได้") 
        with col_b:
            st.text_input("Barcode", value=st.session_state.temp_barcode, 
                          disabled=True, label_visibility="collapsed")
            st.caption("Barcode ที่สแกนได้") 
        
        st.divider()

        # --- (ย้ายมา) ปุ่มบันทึกข้อมูล ---
        st.button("💾 บันทึกทั้งหมด",
                  type="primary",
                  use_container_width=True,
                  on_click=save_all_to_db,
                  disabled=(not st.session_state.staged_scans)
                 )

        # --- (ปรับ) ส่วนที่ 3: ตารางพักข้อมูล (Layout แบบ Card) ---
        st.subheader(f"3. รายการที่กำลังสแกน ({len(st.session_state.staged_scans)} รายการ)")
        
        if not st.session_state.staged_scans:
            st.info("ยังไม่มีรายการสแกน สแกน Barcode และ Tracking") # (เปลี่ยนข้อความ)
        else:
            for item in reversed(st.session_state.staged_scans): 
                with st.container(border=True):
                    st.caption("Tracking:")
                    st.code(item["tracking"])
                    st.caption("Barcode:")
                    col_b, col_del = st.columns([4, 1]) 
                    with col_b:
                        st.code(item["barcode"])
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
    try:
        query = "SELECT * FROM scans"
        filters = []
        params = {}
        if filter_user:
            filters.append("user_id = :user")
            params["user"] = filter_user
        if filter_date:
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
        st.error(f"เกิดข้อผิดพลาดในการบันทึก: {e}")
