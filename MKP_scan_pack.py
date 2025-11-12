import streamlit as st
import pandas as pd
import io
from datetime import datetime
from streamlit.connections import SQLConnection
from streamlit_qrcode_scanner import qrcode_scanner
import uuid # ใช้สำหรับสร้าง ID ชั่วคราวให้ปุ่มลบ

# --- 1. ตั้งค่าหน้าจอและเชื่อมต่อ Supabase ---
st.set_page_config(page_title="Box Scanner", layout="wide")
st.title("📦 App สแกน Tracking และ Barcode")

# เชื่อมต่อ Supabase (เหมือนเดิม)
@st.cache_resource
def init_supabase_connection():
    return st.connection("supabase", type=SQLConnection)

supabase_conn = init_supabase_connection()

# --- 2. สร้าง Session State (ปรับปรุงใหม่) ---
if "current_user" not in st.session_state:
    st.session_state.current_user = ""
if "scan_count" not in st.session_state:
    st.session_state.scan_count = 0

# (ใหม่) สร้างตัวแปรสำหรับพักค่าที่สแกนได้ชั่วคราว
if "temp_tracking" not in st.session_state:
    st.session_state.temp_tracking = ""
if "temp_barcode" not in st.session_state:
    st.session_state.temp_barcode = ""

# (ใหม่) สร้าง "รายการ" สำหรับพักข้อมูลทั้งหมดก่อนบันทึก
if "staged_scans" not in st.session_state:
    st.session_state.staged_scans = [] # จะเป็น List ของ Dict

# --- 3. สร้างฟังก์ชันสำหรับปุ่ม (Callbacks) ---

def add_to_stage():
    """
    ฟังก์ชันสำหรับปุ่ม 'เพิ่มลงในรายการ'
    จะย้ายข้อมูลจาก temp ไปเก็บใน staged_scans
    """
    if st.session_state.temp_tracking and st.session_state.temp_barcode:
        st.session_state.staged_scans.append({
            "id": str(uuid.uuid4()), # สร้าง ID เฉพาะกิจสำหรับปุ่มลบ
            "tracking": st.session_state.temp_tracking,
            "barcode": st.session_state.temp_barcode
        })
        # ล้างค่าในช่องพักข้อมูล
        st.session_state.temp_tracking = ""
        st.session_state.temp_barcode = ""
    else:
        st.warning("กรุณาสแกนให้ครบทั้ง Tracking และ Barcode ก่อนเพิ่ม")

def delete_item(item_id_to_delete):
    """
    ฟังก์ชันสำหรับปุ่ม 'ลบ' (Concept ข้อ 5)
    จะลบรายการที่มี id ตรงกันออกจาก staged_scans
    """
    st.session_state.staged_scans = [
        item for item in st.session_state.staged_scans 
        if item["id"] != item_id_to_delete
    ]

def save_all_to_db():
    """
    ฟังก์ชันสำหรับปุ่ม 'บันทึกทั้งหมด'
    จะนำทุกอย่างใน staged_scans บันทึกลง Supabase
    """
    if not st.session_state.staged_scans:
        st.warning("ไม่มีข้อมูลในรายการให้บันทึก")
        return

    try:
        data_to_insert = []
        current_time = datetime.now()
        
        for item in st.session_state.staged_scans:
            data_to_insert.append({
                "user_id": st.session_state.current_user,
                "tracking_code": item["tracking"],
                "product_barcode": item["barcode"],
                "created_at": current_time
            })
        
        # แปลงเป็น DataFrame
        df_to_insert = pd.DataFrame(data_to_insert)
        
        # บันทึกลง Supabase (วิธีที่เร็วที่สุด)
        df_to_insert.to_sql(
            "scans", 
            con=supabase_conn.engine, 
            if_exists="append", 
            index=False
        )
        
        saved_count = len(st.session_state.staged_scans)
        st.session_state.scan_count += saved_count
        
        # ล้างรายการที่พักไว้
        st.session_state.staged_scans = []
        st.success(f"บันทึกข้อมูลทั้ง {saved_count} รายการ สำเร็จ!")
        st.rerun()

    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการบันทึก: {e}")


# --- 4. แบ่งหน้าจอด้วย Tabs ---
tab1, tab2 = st.tabs(["📷 สแกนกล่อง", "📊 ดูข้อมูลและดาวน์โหลด"])

# --- TAB 1: หน้าสแกน (ออกแบบใหม่ทั้งหมด) ---
with tab1:
    st.header("บันทึกการสแกน")

    user = st.text_input("ชื่อผู้ใช้งาน (User):", st.session_state.current_user)
    st.session_state.current_user = user 

    if not user:
        st.warning("กรุณาป้อนชื่อผู้ใช้งานก่อนเริ่มสแกน")
    else:
        # --- ส่วนที่ 1: กล้องสแกน (ใช้จุดเดียว) ---
        st.subheader("1. สแกนที่นี่ (Scan Here)")
        
        # (Concept ข้อ 1) ใช้กล้องตัวเดียว
        scan_value = qrcode_scanner(key="main_scanner")

        # (Concept ข้อ 2 & 3) Logic การสแกน
        if scan_value:
            if not st.session_state.temp_tracking:
                # Scan ครั้งแรก -> บันทึกที่ Tracking
                st.session_state.temp_tracking = scan_value
                st.rerun() # สั่งให้หน้าจออัปเดตทันที
            elif not st.session_state.temp_barcode:
                # Scan ครั้งที่ 2 -> บันทึกที่ Barcode
                st.session_state.temp_barcode = scan_value
                st.rerun() # สั่งให้หน้าจออัปเดตทันที
            else:
                # ถ้าสแกนครั้งที่ 3 (ทั้งที่ยังไม่กดเพิ่ม) ให้เตือน
                st.warning("กรุณากด 'เพิ่มลงในรายการ' ก่อนสแกนกล่องถัดไป")

        # --- ส่วนที่ 2: แสดงผลค่าที่สแกนได้ชั่วคราว ---
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
                      # ปิดปุ่มไว้ถ้ายังสแกนไม่ครบ
                      disabled=(not st.session_state.temp_tracking or not st.session_state.temp_barcode)
                     )

        st.divider()

        # --- ส่วนที่ 3: ตารางพักข้อมูล (Staging Area) ---
        st.subheader(f"3. รายการที่รอ C ({len(st.session_state.staged_scans)} รายการ)")
        
        # (Concept ข้อ 2) แสดงยอดรวมกล่องที่ Scan (ในรายการ)
        st.metric("จำนวนกล่องที่สแกน (ในรอบนี้)", st.session_state.scan_count)

        # สร้าง Header ของตาราง
        h_col1, h_col2, h_col3 = st.columns([3, 3, 1])
        h_col1.markdown("**Tracking**")
        h_col2.markdown("**Barcode**")
        h_col3.markdown("**ลบ**")

        # (Concept ข้อ 4 & 5) แสดงผลตารางพร้อมปุ่มลบ
        if not st.session_state.staged_scans:
            st.info("ยังไม่มีรายการสแกน กรุณาสแกน Tracking และ Barcode")
        else:
            for item in st.session_state.staged_scans:
                r_col1, r_col2, r_col3 = st.columns([3, 3, 1])
                r_col1.code(item["tracking"]) # ใช้ .code() เพื่อให้อ่านง่าย
                r_col2.code(item["barcode"])
                r_col3.button("❌ ลบ", 
                              key=f"del_{item['id']}", 
                              on_click=delete_item, 
                              args=(item['id'],),
                              use_container_width=True
                             )
        
        # ปุ่มบันทึกข้อมูลทั้งหมด
        st.button("💾 บันทึกทั้งหมดลง Database",
                  type="primary",
                  use_container_width=True,
                  on_click=save_all_to_db,
                  disabled=(not st.session_state.staged_scans) # ปิดปุ่มถ้าไม่มีอะไรให้บันทึก
                 )


# --- TAB 2: หน้าดูข้อมูลและดาวน์โหลด (เหมือนเดิมทุกประการ) ---
with tab2:
    st.header("ค้นหาและดาวน์โหลดข้อมูล")

    with st.expander("ตัวกรองข้อมูล (Filter)", expanded=True):
        col_f1, col_f2 = st.columns(2)
        
        with col_f1:
            filter_user = st.text_input("กรองตาม User (เว้นว่างเพื่อแสดงทั้งหมด)")
        with col_f2:
            filter_date = st.date_input("กรองตามวันที่", value=None) 

    try:
        # สร้าง Query เพื่อดึงข้อมูล
        query = "SELECT * FROM scans"
        filters = []
        params = {}

        if filter_user:
            filters.append("user_id = :user")
            params["user"] = filter_user
        if filter_date:
            filters.append("DATE(created_at) = :date")
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
