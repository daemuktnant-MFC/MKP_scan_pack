import streamlit as st
import pandas as pd
import gspread
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from datetime import datetime
import time
import pytz
import uuid
from PIL import Image
import io

# --- IMPORT LIBRARY ---
try:
    from streamlit_back_camera_input import back_camera_input
    from pyzbar.pyzbar import decode
except ImportError:
    st.error("⚠️ กรุณาติดตั้ง library: streamlit-back-camera-input, pyzbar, Pillow")
    st.stop()

# --- PAGE CONFIG ---
st.set_page_config(page_title="MKP Scan & Pack", page_icon="📦", layout="wide")

# --- CONFIGURATION ---
SHEET_ID = '1Om9qwShA3hBQgKJPQNbJgDPInm9AQ2hY5Z8OuOpkF08'
DATA_SHEET_NAME = 'Data_Pack'    
USER_SHEET_NAME = 'User_MKP'     
MAIN_FOLDER_NAME = 'MKP_app_data'       # Folder แม่
SUB_FOLDER_NAME = 'Backup_Picture'      # Folder ลูก

# --- CSS STYLING ---
st.markdown("""
<style>
div.block-container { padding-top: 1rem; padding-bottom: 2rem; }
.user-header {
    background-color: #f0f2f6; padding: 15px; border-radius: 10px;
    margin-bottom: 15px; border: 1px solid #dce4ef;
}
.vehicle-box {
    background-color: #e8f5e9; padding: 10px; border-radius: 8px;
    border: 1px solid #c8e6c9; margin-bottom: 10px;
}
iframe[title="streamlit_back_camera_input.back_camera_input"] {
    min-height: 300px !important; height: 100% !important;
}
.status-step {
    font-size: 1.2rem; font-weight: bold; padding: 10px;
    border-radius: 5px; margin: 5px 0;
}
.step-pending { background-color: #f5f5f5; color: #9e9e9e; border: 1px dashed #bdbdbd; }
.step-done { background-color: #d1c4e9; color: #512da8; border: 1px solid #673ab7; }
.step-active { background-color: #bbdefb; color: #0d47a1; border: 2px solid #1976d2; }
/* Style สำหรับหน้าถ่ายรูปปิดงาน */
.final-cam-box {
    border: 3px solid #4CAF50; padding: 20px; border-radius: 15px;
    text-align: center; background-color: #f1f8e9; margin-top: 20px;
}
</style>
""", unsafe_allow_html=True)

# --- GOOGLE SERVICES ---
def get_credentials():
    try:
        if "oauth" in st.secrets:
            info = st.secrets["oauth"]
            return Credentials(None, refresh_token=info["refresh_token"], token_uri="https://oauth2.googleapis.com/token", client_id=info["client_id"], client_secret=info["client_secret"])
    except: return None

def get_sheet_connection(sheet_name):
    creds = get_credentials()
    if creds:
        gc = gspread.authorize(creds)
        try: return gc.open_by_key(SHEET_ID).worksheet(sheet_name)
        except: return None
    return None

def get_drive_service():
    creds = get_credentials()
    if creds: return build('drive', 'v3', credentials=creds)
    return None

# [Logic ใหม่] จัดการ Folder ซ้อน Folder
def get_or_create_folder(service, folder_name, parent_id=None):
    # สร้าง Query เพื่อหา Folder
    query = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    
    results = service.files().list(q=query, fields="files(id)").execute()
    files = results.get('files', [])

    if not files:
        # ถ้าไม่เจอ ให้สร้างใหม่
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        if parent_id:
            file_metadata['parents'] = [parent_id]
            
        folder = service.files().create(body=file_metadata, fields='id').execute()
        return folder.get('id')
    else:
        return files[0]['id']

def upload_photo_to_drive(photo_bytes, filename):
    try:
        service = get_drive_service()
        if not service: return None
        
        # 1. หา/สร้าง Folder แม่ (MKP_app_data)
        main_folder_id = get_or_create_folder(service, MAIN_FOLDER_NAME)
        
        # 2. หา/สร้าง Folder ลูก (Backup_Picture) ใน Folder แม่
        target_folder_id = get_or_create_folder(service, SUB_FOLDER_NAME, parent_id=main_folder_id)

        # 3. Upload รูปภาพ
        media = MediaIoBaseUpload(io.BytesIO(photo_bytes), mimetype='image/jpeg')
        file_metadata = {
            'name': filename,
            'parents': [target_folder_id]
        }
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        return file.get('id')
    except Exception as e:
        print(f"Upload Error: {e}")
        return None

# --- CORE FUNCTIONS ---
def verify_user_login(user_id):
    try:
        ws = get_sheet_connection(USER_SHEET_NAME)
        if ws:
            all_records = ws.get_all_values()
            if not all_records: return False, None
            headers = all_records[0]
            target_id = str(user_id).strip().lower()
            
            # Find ID Column
            id_col_idx = -1
            possible_id = ["id", "user", "user_id", "emp_id", "code", "รหัส"]
            for i, h in enumerate(headers):
                if str(h).lower().strip() in possible_id: id_col_idx = i; break
            if id_col_idx == -1: id_col_idx = 0

            # Find Name Column
            name_col_idx = -1
            for i, h in enumerate(headers):
                if "name" in str(h).lower() or "ชื่อ" in str(h).lower(): name_col_idx = i; break
            if name_col_idx == -1: name_col_idx = 1 

            for row in all_records[1:]:
                while len(row) <= max(id_col_idx, name_col_idx): row.append("")
                sheet_id = str(row[id_col_idx]).strip().lower()
                if target_id == sheet_id or (target_id in sheet_id and len(target_id) > 2):
                    u_name = str(row[name_col_idx]).strip()
                    return True, u_name if u_name else "พนักงาน"
            return False, None
    except: return False, None
    return False, None

def save_batch_to_sheet(data_list):
    try:
        ws = get_sheet_connection(DATA_SHEET_NAME)
        if ws:
            rows = []
            tz = pytz.timezone('Asia/Bangkok')
            ts = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
            for item in data_list:
                rows.append([ts, item['user_id'], item['user_name'], item['tracking'], item['barcode'], "Normal", 1, item['mode'], item['license_plate']])
            ws.append_rows(rows)
            return True
    except: return False
    return False

@st.cache_data(ttl=30)
def load_data_from_sheet():
    try:
        ws = get_sheet_connection(DATA_SHEET_NAME)
        if ws:
            data = ws.get_all_values()
            if len(data) > 1:
                df = pd.DataFrame(data[1:], columns=data[0])
                df.columns = df.columns.str.strip()
                return df
    except: pass
    return pd.DataFrame()

# --- INIT SESSION ---
def init_session_state():
    keys = {
        'user_id': "", 'user_name': "", 'staged_data': [],
        'locked_barcode': "", 'scan_error': None, 'play_sound': None,
        'reset_key': 0, 'cam_counter': 0,
        'scan_step': 1, 'temp_track': "", 'temp_prod': "",
        'is_saving_mode': False # [เพิ่ม] สถานะสำหรับหน้าถ่ายรูปปิดงาน
    }
    for k, v in keys.items():
        if k not in st.session_state: st.session_state[k] = v

init_session_state()

# --- HELPERS ---
def process_camera_scan(image_input):
    if image_input:
        try:
            img = Image.open(image_input)
            decoded_objects = decode(img)
            if decoded_objects: return decoded_objects[0].data.decode("utf-8")
        except: pass
    return None

def play_audio_feedback():
    if st.session_state.play_sound == 'success':
        st.audio("https://www.soundjay.com/buttons/sounds/button-16.mp3", format="audio/mp3", autoplay=True)
    elif st.session_state.play_sound == 'error':
        st.audio("https://www.soundjay.com/buttons/sounds/button-10.mp3", format="audio/mp3", autoplay=True)
    st.session_state.play_sound = None

# --- LOGIC ---
def check_duplicate(tracking):
    for item in st.session_state.staged_data:
        if str(item['tracking']).strip() == str(tracking).strip():
            return True, f"⚠️ ซ้ำในรายการรอ! ({tracking})"
    df = load_data_from_sheet()
    if not df.empty:
        cols = df.columns
        t_col = next((c for c in cols if c in ['Tracking ID', 'Order ID', 'Tracking']), None)
        if t_col:
            if str(tracking).strip() in df[t_col].astype(str).str.strip().values:
                return True, f"⛔ เคยบันทึกไปแล้ว! ({tracking})"
    return False, ""

def add_to_staging(tracking, barcode, mode, license_plate):
    st.session_state.scan_error = None
    is_dup, msg = check_duplicate(tracking)
    if is_dup:
        st.session_state.scan_error = msg
        st.session_state.play_sound = 'error'
        st.toast(msg, icon="🚫")
        return False

    if not license_plate:
        st.toast("⚠️ กรุณาระบุทะเบียนรถ", icon="🚛")

    new_item = {
        "id": str(uuid.uuid4()), "user_id": st.session_state.user_id, "user_name": st.session_state.user_name,
        "license_plate": license_plate, "tracking": tracking, "barcode": barcode,
        "mode": mode, "time_scan": datetime.now().strftime("%H:%M:%S")
    }
    st.session_state.staged_data.insert(0, new_item)
    st.session_state.play_sound = 'success'
    st.toast(f"📥 เพิ่ม: {tracking}", icon="➕")
    return True

def delete_staging(item_id):
    st.session_state.staged_data = [d for d in st.session_state.staged_data if d['id'] != item_id]

def logout_callback():
    for k in ['user_id', 'user_name', 'staged_data', 'locked_barcode', 'temp_track', 'temp_prod']:
        st.session_state[k] = "" if isinstance(st.session_state[k], str) else []
    st.session_state.reset_key += 1; st.session_state.cam_counter += 1
    st.session_state.scan_step = 1; st.session_state.is_saving_mode = False
    load_data_from_sheet.clear()

# --- SCAN HANDLERS ---
def handle_scan_mode_b(scanned_val, current_lp):
    if st.session_state.scan_step == 1:
        st.session_state.temp_track = scanned_val
        st.session_state.scan_step = 2
        st.session_state.cam_counter += 1
        st.rerun()
    elif st.session_state.scan_step == 2:
        st.session_state.temp_prod = scanned_val
        if st.session_state.temp_track and st.session_state.temp_prod:
            success = add_to_staging(st.session_state.temp_track, st.session_state.temp_prod, "Mode B", current_lp)
            if success:
                st.session_state.temp_track = ""; st.session_state.temp_prod = ""; st.session_state.scan_step = 1
            else:
                st.session_state.scan_step = 1; st.session_state.temp_track = ""; st.session_state.temp_prod = ""
        st.session_state.cam_counter += 1
        st.rerun()

def handle_scan_mode_a(scanned_val, current_lp):
    if not st.session_state.locked_barcode:
        st.session_state.locked_barcode = scanned_val
        st.session_state.cam_counter += 1
        st.rerun()
    else:
        add_to_staging(scanned_val, st.session_state.locked_barcode, "Mode A", current_lp)
        st.session_state.cam_counter += 1
        st.rerun()

# --- SAVE & UPLOAD HANDLER ---
def final_process_save(photo_bytes, current_lp):
    if not st.session_state.staged_data: return
    
    with st.spinner("🚀 กำลังอัปโหลดรูปภาพและบันทึกข้อมูล..."):
        # 1. Upload Photo to Drive (Nested Folder)
        if photo_bytes:
            ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            lp_clean = str(current_lp).replace(" ", "_")
            fname = f"EVIDENCE_{lp_clean}_{ts_str}.jpg"
            upload_id = upload_photo_to_drive(photo_bytes, fname)
            if upload_id:
                st.toast("✅ อัปโหลดรูปภาพสำเร็จ")
            else:
                st.error("⚠️ อัปโหลดรูปภาพไม่สำเร็จ (แต่จะบันทึกข้อมูลต่อ)")
        
        # 2. Save Data to Sheet
        if save_batch_to_sheet(st.session_state.staged_data[::-1]):
            st.success("🎉 บันทึกข้อมูลสำเร็จเรียบร้อย!")
            # Reset All States
            st.session_state.staged_data = []
            st.session_state.reset_key += 1
            st.session_state.cam_counter += 1
            st.session_state.scan_step = 1
            st.session_state.temp_track = ""
            st.session_state.temp_prod = ""
            st.session_state.is_saving_mode = False # ออกจากโหมดถ่ายรูป
            
            load_data_from_sheet.clear()
            st.balloons()
            time.sleep(1.5)
            st.rerun()
        else:
            st.error("❌ บันทึกข้อมูลไม่สำเร็จ กรุณาลองใหม่")

# ================= MAIN APP =================
st.title("📦 MKP Scan & Pack")
play_audio_feedback()

# --- LOGIN ---
if not st.session_state.user_id:
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        st.info("🔒 กรุณาสแกนรหัสพนักงาน")
        cam_key = f"cam_login_{st.session_state.cam_counter}"
        login_img = back_camera_input("แตะเพื่อสแกนบัตร", key=cam_key)
        scanned_id = process_camera_scan(login_img)
        
        if scanned_id:
            found, name = verify_user_login(scanned_id)
            if found:
                st.session_state.user_id = scanned_id; st.session_state.user_name = name
                st.session_state.cam_counter += 1; st.rerun()
            else: st.error("❌ ไม่พบรหัสพนักงาน")
        
        u_in = st.text_input("หรือพิมพ์รหัส", key="login_input")
        if st.button("Login") and u_in:
             found, name = verify_user_login(u_in)
             if found:
                st.session_state.user_id = u_in; st.session_state.user_name = name
                st.rerun()
else:
    # --- LOGGED IN ---
    with st.container():
        st.markdown(f"""
        <div class="user-header">
            <b>👤 {st.session_state.user_name}</b> ({st.session_state.user_id})
        </div>""", unsafe_allow_html=True)
        col_nul, col_out = st.columns([4,1])
        with col_out: st.button("🚪 Logout", on_click=logout_callback, use_container_width=True)

    t1, t2 = st.tabs(["📷 Scan Center", "📊 History"])

    with t1:
        # Check if we are in Saving Mode (Photo Mode)
        if st.session_state.is_saving_mode:
            # === หน้าถ่ายรูปปิดงาน (Saving Mode) ===
            st.markdown('<div class="final-cam-box">', unsafe_allow_html=True)
            st.markdown("### 📸 กรุณาถ่ายรูปปิดตู้/ปิดงาน")
            st.caption("ถ่ายรูปสภาพสินค้าที่แพ็คเสร็จแล้วเพื่อเป็นหลักฐาน")
            
            # ใช้ st.camera_input ปกติเพื่อให้เห็นภาพพรีวิวชัดเจน
            evidence_photo = st.camera_input("กดปุ่มถ่ายรูป", label_visibility="collapsed")
            
            c_conf1, c_conf2 = st.columns(2)
            with c_conf1:
                if st.button("⬅️ ย้อนกลับ", use_container_width=True):
                    st.session_state.is_saving_mode = False
                    st.rerun()
            with c_conf2:
                # ปุ่มยืนยันจะทำงานได้เมื่อถ่ายรูปแล้ว
                if evidence_photo:
                    if st.button("🚀 ยืนยัน Upload & Save", type="primary", use_container_width=True):
                        # ดึงค่าทะเบียนรถปัจจุบัน (ต้องส่งผ่านเพราะ reset_key อาจเปลี่ยนถ้าไม่ได้เก็บไว้)
                        # ใช้ค่าล่าสุดจาก session state หรือ input
                        # หมายเหตุ: เนื่องจาก input หายไปจากหน้าจอ ค่าอาจหายไป
                        # แต่เรายังเข้าถึง staged_data ได้ ทะเบียนรถเก็บอยู่ใน staged_data แล้ว
                        # ดึงทะเบียนจากรายการแรกของ staged_data มาใช้ตั้งชื่อไฟล์
                        lp_for_save = "Unknown"
                        if st.session_state.staged_data:
                            lp_for_save = st.session_state.staged_data[0]['license_plate']
                        
                        final_process_save(evidence_photo.getvalue(), lp_for_save)
                else:
                    st.warning("⚠️ กรุณาถ่ายรูปก่อนกดบันทึก")
            st.markdown('</div>', unsafe_allow_html=True)

            # Show preview data
            st.markdown("---")
            st.subheader("รายการที่จะบันทึก:")
            st.dataframe(pd.DataFrame(st.session_state.staged_data)[['tracking', 'barcode', 'license_plate']], use_container_width=True)

        else:
            # === หน้าสแกนปกติ (Scanning Mode) ===
            
            # 1. Vehicle
            st.markdown('<div class="vehicle-box">', unsafe_allow_html=True)
            c_v1, c_v2 = st.columns([1, 4])
            with c_v1: st.markdown("### 🚛")
            with c_v2:
                current_lp = st.text_input("ทะเบียนรถ", placeholder="ระบุทะเบียน...", key=f"lp_{st.session_state.reset_key}")
            st.markdown('</div>', unsafe_allow_html=True)

            if st.session_state.scan_error:
                st.error(st.session_state.scan_error)
                if st.button("ล้างข้อความ"): st.session_state.scan_error = None; st.rerun()

            # 2. Mode Selection
            mode = st.radio("โหมดการทำงาน:", ["🚀 งาน Lot (Mode A)", "📦 งานเดี่ยว (Mode B)"], horizontal=True)
            
            st.divider()
            
            if "Mode A" in mode:
                # Mode A Logic
                if not st.session_state.locked_barcode:
                    st.info("🟡 สถานะ: รอสแกน UPC")
                    cam_label = "📸 สแกน UPC"
                else:
                    st.success(f"🔒 สินค้า: {st.session_state.locked_barcode}")
                    st.info("🟢 สถานะ: รอสแกน Tracking")
                    cam_label = "📸 สแกน Tracking"
                    if st.button("เปลี่ยน UPC"):
                        st.session_state.locked_barcode = ""; st.rerun()

                img_input = back_camera_input(cam_label, key=f"cam_A_{st.session_state.cam_counter}")
                res = process_camera_scan(img_input)
                if res: handle_scan_mode_a(res, current_lp)

                 with st.expander("⌨️ พิมพ์เอง"):
                    with st.form("manual_b_form", clear_on_submit=True):
                        m_track = st.text_input("Tracking")
                        m_prod = st.text_input("Barcode")
                        if st.form_submit_button("บันทึก"):
                            if m_track and m_prod:
                                add_to_staging(m_track, m_prod, "Mode B", current_lp); st.rerun()

            else:
                # Mode B Logic
                c_s1, c_s2 = st.columns(2)
                with c_s1:
                    if st.session_state.scan_step == 1:
                        st.markdown(f'<div class="status-step step-active">1. รอสแกน Tracking ⏳</div>', unsafe_allow_html=True)
                    else:
                        st.markdown(f'<div class="status-step step-done">Tracking: {st.session_state.temp_track} ✅</div>', unsafe_allow_html=True)
                
                with c_s2:
                    if st.session_state.scan_step == 1:
                        st.markdown(f'<div class="status-step step-pending">2. รอ Barcode</div>', unsafe_allow_html=True)
                    else:
                        st.markdown(f'<div class="status-step step-active">2. รอสแกน Barcode ⏳</div>', unsafe_allow_html=True)

                if st.session_state.scan_step == 2:
                    if st.button("❌ ยกเลิก/เริ่มใหม่"):
                        st.session_state.scan_step = 1; st.session_state.temp_track = ""; st.session_state.temp_prod = ""; st.rerun()

                cam_label = "📸 สแกน Tracking ID" if st.session_state.scan_step == 1 else "📸 สแกน Barcode สินค้า"

                img_input = back_camera_input(cam_label, key=f"cam_B_{st.session_state.cam_counter}")
                res = process_camera_scan(img_input)
                if res: handle_scan_mode_b(res, current_lp)

                with st.expander("⌨️ พิมพ์เอง"):
                    with st.form("manual_b_form", clear_on_submit=True):
                        m_track = st.text_input("Tracking")
                        m_prod = st.text_input("Barcode")
                        if st.form_submit_button("บันทึก"):
                            if m_track and m_prod:
                                add_to_staging(m_track, m_prod, "Mode B", current_lp); st.rerun()

            # ================= STAGING AREA =================
            st.markdown("---")
            cnt = len(st.session_state.staged_data)
            
            c_h1, c_h2 = st.columns([3, 1])
            with c_h1: st.subheader(f"📋 รายการรอ ({cnt})")
            
            with c_h2:
                if cnt > 0:
                    # ปุ่ม Save จะเปลี่ยนหน้าที่ -> เป็นแค่ปุ่มเข้าสู่โหมดถ่ายรูป
                    if st.button(f"📸 ถ่ายรูป & บันทึก ({cnt})", type="primary", use_container_width=True):
                        st.session_state.is_saving_mode = True
                        st.rerun()

            if cnt > 0:
                with st.container(border=True):
                    cols = st.columns([1, 2, 3, 3, 1])
                    for col, h in zip(cols, ["เวลา", "ทะเบียน", "Tracking", "Barcode", "ลบ"]): col.markdown(f"**{h}**")
                    st.divider()
                    for item in st.session_state.staged_data:
                        c1, c2, c3, c4, c5 = st.columns([1, 2, 3, 3, 1])
                        c1.caption(item['time_scan'])
                        c2.caption(item['license_plate'])
                        c3.write(item['tracking'])
                        c4.write(item['barcode'])
                        c5.button("❌", key=f"d_{item['id']}", on_click=delete_staging, args=(item['id'],))

    with t2:
        if st.button("🔄 Refresh"): load_data_from_sheet.clear(); st.rerun()
        df = load_data_from_sheet()
        if not df.empty: st.dataframe(df.tail(15), use_container_width=True)
