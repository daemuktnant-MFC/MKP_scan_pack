import streamlit as st
from supabase import create_client, Client
import pandas as pd
import io
import cv2  # <--- เพิ่มมาใหม่
import numpy as np # <--- เพิ่มมาใหม่
from pyzbar.pyzbar import decode # <--- เพิ่มมาใหม่
from streamlit_webrtc import webrtc_streamer, WebRtcMode, VideoTransformerBase # <--- เพิ่มมาใหม่

# --- 1. ตั้งค่าหน้าจอและเชื่อมต่อ Supabase ---
st.set_page_config(page_title="Box Scanner", layout="wide")
st.title("📦 App สแกน Tracking และ Barcode")

@st.cache_resource
def init_supabase_client():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase_client()

# --- 2. สร้าง Session State ---
if "tracking_code" not in st.session_state:
    st.session_state.tracking_code = ""
if "product_barcode" not in st.session_state:
    st.session_state.product_barcode = ""
if "scan_count" not in st.session_state:
    st.session_state.scan_count = 0
if "current_user" not in st.session_state:
    st.session_state.current_user = ""

# --- 3. สร้าง Class สำหรับถอดรหัส Barcode (หัวใจของวิธีใหม่) ---
# เราจะสร้าง 2 Class แยกกันสำหรับ Tracking และ Barcode
# เพื่อให้มันไม่เขียนทับค่าของกันและกัน

class TrackingScanner(VideoTransformerBase):
    def __init__(self):
        self.found_code = None

    def transform(self, frame):
        img = frame.to_ndarray(format="bgr24")
        
        # ถอดรหัส Barcode/QR Code
        barcodes = decode(img)
        
        if barcodes:
            data = barcodes[0].data.decode("utf-8")
            # เมื่อสแกนเจอ ให้เก็บค่าใน session_state ทันที
            st.session_state.tracking_code = data
            self.found_code = data

        # วาดสี่เหลี่ยมรอบ Barcode ที่เจอ (ถ้าเจอ)
        if self.found_code:
            # ใส่ข้อความบนจอว่าสแกนเจอแล้ว
            cv2.putText(img, f"Found: {self.found_code}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        return img

class ProductScanner(VideoTransformerBase):
    def __init__(self):
        self.found_code = None

    def transform(self, frame):
        img = frame.to_ndarray(format="bgr24")
        
        barcodes = decode(img)
        
        if barcodes:
            data = barcodes[0].data.decode("utf-8")
            st.session_state.product_barcode = data
            self.found_code = data

        if self.found_code:
            cv2.putText(img, f"Found: {self.found_code}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
        return img

# --- 4. แบ่งหน้าจอด้วย Tabs ---
tab1, tab2 = st.tabs(["📷 สแกนกล่อง", "📊 ดูข้อมูลและดาวน์โหลด"])

# --- TAB 1: หน้าสแกน ---
with tab1:
    st.header("บันทึกการสแกน")

    user = st.text_input("ชื่อผู้ใช้งาน (User):", st.session_state.current_user)
    st.session_state.current_user = user # อัปเดต User ใน state

    if not user:
        st.warning("กรุณาป้อนชื่อผู้ใช้งานก่อนเริ่มสแกน")
    else:
        st.metric("จำนวนกล่องที่สแกน (ในรอบนี้)", st.session_state.scan_count)
        
        col1, col2 = st.columns(2)

        # --- ส่วนสแกน Tracking (QR Code) ---
        with col1:
            st.subheader("1. สแกน Tracking (QR Code)")
            
            # เปิดกล้องด้วย webrtc_streamer
            webrtc_streamer(
                key="tracking_scanner",
                mode=WebRtcMode.SENDONLY, # ส่งภาพจากกล้องผู้ใช้อย่างเดียว
                video_transformer_factory=TrackingScanner, # ใช้ Class ที่เราสร้าง
                media_stream_constraints={"video": True, "audio": False},
                async_processing=True,
            )
            
            # แสดงผลค่าที่สแกนได้จาก session_state
            if st.session_state.tracking_code:
                st.success(f"Tracking ที่สแกนได้: **{st.session_state.tracking_code}**")

        # --- ส่วนสแกน Barcode (EAN) ---
        with col2:
            st.subheader("2. สแกน Barcode สินค้า")

            webrtc_streamer(
                key="product_scanner",
                mode=WebRtcMode.SENDONLY,
                video_transformer_factory=ProductScanner, # ใช้ Class แยกกัน
                media_stream_constraints={"video": True, "audio": False},
                async_processing=True,
            )
            
            if st.session_state.product_barcode:
                st.success(f"Barcode ที่สแกนได้: **{st.session_state.product_barcode}**")

        st.divider()

        # --- ส่วนบันทึกข้อมูล (เหมือนเดิม) ---
        if st.session_state.tracking_code and st.session_state.product_barcode:
            if st.button("💾 บันทึกข้อมูลกล่องนี้", type="primary", use_container_width=True):
                try:
                    data_to_insert = {
                        "user_id": st.session_state.current_user,
                        "tracking_code": st.session_state.tracking_code,
                        "product_barcode": st.session_state.product_barcode
                    }
                    
                    supabase.table("scans").insert(data_to_insert).execute()
                    
                    st.success("บันทึกข้อมูลสำเร็จ!")
                    st.session_state.scan_count += 1
                    
                    # เคลียร์ค่าเพื่อรอสแกนกล่องต่อไป
                    st.session_state.tracking_code = ""
                    st.session_state.product_barcode = ""
                    
                    st.rerun()

                except Exception as e:
                    st.error(f"เกิดข้อผิดพลาดในการบันทึก: {e}")
        else:
            st.info("กรุณาสแกนทั้ง Tracking และ Barcode ให้ครบถ้วนก่อนบันทึก (ค่าที่สแกนได้จะแสดงใต้กล้อง)")

# --- TAB 2: หน้าดูข้อมูลและดาวน์โหลด (เหมือนเดิม) ---
with tab2:
    st.header("ค้นหาและดาวน์โหลดข้อมูล")

    with st.expander("ตัวกรองข้อมูล (Filter)", expanded=True):
        col_f1, col_f2 = st.columns(2)
        
        with col_f1:
            filter_user = st.text_input("กรองตาม User (เว้นว่างเพื่อแสดงทั้งหมด)")
        with col_f2:
            filter_date = st.date_input("กรองตามวันที่", value=None) 

    try:
        query = supabase.table("scans").select("*").order("created_at", desc=True)
        
        if filter_user:
            query = query.eq("user_id", filter_user)
        if filter_date:
            start_date = str(filter_date) + " 00:00:00"
            end_date = str(filter_date) + " 23:59:59"
            query = query.gte("created_at", start_date).lte("created_at", end_date)
            
        data = query.execute().data
        
        if data:
            df = pd.DataFrame(data)
            st.dataframe(df, use_container_width=True)
            
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
