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
[data-testid="stMetricLabel"] { font-size: 0.7rem !important; }

/* 5. Staging Card Container */
[data-testid="stVerticalBlock"] > [data-testid="stContainer"] {
    border: 1px solid #BBBBBB !important; 
    border-radius: 0.5rem;
    padding: 0.5rem 0.75rem !important; 
    margin-bottom: 0.5rem; 
}

/* 6. Code Box */
.stCode { font-size: 0.75rem !important; padding: 0.4em !important; }

/* 7. Delete Button */
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

# --- 3. สร้างฟังก์ชันสำหรับปุ่ม (Callbacks) ---
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

# --- Dialog Function ---
@st.dialog("✅ สแกนสำเร็จ")
def show_confirmation_dialog(is_tracking):
    code_type = "Tracking Number" if is_tracking else "Barcode สินค้า"
    code_value = st.session_state.temp_tracking if is_tracking else st.session_state.temp_barcode
    
    st.info(f"ยืนยัน {code_type} ที่สแกนได้:")
    st.code(code_value)
    
    if is_tracking:
        st.success("Tracking ถูกสแกนและยืนยันแล้ว!")
        st.warning("ข้อมูลจะถูกเพิ่มลงในรายการทันที")
        if st.button("ปิด (และเพิ่มลงในรายการ)"):
            add_and_clear_staging()
    else: 
        st.warning("ขั้นต่อไป: กด 'ปิด' แล้วสแกน Tracking")
        if st.button("ปิด (และเตรียมสแกน Tracking)"):
            st.session_state.show_dialog_for = None
            st.rerun()

# --- 4. แบ่งหน้าจอด้วย Tabs ---
tab1, tab2 = st.tabs(["📷 สแกนกล่อง", "👤 จัดการ User / ดูข้อมูล"])

# --- TAB 1: หน้าสแกน ---
with tab1:
    st.header("บันทึกการสแกน")

    if st.session_state.get("show_scan_error_message", False):
        st.error("⚠️ สแกนซ้ำ! กรุณาสแกน Tracking", icon="⚠️")

    # ส่วนเลือก User (Dropdown จาก DB)
    try:
        users_df = supabase_conn.query("SELECT * FROM users ORDER BY name", ttl=0)
        user_options = users_df['name'].tolist() if not users_df.empty else []
    except:
        user_options = []
    
    col_user, col_metric = st.columns([3, 2]) 
    with col_user:
        # ใช้ Selectbox แทน Text Input เดิม
        selected_scan_user = st.selectbox(
            "ชื่อผู้ใช้งาน (User):", 
            [""] + user_options,
            key="scan_page_user_select"
        )
        # อัปเดต current_user จากการเลือก
        if selected_scan_user:
            st.session_state.current_user = selected_scan_user

    with col_metric:
        st.metric("กล่อง (รอบนี้)", st.session_state.scan_count)

    if not st.session_state.current_user:
        st.warning("เลือกชื่อผู้ใช้งานก่อนเริ่มสแกน")
    else:
        # Logic การสแกน (เหมือนเดิม)
        if st.session_state.show_dialog_for == 'tracking':
             show_confirmation_dialog(is_tracking=True)
        elif st.session_state.show_dialog_for == 'barcode':
             show_confirmation_dialog(is_tracking=False)
             
        st.subheader("1. สแกนที่นี่ (Scan Here)")
        
        if st.session_state.show_dialog_for is None:
            if not st.session_state.temp_barcode:
                st.info("ขั้นตอนที่ 1: สแกน Barcode...")
            elif not st.session_state.temp_tracking:
                 if not st.session_state.show_scan_error_message:
                     st.success("ขั้นตอนที่ 2: สแกน Tracking...")
            else:
                 st.success("สำเร็จ! เริ่มสแกน Barcode กล่องถัดไป")
                 st.session_state.temp_barcode = "" 
                 st.rerun() 

            scan_value = qrcode_scanner(key="main_scanner")

            if scan_value:
                if not st.session_state.temp_barcode:
                    st.session_state.temp_barcode = scan_value
                    st.session_state.show_dialog_for = 'barcode' 
                    st.rerun() 
                elif st.session_state.temp_barcode and not st.session_state.temp_tracking:
                    if scan_value != st.session_state.temp_barcode: 
                        st.session_state.temp_tracking = scan_value
                        st.session_state.show_dialog_for = 'tracking' 
                        st.session_state.show_scan_error_message = False
                        st.rerun() 
                    else:
                        st.session_state.show_scan_error_message = True
                        st.rerun()
                elif st.session_state.temp_barcode and st.session_state.temp_tracking:
                    st.warning("รอสักครู่...")
        else:
            st.info(f"... กด 'ปิด' ใน Popup ...")

        st.subheader("2. ข้อมูลที่กำลังสแกน")
        col_t, col_b = st.columns(2)
        with col_t:
            st.text_input("Tracking", value=st.session_state.temp_tracking, disabled=True, label_visibility="collapsed")
            st.caption("Tracking ที่สแกนได้") 
        with col_b:
            st.text_input("Barcode", value=st.session_state.temp_barcode, disabled=True, label_visibility="collapsed")
            st.caption("Barcode ที่สแกนได้") 
        
        st.divider()
        st.button("💾 บันทึกทั้งหมด", type="primary", use_container_width=True, on_click=save_all_to_db, disabled=(not st.session_state.staged_scans))

        st.subheader(f"3. รายการที่กำลังสแกน ({len(st.session_state.staged_scans)} รายการ)")
        if not st.session_state.staged_scans:
            st.info("ยังไม่มีรายการสแกน")
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
                        st.button("❌", key=f"del_{item['id']}", on_click=delete_item, args=(item['id'],), use_container_width=True)

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
