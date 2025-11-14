import streamlit as st
import pandas as pd
from datetime import datetime
from streamlit.connections import SQLConnection
from streamlit_qrcode_scanner import qrcode_scanner
import uuid
import pytz
from sqlalchemy import text
import numpy as np

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
if "temp_barcode" not in st.session_state:
    st.session_state.temp_barcode = "" 
if "staged_scans" not in st.session_state:
    st.session_state.staged_scans = [] 
if "show_duplicate_tracking_error" not in st.session_state:
    st.session_state.show_duplicate_tracking_error = False 
if "last_scanned_tracking" not in st.session_state:
    st.session_state.last_scanned_tracking = "" 
if "scanner_key" not in st.session_state:
    st.session_state.scanner_key = "scanner_v1"
if "last_scan_processed" not in st.session_state:
    st.session_state.last_scan_processed = ""
if "show_user_not_found_error" not in st.session_state:
    st.session_state.show_user_not_found_error = False
if "last_failed_user_scan" not in st.session_state:
    st.session_state.last_failed_user_scan = ""
if "selected_user_to_edit" not in st.session_state:
    st.session_state.selected_user_to_edit = None
# --- 🟢 สิ้นสุด 🟢 ---

# --- 3. สร้างฟังก์ชันสำหรับปุ่ม (Callbacks) ---

def delete_item(item_id_to_delete):
    """ลบรายการเดียวออกจาก Staging list"""
    st.session_state.staged_scans = [
        item for item in st.session_state.staged_scans 
        if item["id"] != item_id_to_delete
    ]

def clear_all_and_restart():
    """ล้างทุกอย่างและเริ่มใหม่ทั้งหมด (User, Barcode, Staging)"""
    st.session_state.current_user = ""
    st.session_state.temp_barcode = ""
    st.session_state.staged_scans = []
    st.session_state.show_duplicate_tracking_error = False
    st.session_state.last_scanned_tracking = ""
    st.session_state.scanner_key = f"scanner_{uuid.uuid4()}" # บังคับสร้างกล้องใหม่
    st.session_state.last_scan_processed = ""
    st.session_state.show_user_not_found_error = False
    st.session_state.last_failed_user_scan = ""

# --- 🟢 (ใหม่) เพิ่มฟังก์ชันที่หายไป ---
def acknowledge_error_and_reset_scanner():
    """(ใหม่) เคลียร์ Error (User/Tracking ซ้ำ) และรีเซ็ตกล้อง"""
    # ล้างธง Error ทั้งหมด
    st.session_state.show_user_not_found_error = False
    st.session_state.last_failed_user_scan = ""
    st.session_state.show_duplicate_tracking_error = False
    st.session_state.last_scanned_tracking = ""
    
    # (สำคัญ) รีเซ็ตกล้องเพื่อล้างค่าที่ "ค้าง"
    st.session_state.scanner_key = f"scanner_{uuid.uuid4()}"
    st.session_state.last_scan_processed = ""
# --- 🟢 (สิ้นสุด) ---

# --- 🟢 (แก้ไข) ย้ายฟังก์ชันนี้ออกมาให้อยู่ระดับบนสุด ---
def validate_and_lock_user(user_id_to_check):
    """(ใหม่) ตรวจสอบ User ID กับ DB และล็อคค่าถ้าถูกต้อง"""
    if not user_id_to_check:
        return False
        
    try:
        # 1. ค้นหา User
        query = "SELECT COUNT(1) as count FROM user_data WHERE user_id = :user_id"
        params = {"user_id": user_id_to_check}
        result_df = supabase_conn.query(query, params=params, ttl=60) 
        
        if not result_df.empty and result_df['count'][0] > 0:
            # 2. ถ้าเจอ: ล็อค User และล้าง Error (ถ้ามี)
            st.session_state.current_user = user_id_to_check
            st.success(f"User: {user_id_to_check} ถูกล็อคแล้ว")
            st.session_state.show_user_not_found_error = False
            return True
        else:
            # 3. ถ้าไม่เจอ: ตั้งค่า Error (ไม่ล็อค User)
            st.session_state.show_user_not_found_error = True
            st.session_state.last_failed_user_scan = user_id_to_check
            return False
            
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการตรวจสอบ User: {e}")
        st.session_state.show_user_not_found_error = False 
        return False

# --- 🟢 (แก้ไข) แก้ไขโครงสร้างฟังก์ชัน save_all_to_db ---
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
    
    # (ย้าย Logic การบันทึกมาไว้ใน try...except ที่ถูกต้อง)
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
        
        st.success(f"บันทึกข้อมูลทั้ง {saved_count} รายการ สำเร็จ!")
        
        # เรียกใช้ฟังก์ชันล้างค่า
        clear_all_and_restart()
        
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการบันทึก: {e}")

# --- 4. แบ่งหน้าจอด้วย Tabs ---
tab1, tab2 = st.tabs(["📷 สแกนกล่อง", "📊 ดูข้อมูลและดาวน์โหลด"])

# --- TAB 1: หน้าสแกน (เพิ่มปุ่มเคลียร์ Error) ---
with tab1:
    st.header("บันทึกการสแกน") 

    # --- ส่วนที่ 1: กล้องสแกน และ ข้อความแนะนำ (Dynamic) ---
    scanner_prompt_placeholder = st.empty() 
    scan_value = qrcode_scanner(key=st.session_state.scanner_key)

    # --- (ส่วนการคีย์ Manual - เหมือนเดิม) ---
    if not st.session_state.current_user: 
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

    # --- ส่วนที่ 2: Logic ประมวลผลการสแกน (เหมือนเดิม) ---
    is_new_scan = (scan_value is not None) and (scan_value != st.session_state.last_scan_processed)
    
    if is_new_scan:
        st.session_state.last_scan_processed = scan_value 
        
        # 2A: State 1: ยังไม่มี User
        if not st.session_state.current_user:
            validate_and_lock_user(scan_value)

        # 2B: State 2: มี User, ไม่มี Barcode
        elif not st.session_state.temp_barcode:
            st.session_state.show_user_not_found_error = False 
            if scan_value == st.session_state.current_user:
                st.warning("⚠️ นั่นคือ User! กรุณาสแกน Barcode สินค้า", icon="⚠️")
            else:
                st.session_state.temp_barcode = scan_value
                st.success(f"Barcode: {scan_value} ถูกล็อคแล้ว")

        # 2C: State 3: มี User และ Barcode
        else:
            st.session_state.show_user_not_found_error = False 
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

    # --- ส่วนที่ 3: อัปเดตข้อความแนะนำ และ "ปุ่มเคลียร์" ---
    
    # (ตรวจสอบว่ามี Error ค้างหรือไม่)
    has_sticky_error = st.session_state.show_user_not_found_error or st.session_state.show_duplicate_tracking_error

    if not st.session_state.current_user:
        if st.session_state.show_user_not_found_error:
            scanner_prompt_placeholder.error(f"⚠️ ไม่พบ User '{st.session_state.last_failed_user_scan}' ในระบบ! กรุณาสแกน User หรือคีย์ User ที่ถูกต้อง", icon="⚠️")
        else:
            scanner_prompt_placeholder.info("ขั้นตอนที่ 1: สแกน 'ชื่อผู้ใช้งาน' (หรือคีย์ด้านล่าง)")
        
    elif not st.session_state.temp_barcode:
        scanner_prompt_placeholder.info("ขั้นตอนที่ 2: สแกน Barcode สินค้า...")
    else:
        if st.session_state.show_duplicate_tracking_error:
            scanner_prompt_placeholder.error(f"⚠️ สแกนซ้ำ! '{st.session_state.last_scanned_tracking}' มีในรายการแล้ว กรุณาสแกน Tracking ถัดไป...", icon="⚠️")
        else:
            scanner_prompt_placeholder.info("ขั้นตอนที่ 3: สแกน Tracking Number ทีละกล่อง...")

    # --- 🟢 (ใหม่) เพิ่มปุ่มเคลียร์ Error ---
    if has_sticky_error:
        st.button("❌ ปิดแจ้งเตือน (และสแกนใหม่)", 
                  on_click=acknowledge_error_and_reset_scanner, 
                  use_container_width=True,
                  type="primary") # (ใช้สีแดงให้เด่น)
    # --- 🟢 (สิ้นสุด) ---

    # --- ส่วนที่ 4: แสดงผล (Display Area) ---
    st.divider()
    st.subheader("1. ผู้ใช้งาน (User)")
    if st.session_state.current_user:
        st.code(st.session_state.current_user)
        st.button("❌ เปลี่ยน User (และเริ่มใหม่)", on_click=clear_all_and_restart)
    else:
        st.info("...รอล็อค User...")
    
    if st.session_state.current_user:
        st.divider()
        st.subheader("2. Barcode ที่ล็อคอยู่")
        if st.session_state.temp_barcode:
            st.code(st.session_state.temp_barcode)
        else:
            st.info("...รอล็อค Barcode...")
        
        st.divider()

        # --- ส่วนที่ 5: ปุ่มบันทึก และ รายการที่กำลังสแกน ---
        st.button("💾 บันทึกทั้งหมด (และเริ่มใหม่)",
                  type="primary",
                  use_container_width=True,
                  on_click=save_all_to_db,
                  disabled=(not st.session_state.staged_scans or not st.session_state.temp_barcode or not st.session_state.current_user)
                 )

        st.subheader(f"3. รายการที่กำลังสแกน ({len(st.session_state.staged_scans)} รายการ)")
        
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
                        
# --- TAB 2: หน้าดูข้อมูลและดาวน์โหลด (แก้ไข Expander ให้ซ่อน) ---
with tab2:
    st.header("จัดการข้อมูล User")

    # --- (ดึงข้อมูล User ทั้งหมดสำหรับ Dropdown) ---
    @st.cache_data(ttl=60) 
    def get_all_users():
        try:
            query = 'SELECT user_id, "Employee_Name", "Employee_Surname" FROM user_data ORDER BY user_id'
            df = supabase_conn.query(query)
            return df
        except Exception as e:
            st.error(f"ไม่สามารถดึงข้อมูล User: {e}")
            return pd.DataFrame(columns=["user_id", "Employee_Name", "Employee_Surname"])

    user_df = get_all_users()
    
    user_df["Employee_Name"] = user_df["Employee_Name"].fillna("").astype(str)
    user_df["Employee_Surname"] = user_df["Employee_Surname"].fillna("").astype(str)
    
    user_id_list = ["(เลือก User เพื่อ แก้ไข/ลบ)", "--- เพิ่ม User ใหม่ ---"] + user_df["user_id"].tolist()

    # --- (ฟังก์ชันสำหรับปุ่ม "New") ---
    def clear_user_form():
        st.session_state.selected_user_to_edit = "(เลือก User เพื่อ แก้ไข/ลบ)"
        st.session_state.user_id_input = ""
        st.session_state.emp_name_input = ""
        st.session_state.emp_surname_input = ""

    # --- (ฟังก์ชันสำหรับอัปเดต Form เมื่อ Dropdown เปลี่ยน) ---
    def on_user_select():
        selected_id = st.session_state.selected_user_to_edit
        
        if selected_id == "--- เพิ่ม User ใหม่ ---":
            st.session_state.user_id_input = ""
            st.session_state.emp_name_input = ""
            st.session_state.emp_surname_input = ""
        elif selected_id != "(เลือก User เพื่อ แก้ไข/ลบ)":
            user_data = user_df[user_df["user_id"] == selected_id].iloc[0]
            st.session_state.user_id_input = user_data["user_id"]
            st.session_state.emp_name_input = user_data["Employee_Name"]
            st.session_state.emp_surname_input = user_data["Employee_Surname"]
        else:
            # (ถ้าเลือก "(เลือก User...)" ให้ล้างฟอร์ม)
            st.session_state.user_id_input = ""
            st.session_state.emp_name_input = ""
            st.session_state.emp_surname_input = ""

    # --- UI ส่วนที่ 1: Form จัดการ User ---
    
    # --- 🟢 (แก้ไข) เปลี่ยน expanded=True เป็น expanded=False ---
    with st.expander("คลิกเพื่อเปิดฟอร์ม จัดการ User", expanded=False):
    # --- 🟢 สิ้นสุด 🟢 ---
        
        st.selectbox(
            "เลือก User (เพื่อ แก้ไข/ลบ) หรือเลือก 'เพิ่ม User ใหม่'",
            options=user_id_list,
            key="selected_user_to_edit",
            on_change=on_user_select
        )

        with st.form(key="user_management_form"):
            
            is_new_mode = st.session_state.selected_user_to_edit == "--- เพิ่ม User ใหม่ ---"
            
            user_id = st.text_input("User ID (จำเป็น)", key="user_id_input", disabled=(not is_new_mode))
            emp_name = st.text_input("Employee Name (ชื่อจริง)", key="emp_name_input")
            emp_surname = st.text_input("Employee Surname (นามสกุล)", key="emp_surname_input")

            col_b1, col_b2, col_b3 = st.columns([2, 2, 1])

            with col_b1:
                save_label = "💾 บันทึก User ใหม่" if is_new_mode else "💾 อัปเดต User"
                save_button = st.form_submit_button(save_label, use_container_width=True)
            
            with col_b2:
                delete_button = st.form_submit_button("❌ ลบ User นี้", use_container_width=True, disabled=is_new_mode)
            
            with col_b3:
                st.form_submit_button("🆕", on_click=clear_user_form, use_container_width=True, help="ล้างฟอร์มและเริ่มใหม่")

            # --- Logic การประมวลผลเมื่อกดปุ่ม ---
            
            # 3A. Logic ปุ่ม "บันทึก" (Save / Update)
            if save_button:
                if not user_id:
                    st.error("กรุณาป้อน User ID")
                else:
                    try:
                        with supabase_conn.session as session:
                            if is_new_mode:
                                # (โหมด "สร้างใหม่")
                                check_query = "SELECT COUNT(1) as count FROM user_data WHERE user_id = :user_id"
                                check_df = supabase_conn.query(check_query, params={"user_id": user_id}, ttl=5)
                                if not check_df.empty and check_df['count'][0] > 0:
                                    st.error(f"⚠️ User ID '{user_id}' นี้มีในระบบแล้ว! ไม่สามารถเพิ่มซ้ำได้")
                                else:
                                    insert_query = text("""
                                        INSERT INTO user_data (user_id, "Employee_Name", "Employee_Surname")
                                        VALUES (:user_id, :name, :surname)
                                    """)
                                    session.execute(insert_query, {"user_id": user_id, "name": emp_name, "surname": emp_surname})
                                    session.commit()
                                    st.success(f"บันทึก User '{user_id}' สำเร็จ!")
                                    st.cache_data.clear() 
                                    st.rerun() 
                            else:
                                # (โหมด "แก้ไข")
                                update_query = text("""
                                    UPDATE user_data
                                    SET "Employee_Name" = :name, "Employee_Surname" = :surname
                                    WHERE user_id = :user_id
                                """)
                                session.execute(update_query, {"user_id": user_id, "name": emp_name, "surname": emp_surname})
                                session.commit()
                                st.success(f"อัปเดต User '{user_id}' สำเร็จ!")
                                st.cache_data.clear()
                                st.rerun()
                                
                    except Exception as e:
                        st.error(f"เกิดข้อผิดพลาด: {e}")

            # 3B. Logic ปุ่ม "ลบ" (Delete)
            if delete_button:
                if not user_id:
                    st.error("ไม่ได้เลือก User ที่จะลบ")
                else:
                    try:
                        with supabase_conn.session as session:
                            delete_query = text("DELETE FROM user_data WHERE user_id = :user_id")
                            session.execute(delete_query, {"user_id": user_id})
                            session.commit()
                            st.warning(f"ลบ User '{user_id}' ออกจากระบบแล้ว!")
                            st.cache_data.clear()
                            st.rerun() 
                            
                    except Exception as e:
                        st.error(f"เกิดข้อผิดพลาดในการลบ: {e}")

    # --- (สิ้นสุด Form จัดการ User) ---

    st.divider() 
    
    # --- (ส่วนที่ 2: ค้นหาข้อมูลที่สแกนแล้ว) ---
    st.header("ค้นหาข้อมูลที่สแกนแล้ว")
    
    show_error = False 
    
    with st.expander("ตัวกรองข้อมูล (Filter)", expanded=True):
        col_f1, col_col2 = st.columns(2)
        with col_f1:
            filter_user = st.text_input("กรองตาม User (เว้นว่างเพื่อแสดงทั้งหมด)")
        
        with col_col2:
            sub_col1, sub_col2 = st.columns(2)
            with sub_col1:
                start_date = st.date_input("From (จากวันที่)", value=None)
            with sub_col2:
                end_date = st.date_input("To (ถึงวันที่)", value=None)
        
        if start_date and end_date and start_date > end_date:
            st.error("วันที่เริ่มต้น (From) ต้องมาก่อนวันที่สิ้นสุด (To)")
            show_error = True 

    st.metric("กล่องที่บันทึกไปแล้ว (รอบนี้)", st.session_state.scan_count)
    st.divider()

    try:
        query = "SELECT * FROM scans" 
        filters = []
        params = {}
        if filter_user:
            filters.append("user_id = :user")
            params["user"] = filter_user
        
        if not show_error: 
            if start_date and end_date:
                filters.append("DATE(created_at AT TIME ZONE 'Asia/Bangkok') BETWEEN :start AND :end")
                params["start"] = start_date
                params["end"] = end_date
            elif start_date:
                filters.append("DATE(created_at AT TIME ZONE 'Asia/Bangkok') >= :start")
                params["start"] = start_date
            elif end_date:
                filters.append("DATE(created_at AT TIME ZONE 'Asia/Bangkok') <= :end")
                params["end"] = end_date
            
        if filters:
            query += " WHERE " + " AND ".join(filters)
        
        query += " ORDER BY created_at DESC"
        
        if show_error:
            data_df = pd.DataFrame() 
        else:
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
            if not show_error:
                st.info("ไม่พบข้อมูลตามเงื่อนไขที่เลือก")
            
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการดึงข้อมูล: {e}")
