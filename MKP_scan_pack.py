import streamlit as st
import pandas as pd
from datetime import datetime
from streamlit.connections import SQLConnection
from streamlit_qrcode_scanner import qrcode_scanner
import uuid
import pytz
from sqlalchemy import text
import numpy as np

# --- (CSS สำหรับ Mobile Layout - อัปเดต) ---
st.markdown("""
<style>
/* 1. Base Layout */
div.block-container {
    padding-top: 1rem; padding-bottom: 1rem;
    padding-left: 1rem; padding-right: 1rem;
}
/* 2. Headers */
h1 { font-size: 1.8rem !important; margin-bottom: 0.5rem; }

/* 3. h3 (subheader) */
div[data-testid="stTabs-panel-0"] > div[data-testid="stVerticalBlock"] > div[data-testid="stHorizontalBlock"] h3 { 
    font-size: 0.5rem !important; 
    margin-top: 0.25rem; 
    margin-bottom: 0.5rem; 
}

/* 4. Metric */
[data-testid="stMetric"] {
    padding-top: 0 !important; background-color: #FAFAFA;
    border-radius: 0.25rem; padding: 0.25rem 1rem !important;
}
[data-testid="stMetricValue"] { font-size: 0.9rem !important; }
[data-testid="stMetricLabel"] { font-size: 0.9rem !important; }

/* 5. Staging Card Container */
[data-testid="stVerticalBlock"] > [data-testid="stContainer"] {
    border: 1px solid #BBBBBB !important; 
    border-radius: 0.5rem;
    padding: 0.5rem 0.75rem !important; 
    margin-bottom: 0.5rem; 
}
/* 6. Code Box */
.stCode { 
    font-size: 0.75rem !important; 
    padding: 0.4em !important; 
}
/* 7. ปุ่ม "ลบ" */
div[data-testid="stHorizontalBlock"] > div:nth-child(2) .stButton button {
    font-size: 0.8rem !important; 
    padding: 0.4em 0.5em !important; 
    height: 2.8em !important; 
}

/* 8. บังคับ Columns ให้อยู่ข้างกัน */
@media (max-width: 640px) {
    div[data-testid="stTabs-panel-0"] > div[data-testid="stVerticalBlock"] > div[data-testid="stHorizontalBlock"] {
        grid-template-columns: 1fr 1fr !important; 
        gap: 0.75rem !important; 
    }
}

/* --- 🟢 (แก้ไข) 9. ลดขนาดตัวอักษร (เจาะจงมากขึ้น) --- */

/* (เป้าหมายที่ 1: Header "บันทึกการสแกน...") */
/* (เลือก h2 ที่อยู่ใน Tab 1) */
div[data-testid="stTabs-panel-0"] [data-testid="stVerticalBlock"] h2 {
    font-size: 0.5rem !important; 
    margin-bottom: 0.5rem !important;
    line-height: 0.5 !important; 
}

/* (เป้าหมายที่ 2: Prompt "ขั้นตอนที่ 1...") */
/* (เลือก Info/Error ที่อยู่ใน Tab 1) */
div[data-testid="stTabs-panel-0"] [data-testid="stInfo"],
div[data-testid="stTabs-panel-0"] [data-testid="stError"] {
    font-size: 0.85rem !important;
    padding: 0.6rem 0.75rem !important;
}

</style>
""", unsafe_allow_html=True)
# --- จบ Custom CSS ---

# --- 1. ตั้งค่าหน้าจอและเชื่อมต่อ Supabase ---
st.set_page_config(page_title="Box Scanner", layout="wide")
st.title("📦 สแกนแปะ Tracking")

@st.cache_resource
def init_supabase_connection():
    return st.connection("supabase", type=SQLConnection)

supabase_conn = init_supabase_connection()

# --- 2. สร้าง Session State (รวม 2 เวอร์ชัน) ---
if "current_user" not in st.session_state:
    st.session_state.current_user = ""
if "scan_count" not in st.session_state:
    st.session_state.scan_count = 0 
if "staged_scans" not in st.session_state:
    st.session_state.staged_scans = [] 
if "scanner_key" not in st.session_state:
    st.session_state.scanner_key = "scanner_v1"
if "last_scan_processed" not in st.session_state:
    st.session_state.last_scan_processed = ""

# (State จาก Bulk)
if "temp_barcode" not in st.session_state:
    st.session_state.temp_barcode = "" 
if "show_duplicate_tracking_error" not in st.session_state:
    st.session_state.show_duplicate_tracking_error = False 
if "last_scanned_tracking" not in st.session_state:
    st.session_state.last_scanned_tracking = "" 
if "show_user_not_found_error" not in st.session_state:
    st.session_state.show_user_not_found_error = False
if "last_failed_user_scan" not in st.session_state:
    st.session_state.last_failed_user_scan = ""
if "selected_user_to_edit" not in st.session_state:
    st.session_state.selected_user_to_edit = None

# --- 🟢 (ใหม่) State สำหรับเลือกโหมด ---
if "scan_mode" not in st.session_state:
    st.session_state.scan_mode = None # (None, "Bulk", "Single")

# (State จาก Single)
if "temp_tracking" not in st.session_state:
    st.session_state.temp_tracking = ""
if "show_dialog_for" not in st.session_state:
    st.session_state.show_dialog_for = None 
if "show_scan_error_message" not in st.session_state:
    st.session_state.show_scan_error_message = False
# --- 🟢 สิ้นสุด 🟢 ---

# --- 3. สร้างฟังก์ชันสำหรับปุ่ม (Callbacks) ---

def delete_item(item_id_to_delete):
    """ลบรายการเดียวออกจาก Staging list"""
    st.session_state.staged_scans = [
        item for item in st.session_state.staged_scans 
        if item["id"] != item_id_to_delete
    ]

# --- 🟢 (ใหม่) ฟังก์ชันเลือกโหมด ---
def set_scan_mode(mode):
    st.session_state.scan_mode = mode

# --- 🟢 (แก้ไข) clear_all_and_restart (รวมทุก State) ---
def clear_all_and_restart():
    """ล้างทุกอย่างและเริ่มใหม่ทั้งหมด"""
    st.session_state.current_user = ""
    st.session_state.staged_scans = []
    st.session_state.scanner_key = f"scanner_{uuid.uuid4()}" 
    st.session_state.last_scan_processed = ""
    st.session_state.show_user_not_found_error = False
    st.session_state.last_failed_user_scan = ""
    
    # (Bulk)
    st.session_state.temp_barcode = ""
    st.session_state.show_duplicate_tracking_error = False
    st.session_state.last_scanned_tracking = ""
    
    # (Single)
    st.session_state.temp_tracking = ""
    st.session_state.show_dialog_for = None 
    st.session_state.show_scan_error_message = False

    # (Mode)
    st.session_state.scan_mode = None # <-- (สำคัญ) กลับไปหน้าเลือกโหมด
    
    # (ไม่ต้อง st.rerun() เพราะจะถูกเรียกตอนกดปุ่ม)

def acknowledge_error_and_reset_scanner():
    """(Bulk) เคลียร์ Error (User/Tracking ซ้ำ) และรีเซ็ตกล้อง"""
    st.session_state.show_user_not_found_error = False
    st.session_state.last_failed_user_scan = ""
    st.session_state.show_duplicate_tracking_error = False
    st.session_state.last_scanned_tracking = ""
    
    st.session_state.scanner_key = f"scanner_{uuid.uuid4()}"
    st.session_state.last_scan_processed = ""

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

# --- 🟢 (เพิ่ม) ฟังก์ชันจาก Single_version ---
def add_and_clear_staging():
    """(Single) เพิ่มรายการและล้างค่า staging"""
    if st.session_state.temp_tracking and st.session_state.temp_barcode:
        st.session_state.staged_scans.append({
            "id": str(uuid.uuid4()),
            "tracking": st.session_state.temp_tracking,
            "barcode": st.session_state.temp_barcode
        })
        st.session_state.temp_tracking = ""
        st.session_state.temp_barcode = "" # <-- (แก้ไข) ล้าง barcode ด้วย
        st.session_state.show_dialog_for = None 
    st.rerun() 

# --- 🟢 (เพิ่ม) Dialog Function (จาก Single) ---
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
            # (ไม่เรียก add_and_clear_staging() ที่นี่)
            st.session_state.show_dialog_for = 'staging' # (ตั้งสถานะใหม่)
            st.rerun()


# --- (ฟังก์ชัน save_all_to_db จาก Bulk_version - ใช้ร่วมกันได้) ---
def save_all_to_db():
    """บันทึก Staging list ทั้งหมดลง Database"""
    if not st.session_state.staged_scans:
        st.warning("ไม่มีข้อมูลในรายการให้บันทึก")
        return
    if not st.session_state.current_user:
         st.error("ไม่พบชื่อผู้ใช้งาน! กรุณาป้อนชื่อผู้ใช้งาน")
         return
    
    # (เพิ่มเงื่อนไขตรวจสอบสำหรับ Bulk mode)
    if st.session_state.scan_mode == "Bulk" and not st.session_state.temp_barcode:
         st.error("ไม่พบ Barcode! (เกิดข้อผิดพลาด) กรุณาล้างและสแกนใหม่")
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
        
        # (ล้างค่าและกลับไปหน้าเลือกโหมด)
        clear_all_and_restart()
        
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการบันทึก: {e}")

# --- 4. แบ่งหน้าจอด้วย Tabs ---
tab1, tab2 = st.tabs(["📷 สแกนกล่อง", "📊 ดูข้อมูลและดาวน์โหลด"])

# --- TAB 1: หน้าสแกน (เพิ่มปุ่ม "กลับ Menu") ---
with tab1:
    
    # --- 🟢 (Phase 1: Mode Selection - เหมือนเดิม) ---
    if st.session_state.scan_mode is None:
        st.header("เลือก Menu")
        st.button("โหมด Bulk (1 Barcode ➔ หลาย Trackings)", on_click=set_scan_mode, args=("Bulk",), use_container_width=True, type="primary")
        st.button("โหมด Single (1 Tracking ➔ 1 Barcode)", on_click=set_scan_mode, args=("Single",), use_container_width=True)
        
        st.divider()
        st.metric("กล่องที่บันทึกไปแล้ว (รอบนี้)", st.session_state.scan_count)
        if st.session_state.scan_count > 0:
            if st.button("ล้าง Scan Count"):
                st.session_state.scan_count = 0
                st.rerun()

    # --- 🟢 (Phase 2: User Validation - เพิ่มปุ่ม "กลับ") ---
    elif st.session_state.scan_mode is not None and not st.session_state.current_user:
        
        mode_name = "โหมด Bulk" if st.session_state.scan_mode == "Bulk" else "โหมด Single"
        st.header(f"{mode_name}")
        
        scanner_prompt_placeholder = st.empty() 
        scan_value = qrcode_scanner(key=st.session_state.scanner_key)
        
        # --- (ปุ่ม "กลับ" จุดที่ 1) ---
        st.button("🔙 กลับ Menu หลัก", on_click=clear_all_and_restart, key="back_menu_1")

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

        is_new_scan = (scan_value is not None) and (scan_value != st.session_state.last_scan_processed)
        if is_new_scan:
            st.session_state.last_scan_processed = scan_value 
            if validate_and_lock_user(scan_value):
                st.rerun()

        if st.session_state.show_user_not_found_error:
            scanner_prompt_placeholder.error(f"⚠️ ไม่พบ User '{st.session_state.last_failed_user_scan}'! กรุณาสแกน User ที่ถูกต้อง", icon="⚠️")
        else:
            scanner_prompt_placeholder.info("ขั้นตอนที่ 1: สแกน 'ชื่อผู้ใช้งาน' (หรือคีย์ด้านล่าง)")

    # --- 🟢 (Phase 3: Mode-Specific Scanning) ---
    else:
        
        # --- 🔵 (Logic จาก Bulk_version - เพิ่มปุ่ม "กลับ") 🔵 ---
        if st.session_state.scan_mode == "Bulk":
            
            mode_name = "โหมด Bulk" # (เพิ่ม)
            st.header(f"{mode_name}") # (เพิ่ม)

            scanner_prompt_placeholder = st.empty() 
            scan_value = qrcode_scanner(key=st.session_state.scanner_key)
            
            # --- (ปุ่ม "กลับ" จุดที่ 2) ---
            st.button("🔙 กลับ Menu หลัก", on_click=clear_all_and_restart, key="back_menu_bulk")

            is_new_scan = (scan_value is not None) and (scan_value != st.session_state.last_scan_processed)
            if is_new_scan:
                st.session_state.last_scan_processed = scan_value 
                
                if not st.session_state.temp_barcode:
                    st.session_state.show_user_not_found_error = False 
                    if scan_value == st.session_state.current_user:
                        st.warning("⚠️ นั่นคือ User! กรุณาสแกน Barcode สินค้า", icon="⚠️")
                    else:
                        st.session_state.temp_barcode = scan_value
                        st.success(f"Barcode: {scan_value} ถูกล็อคแล้ว")
                        st.rerun()

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
                        
            has_sticky_error = st.session_state.show_user_not_found_error or st.session_state.show_duplicate_tracking_error
            
            if not st.session_state.temp_barcode:
                scanner_prompt_placeholder.info("ขั้นตอนที่ 2: สแกน Barcode สินค้า...")
            else:
                if st.session_state.show_duplicate_tracking_error:
                    scanner_prompt_placeholder.error(f"⚠️ สแกนซ้ำ! '{st.session_state.last_scanned_tracking}' มีในรายการแล้ว", icon="⚠️")
                else:
                    scanner_prompt_placeholder.info("ขั้นตอนที่ 3: สแกน Tracking Number ทีละกล่อง...")

            if has_sticky_error:
                st.button("❌ ปิดแจ้งเตือน (และสแกนใหม่)", 
                          on_click=acknowledge_error_and_reset_scanner, 
                          use_container_width=True, type="primary") 
                          
            st.divider()
            
            col_user, col_barcode = st.columns(2)
            with col_user:
                st.subheader("1.User")
                st.code(st.session_state.current_user)
                st.button("❌ เปลี่ยน User (และเริ่มใหม่)", on_click=clear_all_and_restart, use_container_width=True) 
            with col_barcode:
                st.subheader("2.Barcode")
                if st.session_state.temp_barcode:
                    st.code(st.session_state.temp_barcode)
                else:
                    st.info("...รอล็อค Barcode...")
            
            st.divider() 

            st.button("💾 บันทึกทั้งหมด (และเริ่มใหม่)",
                      type="primary",
                      use_container_width=True,
                      on_click=save_all_to_db,
                      disabled=(not st.session_state.staged_scans or not st.session_state.temp_barcode or not st.session_state.current_user)
                     )

            st.subheader(f"3. รายการที่กำลังสแกน ({len(st.session_state.staged_scans)} รายการ)")
            if not st.session_state.staged_scans:
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
                            st.button("❌ ลบ", key=f"del_{item['id']}", on_click=delete_item, 
                                      args=(item['id'],), use_container_width=True)

        # --- 🟠 (Logic จาก Single_version - เพิ่มปุ่ม "กลับ") 🟠 ---
        elif st.session_state.scan_mode == "Single":
            
            mode_name = "โหมด Single" # (เพิ่ม)
            st.header(f"{mode_name}") # (เพิ่ม)
            
            st.subheader("ผู้ใช้งาน (User)")
            st.code(st.session_state.current_user)
            st.button("❌ เปลี่ยน User (และเริ่มใหม่)", on_click=clear_all_and_restart, use_container_width=True)
            st.divider()

            if st.session_state.show_dialog_for == 'tracking':
                 show_confirmation_dialog(is_tracking=True)
            elif st.session_state.show_dialog_for == 'barcode':
                 show_confirmation_dialog(is_tracking=False)
            
            st.subheader("1. สแกนที่นี่ (Scan Here)")
            scanner_prompt_placeholder = st.empty() 
            
            if st.session_state.show_dialog_for == 'staging':
                add_and_clear_staging()

            if st.session_state.show_dialog_for is None:
                scan_value = qrcode_scanner(key=st.session_state.scanner_key)
                
                # --- (ปุ่ม "กลับ" จุดที่ 3) ---
                st.button("🔙 กลับ Menu หลัก", on_click=clear_all_and_restart, key="back_menu_single")

                is_new_scan = (scan_value is not None) and (scan_value != st.session_state.last_scan_processed)

                if not st.session_state.temp_tracking:
                    scanner_prompt_placeholder.info("ขั้นตอนที่ 2: สแกน Tracking...")
                else:
                    if st.session_state.show_scan_error_message:
                         scanner_prompt_placeholder.error("⚠️ สแกนซ้ำ! กรุณาสแกน Barcode", icon="⚠️")
                    else:
                         scanner_prompt_placeholder.success("ขั้นตอนที่ 3: สแกน Barcode...")

                if is_new_scan:
                    st.session_state.last_scan_processed = scan_value
                    
                    if not st.session_state.temp_tracking:
                        if scan_value == st.session_state.current_user:
                            st.warning("⚠️ นั่นคือ User! กรุณาสแกน Tracking", icon="⚠️")
                        else:
                            st.session_state.temp_tracking = scan_value
                            st.session_state.show_dialog_for = 'tracking' 
                            st.rerun() 
                    
                    elif st.session_state.temp_tracking and not st.session_state.temp_barcode:
                        if scan_value != st.session_state.temp_tracking and scan_value != st.session_state.current_user:
                            st.session_state.temp_barcode = scan_value
                            st.session_state.show_dialog_for = 'barcode' 
                            st.session_state.show_scan_error_message = False 
                            st.rerun() 
                        else:
                            st.session_state.show_scan_error_message = True
                            st.rerun()
            
            else:
                 st.info(f"... กด 'ปิด' ใน Popup ยืนยัน ...")

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

            st.button("💾 บันทึกทั้งหมด (และเริ่มใหม่)",
                      type="primary",
                      use_container_width=True,
                      on_click=save_all_to_db,
                      disabled=(not st.session_state.staged_scans)
                     )

            st.subheader(f"3. รายการที่กำลังสแกน ({len(st.session_state.staged_scans)} รายการ)")
            
            if not st.session_state.staged_scans:
                st.info("ยังไม่มีรายการสแกน...")
            else:
                for item in reversed(st.session_state.staged_scans): 
                    with st.container(border=True):
                        st.caption("Tracking:")
                        st.code(item["tracking"])
                        st.caption("Barcode:")
                        col_b_s, col_del_s = st.columns([4, 1]) 
                        with col_b_s:
                            st.code(item["barcode"])
                        with col_del_s:
                            st.button("❌ ลบ", 
                                      key=f"del_{item['id']}", 
                                      on_click=delete_item, 
                                      args=(item['id'],),
                                      use_container_width=True
                                     )

# --- TAB 2: จัดการ User และ ดูข้อมูล (แก้ไขตามที่ขอ) ---
with tab2:
    st.header("จัดการข้อมูล User")
    
    # 1. ส่วนเพิ่ม/แก้ไข User
    with st.container(border=True):
        st.subheader("เพิ่ม / แก้ไข User")
        
        # ดึงข้อมูล User ล่าสุด
        try:
            users_df = supabase_conn.query("SELECT * FROM users ORDER BY name", ttl=0)
            all_users_list = users_df['name'].tolist() if not users_df.empty else []
        except:
            all_users_list = []
            st.error("ไม่สามารถเชื่อมต่อตาราง users ได้")

        # กล่องเลือก User (Search Box)
        search_options = ["---เพิ่ม User ใหม่---"] + all_users_list
        selected_manage_user = st.selectbox("ค้นหา/แก้ไข User:", search_options, key="manage_user_select")

        # --- 🟢 แก้ไขจุดที่ 1: การเพิ่ม User ใหม่ ---
        if selected_manage_user == "---เพิ่ม User ใหม่---":
            # ใช้ expanded=True เพื่อให้เปิดตลอด
            with st.expander("กรอกข้อมูล User ใหม่", expanded=True):
                with st.form("add_user_form"):
                    new_name = st.text_input("ชื่อ-สกุล (Name):")
                    new_emp_id = st.text_input("รหัสพนักงาน (ID):")
                    submitted_add = st.form_submit_button("บันทึก User ใหม่", type="primary")
                    
                    if submitted_add:
                        if new_name and new_emp_id:
                            try:
                                # เช็คซ้ำ
                                check_dup = users_df[users_df['name'] == new_name] if not users_df.empty else pd.DataFrame()
                                if not check_dup.empty:
                                    st.error("ชื่อนี้มีอยู่ในระบบแล้ว")
                                else:
                                    new_user_data = pd.DataFrame([{"name": new_name, "employee_id": new_emp_id}])
                                    new_user_data.to_sql("users", con=supabase_conn.engine, if_exists="append", index=False)
                                    st.success(f"เพิ่ม User: {new_name} สำเร็จ!")
                                    st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
                        else:
                            st.warning("กรุณากรอกข้อมูลให้ครบ")

        # --- 🟢 แก้ไขจุดที่ 2: การแก้ไข User เดิม ---
        elif selected_manage_user:
            # ดึงข้อมูลของ User ที่เลือก
            current_data = users_df[users_df['name'] == selected_manage_user].iloc[0]
            
            # 🟢 FIX: ใช้ expanded=True เพื่อให้กล่องไม่หุบเมื่อเลือกชื่อ
            with st.expander(f"แก้ไขข้อมูล: {selected_manage_user}", expanded=True):
                with st.form("edit_user_form"):
                    edit_name = st.text_input("แก้ไขชื่อ-สกุล:", value=current_data['name'])
                    edit_emp_id = st.text_input("แก้ไขรหัสพนักงาน:", value=current_data['employee_id'])
                    
                    c1, c2 = st.columns(2)
                    with c1:
                        submitted_edit = st.form_submit_button("บันทึกการแก้ไข", type="primary", use_container_width=True)
                    with c2:
                        submitted_delete = st.form_submit_button("ลบ User นี้", type="secondary", use_container_width=True)

                    if submitted_edit:
                        try:
                            # Update โดยใช้ SQLAlchemy text
                            with supabase_conn.engine.connect() as conn:
                                stmt = text("UPDATE users SET name=:n, employee_id=:e WHERE id=:id")
                                conn.execute(stmt, {"n": edit_name, "e": edit_emp_id, "id": current_data['id']})
                                conn.commit()
                            st.success("แก้ไขข้อมูลสำเร็จ!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error Update: {e}")
                    
                    if submitted_delete:
                        try:
                            with supabase_conn.engine.connect() as conn:
                                stmt = text("DELETE FROM users WHERE id=:id")
                                conn.execute(stmt, {"id": current_data['id']})
                                conn.commit()
                            st.success(f"ลบ User {selected_manage_user} สำเร็จ!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error Delete: {e}")

    st.divider()

    # 2. ส่วนดูข้อมูล Scan (History)
    st.subheader("ประวัติการสแกน (History)")
    with st.expander("ตัวกรองข้อมูล (Filter)", expanded=False):
        col_f1, col_col2 = st.columns(2)
        with col_f1:
            # ใช้ Dropdown User ในการกรองด้วย
            filter_user = st.selectbox("กรองตาม User:", ["ทั้งหมด"] + all_users_list)
        with col_col2:
            filter_date = st.date_input("กรองตามวันที่", value=None) 
            
    # Query Data
    try:
        query = "SELECT * FROM scans"
        filters = []
        params = {}
        
        if filter_user and filter_user != "ทั้งหมด":
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
            
            # CSV Download
            df_for_csv = data_df.copy()
            # จัด Format วันที่ให้สวยงามใน CSV
            try:
                df_for_csv['created_at'] = pd.to_datetime(df_for_csv['created_at']).dt.strftime('%d-%m-%Y %H:%M')
            except:
                pass

            @st.cache_data
            def convert_df_to_csv(df_to_convert):
                return df_to_convert.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
            
            csv_data = convert_df_to_csv(df_for_csv)
            
            st.download_button(
                label="📥 Download ข้อมูลเป็น CSV",
                data=csv_data,
                file_name=f"scan_export_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )
        else:
            st.info("ไม่พบข้อมูลตามเงื่อนไข")

    except Exception as e:
        st.error(f"Error loading history: {e}")
