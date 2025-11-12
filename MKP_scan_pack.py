import streamlit as st
import pandas as pd
import io
from datetime import datetime
from streamlit.connections import SQLConnection
from streamlit_qrcode_scanner import qrcode_scanner
import uuid 
import pytz # <-- เพิ่ม Library สำหรับ Timezone

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
if "show_dialog" not in st.session_state:
    st.session_state.show_dialog = False # <--- เปลี่ยนชื่อ State จาก modal เป็น dialog

# --- 3. สร้างฟังก์ชันสำหรับปุ่ม (Callbacks) ---

def add_to_stage():
    if st.session_state.temp_tracking and st.session_state.temp_barcode:
        st.session_state.staged_scans.append({
            "id": str(uuid.uuid4()),
            "tracking": st.session_state.temp_tracking,
            "barcode": st.session_state.temp_barcode
        })
        st.session_state.temp_tracking = ""
        st.session_state.temp_barcode = ""
    else:
        st.warning("กรุณาสแกนให้ครบทั้ง Tracking และ Barcode ก่อนเพิ่ม")

def delete_item(item_id_to_delete):
    st.session_state.staged_scans = [
        item for item in st.session_state.staged_scans 
        if item["id"] != item_id_to_delete
    ]

def save_all_to_db():
    if not st.session_state.staged_scans:
        st.warning("ไม่มีข้อมูลในรายการให้บันทึก")
        return
    try:
        data_to_insert = []
        # --- (แก้ไข #2) Timezone ---
        THAI_TZ = pytz.timezone("Asia/Bangkok")
        current_time = datetime.now(THAI_TZ)
        
        for item in st.session_state.staged_scans:
            data_to_insert.append({
                "user_id": st.session_state.current_user,
                "tracking_code": item["tracking"],
                "product_barcode": item["barcode"],
                # บันทึกเป็นเวลาท้องถิ่น (Supabase จะรับค่านี้)
                "created_at": current_time
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

# --- 4. แบ่งหน้าจอด้วย Tabs ---
tab1, tab2 = st.tabs(["📷 สแกนกล่อง", "📊 ดูข้อมูลและดาวน์โหลด"])

# --- (ใหม่) สร้าง Dialog Function (นอก with tab1) ---
# เราใช้ st.dialog ที่เป็น function decorator (ต้องอยู่ข้างนอก)
@st.dialog("✅ สแกน Tracking สำเร็จ")
def show_tracking_dialog():
    st.info("กรุณายืนยัน Tracking Number ที่สแกนได้:")
    st.code(st.session_state.temp_tracking)
    st.warning("ขั้นต่อไป: กรุณากด 'ปิด' แล้วสแกน Barcode ครับ")
    
    # ปุ่ม 'ปิด'
    if st.button("ปิด (และเตรียมสแกน Barcode)"):
        st.session_state.show_dialog = False
        st.rerun()

# --- TAB 1: หน้าสแกน ---
with tab1:
    st.header("บันทึกการสแกน")

    user = st.text_input("ชื่อผู้ใช้งาน (User):", st.session_state.current_user)
    st.session_state.current_user = user 

    if not user:
        st.warning("กรุณาป้อนชื่อผู้ใช้งานก่อนเริ่มสแกน")
    else:
        
        # --- Logic การแสดง Dialog ---
        # (แก้ไข #1) ถ้า State เป็น True ให้เรียก Dialog Function
        if st.session_state.show_dialog:
             show_tracking_dialog()
             
        # --- ส่วนที่ 1: กล้องสแกน (ใช้จุดเดียว) ---
        st.subheader("1. สแกนที่นี่ (Scan Here)")
        
        # เราจะแสดง Scanner ก็ต่อเมื่อ Dialog ปิดอยู่เท่านั้น
        if not st.session_state.show_dialog:
            if not st.session_state.temp_tracking:
                st.info("ขั้นตอนที่ 1: กรุณาสแกน Tracking...")
            else:
                st.success("ขั้นตอนที่ 2: กรุณาสแกน Barcode...")

            scan_value = qrcode_scanner(key="main_scanner")

            if scan_value:
                # Logic 1: สแกน Tracking
                if not st.session_state.temp_tracking:
                    st.session_state.temp_tracking = scan_value
                    st.session_state.show_dialog = True # <--- สั่งให้เปิด Dialog
                    # st.rerun() อยู่ใน Logic 1 (Tracking) เพื่อให้ Dialog เปิดทันที
                    st.rerun() 
                
                # Logic 2: สแกน Barcode
                elif st.session_state.temp_tracking and not st.session_state.temp_barcode:
                    if scan_value != st.session_state.temp_tracking:
                        st.session_state.temp_barcode = scan_value
                    
                elif st.session_state.temp_tracking and st.session_state.temp_barcode:
                    st.warning("กรุณากด 'เพิ่มลงในรายการ' ก่อนสแกนกล่องถัดไป")
        
        else:
            st.info("... กรุณากด 'ปิด' ใน Popup เพื่อสแกน Barcode ต่อ ...")

        # --- ส่วนที่ 2: แสดงผลค่าที่สแกนได้ชั่วคราว (เหมือนเดิม) ---
        st.subheader("2. ข้อมูลที่รอเพิ่ม")
        col1, col2, col3 = st.columns([3, 3, 1])
        
        with col1:
            st.text_input("Tracking ที่สแกนได้", 
                          value=st.session_state.temp_tracking, 
                          disabled=True)
        with col2:
            st.text_input("Barcode ที่สแกนได้", 
                          value=st.session_state.temp_barcode, 
                          disabled=True)
        with col3:
            st.button("➕ เพิ่มลงในรายการ", 
                      type="secondary",
                      use_container_width=True,
                      on_click=add_to_stage,
                      # ป้องกันไม่ให้กดเพิ่มถ้ารายการไม่ครบ
                      disabled=(not st.session_state.temp_tracking or not st.session_state.temp_barcode)
                     )

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

# --- TAB 2: หน้าดูข้อมูลและดาวน์โหลด (แก้ไข Timezone ใน Filter) ---
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
            # (แก้ไข #2) กรองตามวันที่ที่ถูกบันทึกใน Timezone ไทย (DATE(created_at) ทำงานบน Supabase)
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
            
            # (แก้ไข) ต้องใช้ data_df ที่ดึงมา
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
