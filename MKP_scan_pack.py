import streamlit as st
import pandas as pd
import io
from datetime import datetime
from streamlit.connections import SQLConnection
from streamlit_qrcode_scanner import qrcode_scanner
import uuid 
import pytz 

# --- 1. ตั้งค่าหน้าจอและเชื่อมต่อ Supabase ---
st.set_page_config(page_title="Box Scanner", layout="wide")
st.title("📦 App สแกน Tracking และ Barcode")

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

# --- 3. สร้างฟังก์ชันสำหรับปุ่ม (Callbacks) ---

# **********************************************
# ฟังก์ชัน add_to_stage() ถูกยกเลิกและย้ายไปรวมใน Dialog แล้ว
# **********************************************

def delete_item(item_id_to_delete):
    """ฟังก์ชันสำหรับลบรายการออกจากตารางพักข้อมูล"""
    st.session_state.staged_scans = [
        item for item in st.session_state.staged_scans 
        if item["id"] != item_id_to_delete
    ]

def add_and_clear_staging():
    """
    (ใหม่) ฟังก์ชันนี้จะถูกเรียกจากปุ่มใน Dialog Barcode 
    เพื่อเพิ่มข้อมูลและเคลียร์ State ทันที
    """
    if st.session_state.temp_tracking and st.session_state.temp_barcode:
        st.session_state.staged_scans.append({
            "id": str(uuid.uuid4()),
            "tracking": st.session_state.temp_tracking,
            "barcode": st.session_state.temp_barcode
        })
        # เคลียร์ค่า staging และ Dialog state
        st.session_state.temp_tracking = ""
        st.session_state.temp_barcode = ""
        st.session_state.show_dialog_for = None 
    
    # ต้อง rerun เพื่ออัปเดตตารางและปิด Dialog
    st.rerun() 

def save_all_to_db():
    """ฟังก์ชันสำหรับบันทึกข้อมูลทั้งหมดลง Database"""
    if not st.session_state.staged_scans:
        st.warning("ไม่มีข้อมูลในรายการให้บันทึก")
        return
    try:
        data_to_insert = []
        
        # 🟢 FIX 1: ดึงเวลาปัจจุบันใน Timezone ไทย (GMT+7)
        THAI_TZ = pytz.timezone("Asia/Bangkok")
        current_time = datetime.now(THAI_TZ)
        
        for item in st.session_state.staged_scans:
            data_to_insert.append({
                "user_id": st.session_state.current_user,
                "tracking_code": item["tracking"],
                "product_barcode": item["barcode"],
                # 🟢 FIX 2: ตัด Timezone ออกก่อนส่งให้ DB 
                # (PostgreSQL จะบันทึกตาม Timezone ที่กำหนด แต่เราไม่ส่งข้อมูล Timezone ไป)
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
        st.success(f"บันทึกข้อมูลทั้ง {saved_count} รายการ สำเร็จ!")
        st.rerun()
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการบันทึก: {e}")

# --- (ใหม่) สร้าง Dialog Function (สำหรับ Tracking และ Barcode) ---
@st.dialog("✅ สแกนสำเร็จ")
def show_confirmation_dialog(is_tracking):
    
    code_type = "Tracking Number" if is_tracking else "Barcode สินค้า"
    code_value = st.session_state.temp_tracking if is_tracking else st.session_state.temp_barcode

    st.info(f"กรุณายืนยัน {code_type} ที่สแกนได้:")
    st.code(code_value)
    
    if is_tracking:
        st.warning("ขั้นต่อไป: กรุณากด 'ปิด' แล้วสแกน Barcode ครับ")
        
        if st.button("ปิด (และเตรียมสแกน Barcode)"):
            st.session_state.show_dialog_for = None
            st.rerun()
    else: # Barcode
        # (แก้ไข #1) เปลี่ยนปุ่มเป็นการ "เพิ่มข้อมูลลงรายการทันที"
        st.success("Barcode ถูกสแกนและยืนยันแล้ว!")
        st.warning("ข้อมูลจะถูกเพิ่มลงในรายการทันที")
        
        if st.button("ปิด (และเพิ่มลงในรายการ)"):
            add_and_clear_staging() # <--- เรียกฟังก์ชันเพิ่มข้อมูลทันที
            # st.rerun() ถูกเรียกจากใน add_and_clear_staging() แล้ว


# --- 4. แบ่งหน้าจอด้วย Tabs ---
tab1, tab2 = st.tabs(["📷 สแกนกล่อง", "📊 ดูข้อมูลและดาวน์โหลด"])

# --- TAB 1: หน้าสแกน ---
with tab1:
    st.header("บันทึกการสแกน")

    user = st.text_input("ชื่อผู้ใช้งาน (User):", st.session_state.current_user)
    st.session_state.current_user = user 

    if not user:
        st.warning("กรุณาป้อนชื่อผู้ใช้งานก่อนเริ่มสแกน")
    else:
        
        # --- Logic การแสดง Dialog ---
        if st.session_state.show_dialog_for == 'tracking':
             show_confirmation_dialog(is_tracking=True)
        elif st.session_state.show_dialog_for == 'barcode':
             show_confirmation_dialog(is_tracking=False)
             
        # --- ส่วนที่ 1: กล้องสแกน (ใช้จุดเดียว) ---
        st.subheader("1. สแกนที่นี่ (Scan Here)")
        
        if st.session_state.show_dialog_for is None:
            if not st.session_state.temp_tracking:
                st.info("ขั้นตอนที่ 1: กรุณาสแกน Tracking...")
            elif not st.session_state.temp_barcode:
                 st.success("ขั้นตอนที่ 2: กรุณาสแกน Barcode...")
            else:
                 st.success("สำเร็จ! กรุณาเริ่มสแกน Tracking กล่องถัดไปได้เลย")
                 # (แก้ไข) แสดง Scanner อีกครั้งทันที
                 st.session_state.temp_tracking = "" # ล้างค่า temp_tracking เพื่อเริ่มใหม่
                 st.rerun() # เริ่ม Logic ใหม่เพื่อสแกน Tracking ถัดไปทันที

            scan_value = qrcode_scanner(key="main_scanner")

            if scan_value:
                # Logic 1: สแกน Tracking
                if not st.session_state.temp_tracking:
                    st.session_state.temp_tracking = scan_value
                    st.session_state.show_dialog_for = 'tracking' 
                    st.rerun() 
                
                # Logic 2: สแกน Barcode
                elif st.session_state.temp_tracking and not st.session_state.temp_barcode:
                    if scan_value != st.session_state.temp_tracking:
                        st.session_state.temp_barcode = scan_value
                        st.session_state.show_dialog_for = 'barcode' 
                        st.rerun() 
                    
                # Logic 3: สแกนซ้ำเมื่อสแกนเสร็จแล้วทั้งคู่ (ควรจะถูก Logic ด้านบนจัดการไปแล้ว)
                elif st.session_state.temp_tracking and st.session_state.temp_barcode:
                    st.warning("กรุณารอสักครู่ (ระบบกำลังเพิ่มรายการ) หรือเริ่มสแกน Tracking ถัดไปได้เลย")

        
        else:
            st.info(f"... กรุณากด 'ปิด' ใน Popup ยืนยัน {st.session_state.show_dialog_for.capitalize()} ...")

        # --- ส่วนที่ 2: แสดงผลค่าที่สแกนได้ชั่วคราว (ลบปุ่มเพิ่มรายการ) ---
        st.subheader("2. ข้อมูลที่กำลังสแกน (เพิ่มอัตโนมัติเมื่อยืนยัน Barcode)")
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.text_input("Tracking ที่สแกนได้", 
                          value=st.session_state.temp_tracking, 
                          disabled=True)
        with col2:
            st.text_input("Barcode ที่สแกนได้", 
                          value=st.session_state.temp_barcode, 
                          disabled=True)
        # ❌❌❌ ลบบล็อกปุ่ม "➕ เพิ่มลงในรายการ" ออกไปแล้ว ❌❌❌

        st.divider()

        # --- ส่วนที่ 3: ตารางพักข้อมูล (Staging Area) (เหมือนเดิม) ---
        st.subheader(f"3. รายการที่รอ C ({len(st.session_state.staged_scans)} รายการ)")
        st.metric("จำนวนกล่องที่สแกน (ในรอบนี้)", st.session_state.scan_count)
        
        h_col1, h_col2, h_col3 = st.columns([3, 3, 1])
        h_col1.markdown("**Tracking**")
        h_col2.markdown("**Barcode**")
        h_col3.markdown("**ลบ**")
        if not st.session_state.staged_scans:
            st.info("ยังไม่มีรายการสแกน กรุณาสแกน Tracking และ Barcode")
        else:
            for item in st.session_state.staged_scans:
                r_col1, r_col2, r_col3 = st.columns([3, 3, 1])
                r_col1.code(item["tracking"])
                r_col2.code(item["barcode"])
                r_col3.button("❌ ลบ", 
                              key=f"del_{item['id']}", 
                              on_click=delete_item, 
                              args=(item['id'],),
                              use_container_width=True
                             )
        st.button("💾 บันทึกทั้งหมดลง Database",
                  type="primary",
                  use_container_width=True,
                  on_click=save_all_to_db,
                  disabled=(not st.session_state.staged_scans)
                 )

# --- TAB 2: หน้าดูข้อมูลและดาวน์โหลด (เหมือนเดิมทุกประการ) ---
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
        st.error(f"เกิดข้อผิดพลาดในการดึงข้อมูล: {e}")
