import streamlit as st
import pandas as pd
import gspread
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from datetime import datetime, timedelta
import time
import pytz
import uuid
from PIL import Image
import io
from googleapiclient.errors import HttpError
import json

# --- IMPORT LIBRARY กล้อง ---
try:
    from streamlit_back_camera_input import back_camera_input
    from pyzbar.pyzbar import decode
except ImportError:
    st.error("⚠️ กรุณาติดตั้ง library: streamlit-back-camera-input, pyzbar, Pillow")
    st.stop()

# --- PAGE CONFIG ---
st.set_page_config(page_title="New App: Scan & Pack", page_icon="✨", layout="wide")

# --- CSS STYLING ---
st.markdown("""
<style>
div.block-container { padding-top: 1rem; padding-bottom: 2rem; }
.user-header {
    background-color: #e3f2fd; padding: 15px; border-radius: 10px;
    margin-bottom: 15px; border: 1px solid #bbdefb; color: #0d47a1;
}
.vehicle-box {
    background-color: #fff3e0; padding: 10px; border-radius: 8px;
    border: 1px solid #ffe0b2; margin-bottom: 10px;
}
iframe[title="streamlit_back_camera_input.back_camera_input"] {
    min-height: 300px !important; height: 100% !important;
}
.status-step {
    font-size: 1.2rem; font-weight: bold; padding: 10px;
    border-radius: 5px; margin: 5px 0;
}
.step-pending { background-color: #f5f5f5; color: #9e9e9e; border: 1px dashed #bdbdbd; }
.step-done { background-color: #c8e6c9; color: #2e7d32; border: 1px solid #81c784; }
.step-active { background-color: #bbdefb; color: #0d47a1; border: 2px solid #1976d2; }
.final-cam-box {
    border: 3px solid #ff9800; padding: 20px; border-radius: 15px;
    text-align: center; background-color: #fff3e0; margin-top: 20px;
}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 👇 แก้ไข Configuration ตรงนี้ (สำหรับ App ใหม่)
# ==========================================
NEW_MAIN_FOLDER_ID = '1sZQKOuw4YGazuy4euk4ns7nLr7Zie6cm' 
NEW_SHEET_ID = '1Om9qwShA3hBQgKJPQNbJgDPInm9AQ2hY5Z8OuOpkF08'

# ชื่อแผ่นงานในไฟล์ Google Sheet ใหม่ (ต้องสร้างรอไว้)
DATA_SHEET_NAME = 'Data_Pack'    
USER_SHEET_NAME = 'User_MKP'         
# ==========================================

# --- AUTHENTICATION (OAUTH - ใช้ User เดิม) ---
def get_credentials():
    try:
        if "oauth" in st.secrets:
            info = st.secrets["oauth"]
            creds = Credentials(
                None,
                refresh_token=info["refresh_token"],
                token_uri="https://oauth2.googleapis.com/token",
                client_id=info["client_id"],
                client_secret=info["client_secret"],
                scopes=[
                    "https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive"
                ]
            )
            return creds
        else:
            st.error("❌ ไม่พบข้อมูล [oauth] ใน Secrets")
            return None
    except Exception as e:
        st.error(f"❌ Error Credentials: {e}")
        return None

def get_sheet_connection(sheet_name):
    creds = get_credentials()
    if creds:
        gc = gspread.authorize(creds)
        try: 
            sh = gc.open_by_key(NEW_SHEET_ID) # เชื่อมต่อ Sheet ใหม่
            try:
                return sh.worksheet(sheet_name)
            except:
                # ถ้าหาแผ่นงานไม่เจอ ให้สร้างใหม่
                return sh.add_worksheet(title=sheet_name, rows="1000", cols="20")
        except Exception as e: 
            st.error(f"Google Sheet Error (ตรวจสอบ ID ใหม่): {e}")
            return None
    return None

def authenticate_drive():
    try:
        creds = get_credentials()
        if creds: return build('drive', 'v3', credentials=creds)
        return None
    except Exception as e:
        st.error(f"Error Drive: {e}")
        return None

# --- FOLDER STRUCTURE LOGIC (เก็บใน Folder ใหม่) ---
def get_target_folder_structure(service, grouping_name, main_parent_id):
    """
    สร้าง Folder: ปี > เดือน > วันที่ > grouping_name (เช่น ทะเบียนรถ)
    """
    now = datetime.utcnow() + timedelta(hours=7)
    year_str = now.strftime("%Y")
    month_str = now.strftime("%m")
    date_str = now.strftime("%d-%m-%Y")

    def _get_or_create(parent_id, name):
        q = f"name = '{name}' and '{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        res = service.files().list(q=q, fields="files(id)").execute()
        files = res.get('files', [])
        if files: return files[0]['id']
        
        meta = {'name': name, 'parents': [parent_id], 'mimeType': 'application/vnd.google-apps.folder'}
        folder = service.files().create(body=meta, fields='id').execute()
        return folder.get('id')

    # Step 1-3: Year > Month > Date
    year_id = _get_or_create(main_parent_id, year_str)
    month_id = _get_or_create(year_id, month_str)
    date_id = _get_or_create(month_id, date_str)

    # Step 4: Group Folder (ใช้ทะเบียนรถ หรือ ชื่อกลุ่มงาน)
    time_suffix = now.strftime("%H-%M")
    clean_name = str(grouping_name).replace("/", "-").strip()
    folder_name = f"{clean_name}_{time_suffix}"
    
    meta_group = {'name': folder_name, 'parents': [date_id], 'mimeType': 'application/vnd.google-apps.folder'}
    target_folder = service.files().create(body=meta_group, fields='id').execute()
    
    return target_folder.get('id')

def upload_photo(service, file_obj, filename, folder_id):
    try:
        file_metadata = {'name': filename, 'parents': [folder_id]}
        
        if isinstance(file_obj, bytes): 
            media_body = io.BytesIO(file_obj)
        else: 
            media_body = file_obj 
            
        media = MediaIoBaseUpload(media_body, mimetype='image/jpeg', chunksize=1024*1024, resumable=True)
        
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        return file.get('id')

    except HttpError as error:
        error_reason = json.loads(error.content.decode('utf-8'))
        print(f"❌ DRIVE ERROR: {error_reason}")
        st.error(f"Google Drive Error: {error_reason}")
        raise error
    except Exception as e:
        print(f"❌ GENERAL ERROR: {e}")
        raise e

# --- CORE FUNCTIONS (เหมือนเดิม) ---
def verify_user_login(user):
    try:
        ws = get_sheet_connection(USER_SHEET_NAME)
        if ws:
            all_records = ws.get_all_values()
            if not all_records: return False, None
            headers = all_records[0]
            target_id = str(user).strip().lower()
            
            id_col_idx = -1
            possible_id = ["id", "user", "user_id", "emp_id", "code", "รหัส"]
            for i, h in enumerate(headers):
                if str(h).lower().strip() in possible_id: id_col_idx = i; break
            if id_col_idx == -1: id_col_idx = 0

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
            # ถ้า Sheet ว่าง ให้เติม Header
            if len(ws.get_all_values()) == 0:
                ws.append_row(["Timestamp", "User ID", "User Name", "Tracking", "Barcode", "Status", "Qty", "Mode", "License Plate", "Image Link"])
            
            rows = []
            tz = pytz.timezone('Asia/Bangkok')
            ts = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
            
            for item in data_list:
                img_link = item.get('image_link', '-')
                rows.append([ts, item['user'], item['user_name'], item['tracking'], item['barcode'], "Normal", 1, item['mode'], item['license_plate'], img_link])
            
            ws.append_rows(rows)
            return True
    except Exception as e:
        st.error(f"Save Sheet Error: {e}")
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
        'user': "", 'user_name': "", 'staged_data': [],
        'locked_barcode': "", 'scan_error': None, 'play_sound': None,
        'reset_key': 0, 'cam_counter': 0,
        'scan_step': 1, 'temp_track': "", 'temp_prod': "",
        'is_saving_mode': False
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
        "id": str(uuid.uuid4()), "user": st.session_state.user, "user_name": st.session_state.user_name,
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
    for k in ['user', 'user_name', 'staged_data', 'locked_barcode', 'temp_track', 'temp_prod']:
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
    
    with st.spinner("🚀 กำลังบันทึกข้อมูลและอัปโหลดรูปภาพ..."):
        drive_service = authenticate_drive()
        
        uploaded_link = "-"
        # 1. Upload Photo to NEW Folder (Year > Month > Date Structure)
        if photo_bytes and drive_service:
            # ใช้ NEW_MAIN_FOLDER_ID ที่ตั้งค่าไว้ข้างบน
            target_folder_id = get_target_folder_structure(drive_service, current_lp, NEW_MAIN_FOLDER_ID)
            
            ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            lp_clean = str(current_lp).replace(" ", "_")
            fname = f"EVIDENCE_{lp_clean}_{ts_str}.jpg"
            
            upload_id = upload_photo(drive_service, photo_bytes, fname, target_folder_id)
            if upload_id:
                uploaded_link = f"https://drive.google.com/open?id={upload_id}"
                st.toast("✅ อัปโหลดรูปภาพสำเร็จ")
            else:
                st.error("⚠️ อัปโหลดรูปภาพไม่สำเร็จ")
        
        # เพิ่ม Link รูปภาพ
        for item in st.session_state.staged_data:
            item['image_link'] = uploaded_link

        # 2. Save Data to NEW Sheet
        if save_batch_to_sheet(st.session_state.staged_data[::-1]):
            st.success("🎉 บันทึกข้อมูลสำเร็จ!")
            # Reset
            st.session_state.staged_data = []
            st.session_state.reset_key += 1
            st.session_state.cam_counter += 1
            st.session_state.scan_step = 1
            st.session_state.temp_track = ""
            st.session_state.temp_prod = ""
            st.session_state.is_saving_mode = False 
            
            load_data_from_sheet.clear()
            st.balloons()
            time.sleep(1.5)
            st.rerun()
        else:
            st.error("❌ บันทึกข้อมูลไม่สำเร็จ กรุณาลองใหม่")

# ================= MAIN APP =================
st.title("📦 New App: Scan & Pack")
play_audio_feedback()

# --- LOGIN ---
if not st.session_state.user:
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        st.info("🔒 กรุณาสแกนรหัสพนักงาน")
        cam_key = f"cam_login_{st.session_state.cam_counter}"
        login_img = back_camera_input("แตะเพื่อสแกนบัตร", key=cam_key)
        scanned_id = process_camera_scan(login_img)
        
        if scanned_id:
            found, name = verify_user_login(scanned_id)
            if found:
                st.session_state.user = scanned_id; st.session_state.user_name = name
                st.session_state.cam_counter += 1; st.rerun()
            else: st.error("❌ ไม่พบรหัสพนักงาน (ตรวจสอบไฟล์ User ใหม่)")
        
        u_in = st.text_input("หรือพิมพ์รหัส", key="login_input")
        if st.button("Login") and u_in:
             found, name = verify_user_login(u_in)
             if found:
                st.session_state.user = u_in; st.session_state.user_name = name
                st.rerun()
else:
    # --- LOGGED IN ---
    with st.container():
        st.markdown(f"""
        <div class="user-header">
            <b>👤 {st.session_state.user_name}</b> ({st.session_state.user})
        </div>""", unsafe_allow_html=True)
        col_nul, col_out = st.columns([4,1])
        with col_out: st.button("🚪 Logout", on_click=logout_callback, use_container_width=True)

    t1, t2 = st.tabs(["📷 Scan Center", "📊 History"])

    with t1:
        if st.session_state.is_saving_mode:
            # === หน้าถ่ายรูปปิดงาน ===
            st.markdown('<div class="final-cam-box">', unsafe_allow_html=True)
            st.markdown("### 📸 กรุณาถ่ายรูปปิดตู้/ปิดงาน")
            st.caption("ถ่ายรูปสภาพสินค้าที่แพ็คเสร็จแล้วเพื่อเป็นหลักฐาน")
            
            evidence_photo = st.camera_input("กดปุ่มถ่ายรูป", label_visibility="collapsed")
            
            c_conf1, c_conf2 = st.columns(2)
            with c_conf1:
                if st.button("⬅️ ย้อนกลับ", use_container_width=True):
                    st.session_state.is_saving_mode = False
                    st.rerun()
            with c_conf2:
                if evidence_photo:
                    if st.button("🚀 ยืนยัน Upload & Save", type="primary", use_container_width=True):
                        lp_for_save = "Unknown"
                        if st.session_state.staged_data:
                            lp_for_save = st.session_state.staged_data[0]['license_plate']
                        
                        final_process_save(evidence_photo.getvalue(), lp_for_save)
                else:
                    st.warning("⚠️ กรุณาถ่ายรูปก่อนกดบันทึก")
            st.markdown('</div>', unsafe_allow_html=True)

            st.markdown("---")
            st.subheader("รายการที่จะบันทึก:")
            st.dataframe(pd.DataFrame(st.session_state.staged_data)[['tracking', 'barcode', 'license_plate']], use_container_width=True)

        else:
            # === หน้าสแกนปกติ ===
            st.markdown('<div class="vehicle-box">', unsafe_allow_html=True)
            c_v1, c_v2 = st.columns([1, 4])
            with c_v1: st.markdown("### 🚛")
            with c_v2:
                current_lp = st.text_input("ทะเบียนรถ", placeholder="ระบุทะเบียน...", key=f"lp_{st.session_state.reset_key}")
            st.markdown('</div>', unsafe_allow_html=True)

            if st.session_state.scan_error:
                st.error(st.session_state.scan_error)
                if st.button("ล้างข้อความ"): st.session_state.scan_error = None; st.rerun()

            mode = st.radio("โหมดการทำงาน:", ["🚀 งาน Lot (Mode A)", "📦 งานเดี่ยว (Mode B)"], horizontal=True)
            st.divider()
            
            if "Mode A" in mode:
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
                
                with st.expander("⌨️ พิมพ์เอง (Mode A)"):
                    with st.form("manual_a_form", clear_on_submit=True):
                        if not st.session_state.locked_barcode:
                            st.markdown("**ระบุ Barcode สินค้าหลัก (UPC):**")
                            man_input_a = st.text_input("UPC / Barcode", key="man_a_upc")
                            submit_label_a = "🔒 ล็อค UPC"
                        else:
                            st.markdown(f"**ระบุ Tracking สำหรับ:** `{st.session_state.locked_barcode}`")
                            man_input_a = st.text_input("Tracking ID", key="man_a_track")
                            submit_label_a = "📥 บันทึก Tracking"

                        if st.form_submit_button(submit_label_a):
                            if man_input_a:
                                handle_scan_mode_a(man_input_a, current_lp)
                                st.rerun()

            else:
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

                with st.expander("⌨️ พิมพ์เอง (Mode B)"):
                    with st.form("manual_b_form", clear_on_submit=True):
                        m_track = st.text_input("Tracking")
                        m_prod = st.text_input("Barcode")
                        if st.form_submit_button("บันทึก"):
                            if m_track and m_prod:
                                add_to_staging(m_track, m_prod, "Mode B", current_lp); st.rerun()

            cnt = len(st.session_state.staged_data)
            c_h1, c_h2 = st.columns([3, 1])
            with c_h1: st.subheader(f"📋 รายการรอ ({cnt})")
            with c_h2:
                if cnt > 0:
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
