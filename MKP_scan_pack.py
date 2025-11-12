import streamlit as st
from streamlit_camera_barcode_reader import camera_barcode_reader as barcode_scanner # ตัวสแกน
from supabase import create_client, Client
import pandas as pd
import io

# --- 1. ตั้งค่าหน้าจอและเชื่อมต่อ Supabase ---

st.set_page_config(page_title="Box Scanner", layout="wide")
st.title("📦 App สแกน Tracking และ Barcode")

# เชื่อมต่อ Supabase (ใช้ st.secrets)
@st.cache_resource
def init_supabase_client():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase_client()

# --- 2. สร้าง Session State (หัวใจสำคัญ) ---
# ใช้เก็บค่าที่สแกนไว้ชั่วคราวก่อนบันทึก

if "tracking_code" not in st.session_state:
    st.session_state.tracking_code = None
if "product_barcode" not in st.session_state:
    st.session_state.product_barcode = None
if "scan_count" not in st.session_state:
    st.session_state.scan_count = 0
if "current_user" not in st.session_state:
    st.session_state.current_user = ""

# --- 3. แบ่งหน้าจอด้วย Tabs ---

tab1, tab2 = st.tabs(["📷 สแกนกล่อง", "📊 ดูข้อมูลและดาวน์โหลด"])

# --- TAB 1: หน้าสแกน ---
with tab1:
    st.header("บันทึกการสแกน")

    # Concept 1: บันทึก User
    user = st.text_input("ชื่อผู้ใช้งาน (User):", key="current_user")

    if not user:
        st.warning("กรุณาป้อนชื่อผู้ใช้งานก่อนเริ่มสแกน")
    else:
        # แสดงยอดรวมที่สแกนใน Session นี้ (Concept 2)
        st.metric("จำนวนกล่องที่สแกน (ในรอบนี้)", st.session_state.scan_count)
        
        col1, col2 = st.columns(2)

        # --- ส่วนสแกน Tracking (QR Code) ---
        with col1:
            st.subheader("1. สแกน Tracking (QR Code)")
            
            # ปุ่มสแกน
            tracking_val = barcode_scanner(key="tracking_scanner")
            
            if tracking_val:
                st.session_state.tracking_code = tracking_val
            
            if st.session_state.tracking_code:
                st.success(f"Tracking ที่สแกนได้: **{st.session_state.tracking_code}**")

        # --- ส่วนสแกน Barcode (EAN) ---
        with col2:
            st.subheader("2. สแกน Barcode สินค้า")

            # ปุ่มสแกน
            barcode_val = barcode_scanner(key="product_scanner")
            
            if barcode_val:
                st.session_state.product_barcode = barcode_val

            if st.session_state.product_barcode:
                st.success(f"Barcode ที่สแกนได้: **{st.session_state.product_barcode}**")

        st.divider()

        # --- ส่วนบันทึกข้อมูล ---
        if st.session_state.tracking_code and st.session_state.product_barcode:
            if st.button("💾 บันทึกข้อมูลกล่องนี้", type="primary", use_container_width=True):
                try:
                    # Concept 3: บันทึก User, Tracking, Barcode และเวลา (อัตโนมัติ)
                    data_to_insert = {
                        "user_id": st.session_state.current_user,
                        "tracking_code": st.session_state.tracking_code,
                        "product_barcode": st.session_state.product_barcode
                    }
                    
                    supabase.table("scans").insert(data_to_insert).execute()
                    
                    st.success("บันทึกข้อมูลสำเร็จ!")
                    
                    # เพิ่มยอดรวม (Concept 2)
                    st.session_state.scan_count += 1
                    
                    # เคลียร์ค่าเพื่อรอสแกนกล่องต่อไป
                    st.session_state.tracking_code = None
                    st.session_state.product_barcode = None
                    
                    # Rerun สคริปต์เพื่อให้หน้าจออัปเดต
                    st.rerun()

                except Exception as e:
                    st.error(f"เกิดข้อผิดพลาดในการบันทึก: {e}")
        else:
            st.info("กรุณาสแกนทั้ง Tracking และ Barcode ให้ครบถ้วนก่อนบันทึก")

# --- TAB 2: หน้าดูข้อมูลและดาวน์โหลด ---
with tab2:
    st.header("ค้นหาและดาวน์โหลดข้อมูล")

    # Concept 4: Filter Data
    with st.expander("ตัวกรองข้อมูล (Filter)", expanded=True):
        col_f1, col_f2 = st.columns(2)
        
        with col_f1:
            filter_user = st.text_input("กรองตาม User (เว้นว่างเพื่อแสดงทั้งหมด)")
        with col_f2:
            # กรองตามวันที่ (Concept 3)
            filter_date = st.date_input("กรองตามวันที่", value=None) 

    # --- ดึงข้อมูลจาก Supabase ---
    try:
        query = supabase.table("scans").select("*").order("created_at", desc=True)
        
        # ใช้ Filter
        if filter_user:
            query = query.eq("user_id", filter_user)
        if filter_date:
            # กรองข้อมูลตามวันที่ที่เลือก (เริ่ม 00:00 ถึง 23:59)
            start_date = str(filter_date) + " 00:00:00"
            end_date = str(filter_date) + " 23:59:59"
            query = query.gte("created_at", start_date).lte("created_at", end_date)
            
        data = query.execute().data
        
        if data:
            df = pd.DataFrame(data)
            st.dataframe(df, use_container_width=True)
            
            # --- ปุ่ม Download (Concept 4) ---
            
            # แปลง DataFrame เป็น CSV
            @st.cache_data
            def convert_df_to_csv(df_to_convert):
                output = io.StringIO()
                df_to_convert.to_csv(output, index=False, encoding='utf-8')
                return output.getvalue()

            csv_data = convert_df_to_csv(df)
            
            st.download_button(
                label="📥 Download ข้อมูลเป็น CSV",
                data=csv_data,
                file_name=f"scan_export_{filter_date or 'all'}.csv",
                mime="text/csv",
            )
            
        else:
            st.info("ไม่พบข้อมูลตามเงื่อนไขที่เลือก")
            
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการดึงข้อมูล: {e}")
