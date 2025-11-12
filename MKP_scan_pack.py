import streamlit as st
import pandas as pd
import io
from datetime import datetime
from streamlit.connections import SQLConnection # <-- ใช้วิธีจาก Time_app
from streamlit_qrcode_scanner import qrcode_scanner # <-- ใช้วิธีจาก Time_app

# --- 1. ตั้งค่าหน้าจอและเชื่อมต่อ Supabase ---
st.set_page_config(page_title="Box Scanner", layout="wide")
st.title("📦 App สแกน Tracking และ Barcode")

# เชื่อมต่อ Supabase โดยใช้ st.connection (ตามแบบ Time_app)
@st.cache_resource
def init_supabase_connection():
    # ชื่อ "supabase" ต้องตรงกับใน Secrets [connections.supabase]
    return st.connection("supabase", type=SQLConnection)

supabase_conn = init_supabase_connection()

# --- 2. สร้าง Session State ---
if "tracking_code" not in st.session_state:
    st.session_state.tracking_code = ""
if "product_barcode" not in st.session_state:
    st.session_state.product_barcode = ""
if "scan_count" not in st.session_state:
    st.session_state.scan_count = 0
if "current_user" not in st.session_state:
    st.session_state.current_user = ""

# --- 3. แบ่งหน้าจอด้วย Tabs ---
tab1, tab2 = st.tabs(["📷 สแกนกล่อง", "📊 ดูข้อมูลและดาวน์โหลด"])

# --- TAB 1: หน้าสแกน ---
with tab1:
    st.header("บันทึกการสแกน")

    user = st.text_input("ชื่อผู้ใช้งาน (User):", st.session_state.current_user)
    st.session_state.current_user = user 

    if not user:
        st.warning("กรุณาป้อนชื่อผู้ใช้งานก่อนเริ่มสแกน")
    else:
        st.metric("จำนวนกล่องที่สแกน (ในรอบนี้)", st.session_state.scan_count)

        col1, col2 = st.columns(2)

        # --- ส่วนสแกน Tracking (QR Code) ---
        with col1:
            st.subheader("1. สแกน Tracking (QR Code)")
            # ใช้ qrcode_scanner (ตามแบบ Time_app)
            tracking_val = qrcode_scanner(key="tracking_scanner")

            if tracking_val:
                st.session_state.tracking_code = tracking_val

            if st.session_state.tracking_code:
                st.success(f"Tracking ที่สแกนได้: **{st.session_state.tracking_code}**")

        # --- ส่วนสแกน Barcode (EAN) ---
        with col2:
            st.subheader("2. สแกน Barcode สินค้า")
            # ใช้ qrcode_scanner (ตามแบบ Time_app)
            barcode_val = qrcode_scanner(key="product_scanner")

            if barcode_val:
                st.session_state.product_barcode = barcode_val

            if st.session_state.product_barcode:
                st.success(f"Barcode ที่สแกนได้: **{st.session_state.product_barcode}**")

        st.divider()

        # --- ส่วนบันทึกข้อมูล (ใช้ SQLConnection) ---
        if st.session_state.tracking_code and st.session_state.product_barcode:
            if st.button("💾 บันทึกข้อมูลกล่องนี้", type="primary", use_container_width=True):
                try:
                    # สร้าง SQL Query เพื่อ INSERT ข้อมูล
                    # (ตาราง "scans" และคอลัมน์ต้องตรงกับที่คุณสร้างไว้)
                    query = """
                    INSERT INTO scans (user_id, tracking_code, product_barcode, created_at)
                    VALUES (:user, :tracking, :barcode, :now)
                    """

                    # รันคำสั่ง SQL
                    supabase_conn.execute(
                        query,
                        params={
                            "user": st.session_state.current_user,
                            "tracking": st.session_state.tracking_code,
                            "barcode": st.session_state.product_barcode,
                            "now": datetime.now() # Supabase/Postgres จะจัดการ Timezone
                        }
                    )

                    st.success("บันทึกข้อมูลสำเร็จ!")
                    st.session_state.scan_count += 1

                    # เคลียร์ค่าเพื่อรอสแกนกล่องต่อไป
                    st.session_state.tracking_code = ""
                    st.session_state.product_barcode = ""
                    st.rerun()

                except Exception as e:
                    st.error(f"เกิดข้อผิดพลาดในการบันทึก: {e}")
        else:
            st.info("กรุณาสแกนทั้ง Tracking และ Barcode ให้ครบถ้วน")

# --- TAB 2: หน้าดูข้อมูลและดาวน์โหลด (ใช้ SQLConnection) ---
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
            # กรองข้อมูลตามวันที่ (Postgres)
            filters.append("DATE(created_at) = :date")
            params["date"] = filter_date

        if filters:
            query += " WHERE " + " AND ".join(filters)

        query += " ORDER BY created_at DESC"

        # ใช้ .query() เพื่อดึงข้อมูลเป็น DataFrame
        data_df = supabase_conn.query(query, params=params)

        if not data_df.empty:
            st.dataframe(data_df, use_container_width=True)

            # ฟังก์ชันแปลง CSV (เหมือนใน Time_app)
            @st.cache_data
            def convert_df_to_csv(df_to_convert):
                # ใช้ encoding='utf-8-sig' เพื่อให้ Excel เปิดภาษาไทยได้
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
