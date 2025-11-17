import streamlit as st
import pandas as pd
import io
from datetime import datetime
from streamlit.connections import SQLConnection
from streamlit_qrcode_scanner import qrcode_scanner
import uuid 
import pytz 
from sqlalchemy import text # 🟢 (เพิ่ม) Import ที่จำเป็น

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

# --- 2. สร้าง Session State ---
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

# --- 🟢 (เพิ่ม) State จาก Bulk_version ---
if "scanner_key" not in st.session_state:
    st.session_state.scanner_key = "scanner_v1"
if "last_scan_processed" not in st.session_state:
    st.session_state.last_scan_processed = ""
if "show_user_not_found_error" not in st.session_state:
    st.session_state.show_user_not_found_error = False
if "last_failed_user_scan" not in st.session_state:
    st.session_state.last_failed_user_scan = ""
# --- 🟢 สิ้นสุด 🟢 ---


# --- 3. สร้างฟังก์ชันสำหรับปุ่ม (Callbacks) ---

def delete_item(item_id_to_delete):
    st.session_state.staged_scans = [
        item for item in st.session_state.staged_scans 
        if item["id"] != item_id_to_delete
    ]

# --- 🟢 (เพิ่ม) ฟังก์ชัน clear_all_and_restart (รวม 2 เวอร์ชัน) ---
def clear_all_and_restart():
    """ล้างทุกอย่างและเริ่มใหม่ทั้งหมด"""
    # (จาก Bulk)
    st.session_state.current_user = ""
    st.session_state.staged_scans = []
    st.session_state.scanner_key = f"scanner_{uuid.uuid4()}" 
    st.session_state.last_scan_processed = ""
    st.session_state.show_user_not_found_error = False
    st.session_state.last_failed_user_scan = ""
    # (จาก Single)
    st.session_state.temp_tracking = ""
    st.session_state.temp_barcode = ""
    st.session_state.show_dialog_for = None 
    st.session_state.show_scan_error_message = False
    st.rerun() # (เพิ่ม Rerun)

# --- 🟢 (เพิ่ม) ฟังก์ชัน validate_and_lock_user ---
def validate_and_lock_user(user_id_to_check):
    """ตรวจสอบ User ID กับ DB และล็อคค่าถ้าถูกต้อง"""
    if not user_id_to_check:
        return False
    try:
        query = "SELECT COUNT(1) as count FROM user_data WHERE user_id = :user_id"
        params = {"user_id": user_id_to_check}
        result_df = supabase_conn.query(query, params=params, ttl=60) 
        
        if not result_df.empty and result_df['count'][0] > 0:
            st.session_state.current_user = user_id_to_check
            st.success(f"User: {user_id_to_check} ถูกล็อคแล้ว")
            st.session_state.show_user_not_found_error = False
            return True
        else:
            st.session_state.show_user_not_found_error = True
            st.session_state.last_failed_user_scan = user_id_to_check
            return False
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการตรวจสอบ User: {e}")
        st.session_state.show_user_not_found_error = False 
        return False

# --- (ฟังก์ชันเดิมจาก Single) ---
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

# --- 🟢 (แก้ไข) ฟังก์ชัน save_all_to_db ---
def save_all_to_db():
    if not st.session_state.staged_scans:
        st.warning("ไม่มีข้อมูลในรายการให้บันทึก")
        return
    # (เพิ่มการตรวจสอบ User/Barcode ก่อนบันทึก)
    if not st.session_state.current_user:
        st.error("ไม่พบชื่อผู้ใช้งาน! กรุณาเริ่มใหม่")
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
        
        # (ใช้วิธีบันทึกแบบ .session ที่เสถียรกว่า)
        with supabase_conn.session as session:
            df_to_insert.to_sql(
                "scans", 
                con=session.connection(),
                if_exists="append", 
                index=False
            )
            session.commit()
        
        saved_count = len(st.session_state.staged_scans)
        st.session_state.scan_count += saved_count
        st.success(f"บันทึกข้อมูลทั้ง {saved_count} รายการ สำเร็จ!")
        
        clear_all_and_restart() # (เรียกใช้ฟังก์ชันล้างค่าใหม่)
        # (st.rerun() ถูกย้ายไปอยู่ใน clear_all_and_restart)
        
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการบันทึก: {e}")

# --- Dialog Function (เหมือนเดิม) ---
@st.dialog("✅ สแกนสำเร็จ")
def show_confirmation_dialog(is_tracking):
    code_type = "Tracking Number" if is_tracking else "Barcode สินค้า"
    code_value = st.session_state.temp_tracking if is_tracking else st.session_state.temp_barcode
    st.info(f"ยืนยัน {code_type} ที่สแกนได้:")
    st.code(code_value)
    if is_tracking:
        st.warning("ขั้นต่อไป: กด 'ปิด' แล้วสแกน Barcode")
        if st.button("ปิด (และเตรียมสแกน Barcode)"):
            st.session_state.show_dialog_for = None
            st.rerun()
    else: # Barcode
        st.success("Barcode ถูกสแกนและยืนยันแล้ว!")
        st.warning("ข้อมูลจะถูกเพิ่มลงในรายการทันที")
        if st.button("ปิด (และเพิ่มลงในรายการ)"):
            add_and_clear_staging()

# --- 4. แบ่งหน้าจอด้วย Tabs ---
tab1, tab2 = st.tabs(["📷 สแกนกล่อง", "📊 ดูข้อมูลและดาวน์โหลด"])

# --- TAB 1: หน้าสแกน (ปรับ Layout) ---
with tab1:
    st.header("บันทึกการสแกน")
    
    # (ย้าย Metric มาไว้บนสุด)
    st.metric("กล่องที่บันทึกไปแล้ว (รอบนี้)", st.session_state.scan_count)
    st.divider()

    # --- 🟢 (เพิ่ม) Logic การสแกน/ล็อค User ---
    
    # (ใช้ scanner ร่วม)
    scanner_prompt_placeholder = st.empty() 
    scan_value = qrcode_scanner(key=st.session_state.scanner_key)

    # (ประมวลผลการสแกน)
    is_new_scan = (scan_value is not None) and (scan_value != st.session_state.last_scan_processed)

    if not st.session_state.current_user:
        # --- (ส่วนที่ 1: ยังไม่มี User) ---
        
        # (แสดง Expander สำหรับคีย์ User)
        with st.expander("คีย์ User ID (กรณีสแกนไม่ได้)"):
            with st.form(key="manual_user_form"):
                manual_user_id = st.text_input("ป้อน User ID:")
                manual_user_submit = st.form_submit_button("ล็อค User")

            if manual_user_submit:
                if manual_user_id:
                    if validate_and_lock_user(manual_user_id):
                        st.session_state.last_scan_processed = manual_user_id 
                        st.rerun() 
                else:
                    st.warning("กรุณาป้อน User ID")
        
        # (ประมวลผลการสแกน User)
        if is_new_scan:
            st.session_state.last_scan_processed = scan_value
            if validate_and_lock_user(scan_value):
                st.rerun()
        
        # (แสดงข้อความแนะนำ)
        if st.session_state.show_user_not_found_error:
            scanner_prompt_placeholder.error(f"⚠️ ไม่พบ User '{st.session_state.last_failed_user_scan}'! กรุณาสแกน User ที่ถูกต้อง", icon="⚠️")
        else:
            scanner_prompt_placeholder.info("ขั้นตอนที่ 1: สแกน 'ชื่อผู้ใช้งาน' (หรือคีย์ด้านล่าง)")

    else:
        # --- (ส่วนที่ 2: มี User แล้ว) ---
        # (แสดงข้อมูล User และปุ่มล้างค่า)
        st.subheader("ผู้ใช้งาน (User)")
        st.code(st.session_state.current_user)
        st.button("❌ เปลี่ยน User (และเริ่มใหม่)", on_click=clear_all_and_restart)
        st.divider()
        
        # --- ( Logic การสแกนเดิมของ Single_version) ---

        if st.session_state.get("show_scan_error_message", False):
            st.error("⚠️ สแกนซ้ำ! กรุณาสแกน Barcode", icon="⚠️")

        if st.session_state.show_dialog_for == 'tracking':
             show_confirmation_dialog(is_tracking=True)
        elif st.session_state.show_dialog_for == 'barcode':
             show_confirmation_dialog(is_tracking=False)
             
        st.subheader("1. สแกนที่นี่ (Scan Here)")
        
        if st.session_state.show_dialog_for is None:
            # (อัปเดตข้อความ Prompt)
            if not st.session_state.temp_tracking:
                scanner_prompt_placeholder.info("ขั้นตอนที่ 2: สแกน Tracking...")
            elif not st.session_state.temp_barcode:
                 if not st.session_state.show_scan_error_message:
                     scanner_prompt_placeholder.success("ขั้นตอนที่ 3: สแกน Barcode...")
                 else:
                     scanner_prompt_placeholder.error("⚠️ สแกนซ้ำ! กรุณาสแกน Barcode", icon="⚠️")
            else:
                 # (สถานะนี้คือ สแกน Barcode สำเร็จ)
                 add_and_clear_staging() # (ย้าย add_and_clear_staging มาที่นี่)

            if is_new_scan:
                st.session_state.last_scan_processed = scan_value
                
                # Logic 1: สแกน Tracking
                if not st.session_state.temp_tracking:
                    if scan_value == st.session_state.current_user:
                        st.warning("⚠️ นั่นคือ User! กรุณาสแกน Tracking", icon="⚠️")
                    else:
                        st.session_state.temp_tracking = scan_value
                        st.session_state.show_dialog_for = 'tracking' 
                        st.rerun() 
                
                # Logic 2: สแกน Barcode
                elif st.session_state.temp_tracking and not st.session_state.temp_barcode:
                    if scan_value != st.session_state.temp_tracking and scan_value != st.session_state.current_user:
                        st.session_state.temp_barcode = scan_value
                        st.session_state.show_dialog_for = 'barcode' 
                        st.session_state.show_scan_error_message = False 
                        st.rerun() 
                    else:
                        st.session_state.show_scan_error_message = True
                        st.rerun()
                        
                elif st.session_state.temp_tracking and st.session_state.temp_barcode:
                    st.warning("รอสักครู่ (ระบบกำลังเพิ่มรายการ) หรือเริ่มสแกน Tracking ถัดไปได้เลย")
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

        st.button("💾 บันทึกทั้งหมด",
                  type="primary",
                  use_container_width=True,
                  on_click=save_all_to_db,
                  disabled=(not st.session_state.staged_scans)
                 )

        st.subheader(f"3. รายการที่กำลังสแกน ({len(st.session_state.staged_scans)} รายการ)")
        
        if not st.session_state.staged_scans:
            st.info("ยังไม่มีรายการสแกน สแกน Tracking และ Barcode")
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
            # (แก้ไข) เปลี่ยนชื่อตัวแปรเป็น filter_date (เหมือนใน query)
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
