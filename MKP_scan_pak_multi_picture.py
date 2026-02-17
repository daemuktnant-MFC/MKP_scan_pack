import streamlit as st
import pandas as pd
import gspread
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from datetime import datetime, timedelta
from PIL import Image
from pyzbar.pyzbar import decode 
import io 
import time
from googleapiclient.errors import HttpError
import json
import base64
import tempfile # [NEW] สำหรับจัดการไฟล์ชั่วคราว
import os      # [NEW] สำหรับจัดการไฟล์

# --- IMPORT LIBRARY กล้อง ---
try:
    from streamlit_back_camera_input import back_camera_input
except ImportError:
    st.error("⚠️ ต้องเพิ่ม 'streamlit-back-camera-input' ใน requirements.txt")
    st.stop()

# --- [NEW] IMPORT MOVIEPY สำหรับย่อวิดีโอ ---
try:
    from moviepy.editor import VideoFileClip
except ImportError:
    # ถ้ายังไม่ลง moviepy ระบบจะยังทำงานได้ แต่ฟังก์ชันย่อวิดีโอจะใช้ไม่ได้
    pass

# --- CSS HACK ---
st.markdown(
    """
    <style>
    h1 { font-size: 14px !important; } 
    h2 { font-size: 12px !important; } 
    h3 { font-size: 10px !important; } 
    h4 { font-size: 9px !important; } 
    
    iframe[title="streamlit_back_camera_input.back_camera_input"] {
        min-height: 450px !important; 
        height: 150% !important;
    }
    div[data-testid="stDataFrame"] { width: 100%; }
    div.stButton > button:disabled {
        background-color: #cccccc;
        color: #666666;
        cursor: not-allowed;
    }
    div[data-testid="stFileUploader"] {
        padding: 10px;
        border: 1px dashed #ccc;
        border-radius: 5px;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# --- CONFIGURATION ---
MAIN_FOLDER_ID = '1sZQKOuw4YGazuy4euk4ns7nLr7Zie6cm'
LOG_SHEET_ID = '1tZfX9I6Ntbo-Jf2_rcqBc2QYUrCCCSAx8K4YBkly92c' 
ORDER_CHECK_SHEET_ID = '1Om9qwShA3hBQgKJPQNbJgDPInm9AQ2hY5Z8OuOpkF08' 
ORDER_DATA_SHEET_NAME = 'Order_Data'
LOG_SHEET_NAME = 'Logs'
RIDER_SHEET_NAME = 'Rider_Logs'
USER_SHEET_NAME = 'User'

# --- SOUND HELPER ---
def play_sound(status='success'):
    sound_files = {'scan': 'beep.mp3', 'success': 'success.mp3', 'error': 'error.mp3'}
    backup_urls = {
        'scan': "https://www.myinstants.com/media/sounds/barcode-scanner-beep-sound.mp3",
        'success': "https://www.myinstants.com/media/sounds/success-sound-effect.mp3",
        'error': "https://www.myinstants.com/media/sounds/error_CDOxCNm.mp3"
    }
    target_file = sound_files.get(status, 'beep.mp3')
    try:
        with open(target_file, "rb") as f:
            data = f.read(); b64 = base64.b64encode(data).decode()
            md = f"""<audio autoplay><source src="data:audio/mp3;base64,{b64}" type="audio/mp3"></audio>"""
            st.markdown(md, unsafe_allow_html=True)
    except FileNotFoundError:
        sound_url = backup_urls.get(status, backup_urls['scan'])
        st.markdown(f"""<audio autoplay><source src="{sound_url}" type="audio/mp3"></audio>""", unsafe_allow_html=True)

# --- AUTHENTICATION ---
def get_credentials():
    try:
        if "oauth" in st.secrets:
            info = st.secrets["oauth"]
            creds = Credentials(None, refresh_token=info["refresh_token"], token_uri="https://oauth2.googleapis.com/token", client_id=info["client_id"], client_secret=info["client_secret"], scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
            return creds
        else:
            st.error("❌ ไม่พบข้อมูล [oauth] ใน Secrets")
            return None
    except Exception as e:
        st.error(f"❌ Error Credentials: {e}"); return None

def authenticate_drive():
    try:
        creds = get_credentials()
        if creds: return build('drive', 'v3', credentials=creds)
        return None
    except Exception as e:
        st.error(f"Error Drive: {e}"); return None

# --- GOOGLE SERVICES ---
@st.cache_data(ttl=600)
def load_sheet_data(sheet_name, spreadsheet_key): 
    try:
        creds = get_credentials()
        if not creds: return pd.DataFrame()
        gc = gspread.authorize(creds)
        try: sh = gc.open_by_key(spreadsheet_key)
        except Exception as e: st.error(f"❌ เปิดไฟล์ Google Sheet ไม่ได้: {e}"); return pd.DataFrame()
        try:
            if isinstance(sheet_name, int): worksheet = sh.get_worksheet(sheet_name)
            else: worksheet = sh.worksheet(sheet_name)
        except Exception as e: st.error(f"❌ ไม่พบ Tab '{sheet_name}': {e}"); return pd.DataFrame()
        
        rows = worksheet.get_all_values()
        if len(rows) > 1:
            headers = rows[0]; data = rows[1:]
            seen = {}; unique_headers = []
            for col in headers:
                clean_col = col.strip()
                if not clean_col: clean_col = "Untitled" 
                if clean_col in seen: seen[clean_col] += 1; unique_headers.append(f"{clean_col}_{seen[clean_col]}")
                else: seen[clean_col] = 0; unique_headers.append(clean_col)
            df = pd.DataFrame(data, columns=unique_headers)
            for col in df.columns:
                col_lower = col.lower()
                if 'tracking' in col_lower or ('order' in col_lower and 'id' in col_lower): df.rename(columns={col: 'Tracking'}, inplace=True)
                elif 'barcode' in col_lower: df.rename(columns={col: 'Barcode'}, inplace=True); df['Barcode'] = df['Barcode'].astype(str).str.replace(r'\.0$', '', regex=True)
                elif col == 'Name' or 'product name' in col_lower: df.rename(columns={col: 'Product Name'}, inplace=True)
                elif 'qty' in col_lower or 'quantity' in col_lower: df.rename(columns={col: 'Qty'}, inplace=True)
            return df
        return pd.DataFrame()
    except Exception as e: st.error(f"❌ Load Error Other: {e}"); return pd.DataFrame()

@st.cache_data(ttl=30)
def load_rider_history():
    try:
        creds = get_credentials(); gc = gspread.authorize(creds); sh = gc.open_by_key(LOG_SHEET_ID) 
        try:
            worksheet = sh.worksheet(RIDER_SHEET_NAME); records = worksheet.get_all_records()
            if records:
                df = pd.DataFrame(records); target_col = None
                for col in df.columns:
                    if "order" in col.lower() and "id" in col.lower(): target_col = col; break
                if target_col: return df[target_col].astype(str).str.strip().str.upper().tolist()
        except: pass 
        return []
    except: return []

# --- MANAGE USERS ---
def add_new_user_to_sheet(user_id, password, name, role):
    try:
        creds = get_credentials(); gc = gspread.authorize(creds); sh = gc.open_by_key(ORDER_CHECK_SHEET_ID); ws = sh.worksheet(USER_SHEET_NAME)
        existing_ids = ws.col_values(1)
        clean_existing = [str(x).strip().lower() for x in existing_ids if str(x).strip() != '']
        clean_new_id = str(user_id).strip().lower()
        if clean_new_id in clean_existing: return False, f"❌ ID '{user_id}' มีอยู่ในระบบแล้ว"
        ws.append_row([str(user_id).strip(), str(password).strip(), str(name).strip(), str(role)])
        load_sheet_data.clear(); return True, f"✅ เพิ่มพนักงาน {name} ({role}) เรียบร้อย"
    except Exception as e: return False, f"Error: {e}"

def delete_user_from_sheet(user_id):
    try:
        creds = get_credentials(); gc = gspread.authorize(creds); sh = gc.open_by_key(ORDER_CHECK_SHEET_ID); ws = sh.worksheet(USER_SHEET_NAME)
        try:
            cell = ws.find(str(user_id))
            if cell: ws.delete_rows(cell.row); load_sheet_data.clear(); return True, f"✅ ลบ ID {user_id} เรียบร้อย"
            else: return False, f"❌ ไม่พบ ID {user_id}"
        except: return False, f"❌ ไม่พบ ID {user_id}"
    except Exception as e: return False, f"Error: {e}"

# --- TIME HELPER ---
def get_thai_time(): return (datetime.utcnow() + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S")
def get_thai_date_str(): return (datetime.utcnow() + timedelta(hours=7)).strftime("%d-%m-%Y")
def get_thai_ts_filename(): return (datetime.utcnow() + timedelta(hours=7)).strftime("%Y%m%d_%H%M%S")

# --- SAVE LOGS (UPDATED FOR MULTI-PHOTOS) ---
def save_log_to_sheet(picker_name, order_id, barcode, prod_name, location, pick_qty, user_col, file_id_or_list):
    try:
        creds = get_credentials(); gc = gspread.authorize(creds)
        sh = gc.open_by_key(LOG_SHEET_ID) 
        try: worksheet = sh.worksheet(LOG_SHEET_NAME)
        except: worksheet = sh.add_worksheet(title=LOG_SHEET_NAME, rows="1000", cols="20"); worksheet.append_row(["Timestamp", "Picker Name", "Order ID", "Barcode", "Product Name", "Location", "Pick Qty", "User", "Image Link (Col I)"])
        
        timestamp = get_thai_time()
        
        # [UPDATED] รองรับทั้ง ID เดียว และ List ของ ID
        if isinstance(file_id_or_list, list):
            # กรณีเป็น List ให้สร้าง Link หลายบรรทัด
            links = [f"https://drive.google.com/open?id={fid}" for fid in file_id_or_list]
            image_link = "\n".join(links)
        else:
            # กรณีเป็น ID เดียว
            image_link = f"https://drive.google.com/open?id={file_id_or_list}"
            
        worksheet.append_row([timestamp, picker_name, order_id, barcode, prod_name, location, pick_qty, user_col, image_link])
        
    except Exception as e: st.warning(f"⚠️ บันทึก Log ไม่สำเร็จ: {e}")

def save_rider_log(picker_name, order_id, file_ids_list, folder_name, license_plate="-"):
    try:
        creds = get_credentials(); gc = gspread.authorize(creds); sh = gc.open_by_key(LOG_SHEET_ID) 
        try: worksheet = sh.worksheet(RIDER_SHEET_NAME)
        except: worksheet = sh.add_worksheet(title=RIDER_SHEET_NAME, rows="1000", cols="10"); worksheet.append_row(["Timestamp", "User Name", "Order ID", "License Plate", "Folder Name", "Rider Image Link"])
        timestamp = get_thai_time()
        links = []; image_link_str = ""
        if isinstance(file_ids_list, list):
            for fid in file_ids_list: links.append(f"https://drive.google.com/open?id={fid}")
            image_link_str = "\n".join(links) 
        else: image_link_str = f"https://drive.google.com/open?id={file_ids_list}"
        worksheet.append_row([timestamp, picker_name, order_id, license_plate, folder_name, image_link_str])
        load_rider_history.clear() 
    except Exception as e: st.warning(f"⚠️ บันทึก Rider Log ไม่สำเร็จ: {e}")

# --- FOLDER STRUCTURE ---
def get_target_folder_structure(service, order_id, main_parent_id):
    now = datetime.utcnow() + timedelta(hours=7); year_str = now.strftime("%Y"); month_str = now.strftime("%m"); date_str = now.strftime("%d-%m-%Y")
    def _get_or_create(parent_id, name):
        q = f"name = '{name}' and '{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        res = service.files().list(q=q, fields="files(id)").execute(); files = res.get('files', [])
        if files: return files[0]['id']
        meta = {'name': name, 'parents': [parent_id], 'mimeType': 'application/vnd.google-apps.folder'}
        folder = service.files().create(body=meta, fields='id').execute(); return folder.get('id')
    year_id = _get_or_create(main_parent_id, year_str); month_id = _get_or_create(year_id, month_str); date_id = _get_or_create(month_id, date_str)
    order_folder_name = f"{order_id}_{now.strftime('%H-%M')}"
    meta_order = {'name': order_folder_name, 'parents': [date_id], 'mimeType': 'application/vnd.google-apps.folder'}
    order_folder = service.files().create(body=meta_order, fields='id').execute(); return order_folder.get('id')

def get_rider_daily_folder(service, main_parent_id):
    now = datetime.utcnow() + timedelta(hours=7); year_str = now.strftime("%Y"); month_str = now.strftime("%m"); folder_name = f"Rider_{now.strftime('%d-%m-%Y')}"
    def _get_or_create(parent_id, name):
        q = f"name = '{name}' and '{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        res = service.files().list(q=q, fields="files(id)").execute(); files = res.get('files', [])
        if files: return files[0]['id']
        meta = {'name': name, 'parents': [parent_id], 'mimeType': 'application/vnd.google-apps.folder'}
        folder = service.files().create(body=meta, fields='id').execute(); return folder.get('id')
    year_id = _get_or_create(main_parent_id, year_str); month_id = _get_or_create(year_id, month_str); final_id = _get_or_create(month_id, folder_name)
    return final_id, folder_name

# --- [NEW] PROCESS VIDEO QUALITY ---
def process_video_quality(uploaded_file, quality_setting):
    """
    Quality Settings:
    1. 'Original (Max)': ไม่ทำอะไรเลย (เร็วสุด)
    2. 'High (720p)': ย่อเหลือ 720p
    3. 'Medium (480p)': ย่อเหลือ 480p
    4. 'Low (360p)': ย่อเหลือ 360p (ประหยัดสุด)
    """
    if quality_setting == 'Original (Max)':
        return uploaded_file, "original" # Return original bytes-like object

    # ถ้าเลือกแบบย่อ ต้องใช้ moviepy
    try:
        from moviepy.editor import VideoFileClip
        
        # 1. Save uploaded file to temp
        tfile = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
        tfile.write(uploaded_file.getvalue())
        tfile.close()
        
        # 2. Set target height
        target_h = 720
        if quality_setting == 'Medium (480p)': target_h = 480
        elif quality_setting == 'Low (360p)': target_h = 360
        
        # 3. Process
        clip = VideoFileClip(tfile.name)
        
        # เช็คว่าถ้าวิดีโอเล็กกว่าเป้าหมายอยู่แล้ว ไม่ต้องขยาย
        if clip.h <= target_h:
            clip.close()
            return uploaded_file, "original"

        # Resize
        new_clip = clip.resize(height=target_h)
        
        # 4. Write to new temp file
        processed_tfile = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
        processed_tfile.close() # Close to allow ffmpeg to write
        
        # preset='ultrafast' เพื่อความเร็วในการประมวลผลบน Cloud
        new_clip.write_videofile(processed_tfile.name, codec='libx264', audio_codec='aac', preset='ultrafast', verbose=False, logger=None)
        
        clip.close()
        new_clip.close()
        
        # 5. Read back as bytes
        with open(processed_tfile.name, 'rb') as f:
            processed_bytes = io.BytesIO(f.read())
            
        # Clean up
        os.unlink(tfile.name)
        os.unlink(processed_tfile.name)
        
        return processed_bytes, "processed"

    except ImportError:
        st.warning("⚠️ MoviePy ไม่ได้ติดตั้ง จะใช้วิดีโอต้นฉบับแทน")
        return uploaded_file, "original"
    except Exception as e:
        st.error(f"⚠️ เกิดข้อผิดพลาดในการย่อวิดีโอ: {e} (ใช้วิดีโอต้นฉบับ)")
        return uploaded_file, "original"

# --- UPLOAD FUNCTIONS ---
def upload_file_to_drive(service, file_obj, filename, folder_id, mime_type='image/jpeg'):
    try:
        file_metadata = {'name': filename, 'parents': [folder_id]}
        # ถ้าเป็น BytesIO (processed)
        if isinstance(file_obj, io.BytesIO):
            media = MediaIoBaseUpload(file_obj, mimetype=mime_type, chunksize=5*1024*1024, resumable=True)
        # ถ้าเป็น UploadedFile (original)
        else:
             media = MediaIoBaseUpload(file_obj, mimetype=mime_type, chunksize=5*1024*1024, resumable=True)
             
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        return file.get('id')
    except HttpError as error:
        st.error(f"Drive Error: {json.loads(error.content.decode('utf-8'))}"); raise error
    except Exception as e: raise e

def upload_photo(service, file_obj, filename, folder_id):
    return upload_file_to_drive(service, io.BytesIO(file_obj), filename, folder_id, 'image/jpeg')

# --- SAFE RESET SYSTEM ---
def trigger_reset(): st.session_state.need_reset = True
def check_and_execute_reset():
    if st.session_state.get('need_reset'):
        keys = ['pack_order_man','pack_prod_man','loc_man','order_val','prod_val','loc_val','prod_display_name']
        for k in keys: st.session_state[k] = ""
        st.session_state.current_order_items = []; st.session_state.expected_items = [] 
        st.session_state.photo_gallery = []; st.session_state.rider_photo_gallery = []
        st.session_state.video_file = None; st.session_state.rider_photo = None
        st.session_state.picking_phase = 'scan'; st.session_state.temp_login_user = None
        st.session_state.pick_qty = 1; st.session_state.cam_counter += 1; st.session_state.need_reset = False
        st.session_state.processing_pack = False; st.session_state.processing_rider = False
        st.session_state.rider_scanned_orders = []; st.session_state.rider_input_reset_key += 1 

def logout_user():
    st.session_state.current_user_name = ""; st.session_state.current_user_id = ""; st.session_state.current_user_role = ""
    trigger_reset(); st.rerun()

# --- CALLBACKS ---
def go_to_pack_phase(): st.session_state.picking_phase = 'pack'
def click_confirm_pack(): st.session_state.processing_pack = True
def click_confirm_rider(): st.session_state.processing_rider = True

# --- UI SETUP ---
st.set_page_config(page_title="Smart Picking System", page_icon="📦")
def init_session_state():
    if 'need_reset' not in st.session_state: st.session_state.need_reset = False
    if 'processing_pack' not in st.session_state: st.session_state.processing_pack = False
    if 'processing_rider' not in st.session_state: st.session_state.processing_rider = False
    if 'rider_scanned_orders' not in st.session_state: st.session_state.rider_scanned_orders = []
    if 'rider_photo_gallery' not in st.session_state: st.session_state.rider_photo_gallery = []
    if 'expected_items' not in st.session_state: st.session_state.expected_items = []
    if 'rider_input_reset_key' not in st.session_state: st.session_state.rider_input_reset_key = 0
    if 'scan_status_msg' not in st.session_state: st.session_state.scan_status_msg = None
    if 'add_user_id' not in st.session_state: st.session_state.add_user_id = ""
    if 'add_user_name' not in st.session_state: st.session_state.add_user_name = ""
    if 'add_user_pass' not in st.session_state: st.session_state.add_user_pass = ""
    if 'video_file' not in st.session_state: st.session_state.video_file = None 
    if 'current_user_role' not in st.session_state: st.session_state.current_user_role = ""
    
    # [NEW] Video Quality State
    if 'video_quality' not in st.session_state: st.session_state.video_quality = 'Original (Max)'

    keys = ['current_user_name', 'current_user_id', 'order_val', 'prod_val', 'loc_val', 'prod_display_name', 
            'photo_gallery', 'cam_counter', 'pick_qty', 'rider_photo', 'current_order_items', 'picking_phase', 'temp_login_user',
            'target_rider_folder_id', 'target_rider_folder_name', 'rider_lp_val']
    for k in keys:
        if k not in st.session_state:
            if k == 'pick_qty': st.session_state[k] = 1
            elif k == 'cam_counter': st.session_state[k] = 0
            elif k == 'photo_gallery': st.session_state[k] = []
            elif k == 'current_order_items': st.session_state[k] = []
            elif k == 'picking_phase': st.session_state[k] = 'scan'
            else: st.session_state[k] = None

init_session_state()
check_and_execute_reset()

# --- LOGIN ---
if not st.session_state.current_user_name:
    st.title("🔐 Login พนักงาน")
    df_users = load_sheet_data(USER_SHEET_NAME, ORDER_CHECK_SHEET_ID)
    if st.session_state.temp_login_user is None:
        st.info("กรุณาสแกนรหัสพนักงาน")
        col1, col2 = st.columns([3, 1])
        manual_user = col1.text_input("พิมพ์รหัสพนักงาน", key="input_user_manual").strip()
        cam_key_user = f"cam_user_{st.session_state.cam_counter}"
        scan_user = back_camera_input("แตะเพื่อสแกนบัตรพนักงาน", key=cam_key_user)
        user_input_val = None
        if manual_user: user_input_val = manual_user
        elif scan_user:
            res_u = decode(Image.open(scan_user)); 
            if res_u: user_input_val = res_u[0].data.decode("utf-8")
        if user_input_val:
            if not df_users.empty and len(df_users.columns) >= 3:
                clean_input_id = str(user_input_val).strip().lower()
                match = df_users[df_users.iloc[:, 0].astype(str).str.strip().str.lower() == clean_input_id]
                if not match.empty:
                    user_role = 'staff'; 
                    if len(match.columns) >= 4 and str(match.iloc[0, 3]).strip().lower() == 'admin': user_role = 'admin'
                    st.session_state.temp_login_user = {'id': str(match.iloc[0, 0]), 'pass': str(match.iloc[0, 1]).strip(), 'name': match.iloc[0, 2], 'role': user_role}
                    st.rerun()
                else: st.error(f"❌ ไม่พบรหัสพนักงาน: {user_input_val}")
            else: st.warning("⚠️ โหลดข้อมูลพนักงานไม่ได้")
    else:
        user_info = st.session_state.temp_login_user
        st.info(f"👤 พนักงาน: **{user_info['name']}** ({user_info['role'].upper()})")
        password_input = st.text_input("🔑 กรุณากรอกรหัสผ่าน", type="password", key="login_pass_input").strip()
        c1, c2 = st.columns([1, 1])
        with c1:
            if st.button("✅ ยืนยัน Login", type="primary", use_container_width=True):
                if password_input == user_info['pass']:
                    st.session_state.current_user_id = user_info['id']; st.session_state.current_user_name = user_info['name']; st.session_state.current_user_role = user_info['role'] 
                    st.session_state.temp_login_user = None; st.toast(f"ยินดีต้อนรับคุณ {user_info['name']} 👋", icon="✅"); time.sleep(1); st.rerun()
                else: st.error("❌ รหัสผ่านไม่ถูกต้อง")
        with c2:
            if st.button("⬅️ เปลี่ยน User", use_container_width=True): st.session_state.temp_login_user = None; st.rerun()
else:
    # --- LOGGED IN ---
    with st.sidebar:
        st.write(f"👤 **{st.session_state.current_user_name}**"); st.caption(f"Role: {st.session_state.current_user_role}")
        menu_options = ["📦 แผนกแพ็คสินค้า", "🚚 Scan ปิดตู้"]
        if st.session_state.current_user_role == 'admin': menu_options.append("👥 จัดการพนักงาน")
        mode = st.radio("เลือกโหมดทำงาน:", menu_options)
        st.divider()
        if st.button("Logout", type="secondary"): logout_user()

    # ================= MODE 1: PACKING =================
    if mode == "📦 แผนกแพ็คสินค้า":
        st.title("📦 ระบบแพ็คสินค้า")
        df_order_data = load_sheet_data(ORDER_DATA_SHEET_NAME, ORDER_CHECK_SHEET_ID)

        if st.session_state.picking_phase == 'scan':
            st.markdown("#### 1. Scan Tracking (ตรวจสอบ Order Data)")
            if not st.session_state.order_val:
                col1, col2 = st.columns([3, 1])
                manual_order = col1.text_input("พิมพ์ Tracking ID", key="pack_order_man").strip().upper()
                if manual_order: st.session_state.order_val = manual_order; st.rerun()
                scan_order = back_camera_input("แตะเพื่อสแกน Tracking", key=f"pack_cam_{st.session_state.cam_counter}")
                if scan_order:
                    res = decode(Image.open(scan_order))
                    if res: st.session_state.order_val = res[0].data.decode("utf-8").upper(); st.rerun()
            else:
                c1, c2 = st.columns([3, 1])
                with c1: st.success(f"📦 Tracking: **{st.session_state.order_val}**")
                with c2: 
                    if st.button("เปลี่ยน Tracking"): trigger_reset(); st.rerun()

            if st.session_state.order_val:
                if df_order_data.empty: st.error(f"❌ ไม่พบข้อมูลใน Sheet {ORDER_DATA_SHEET_NAME}")
                else:
                    if not st.session_state.expected_items:
                        try:
                            matches = df_order_data[df_order_data['Tracking'] == st.session_state.order_val]
                            matches = matches.drop_duplicates(subset=['Barcode'], keep='first')
                            if matches.empty: play_sound('error'); st.error(f"⛔ ไม่พบ Tracking ในระบบ!"); time.sleep(2); st.session_state.order_val = ""; st.rerun()
                            else: st.session_state.expected_items = matches.to_dict('records')
                        except KeyError: st.error("❌ Sheet Order_Data Column Error")

                if st.session_state.expected_items:
                    st.info(f"📋 รายการสินค้าที่ต้องแพ็ค ({len(st.session_state.expected_items)} รายการ):")
                    exp_df = pd.DataFrame(st.session_state.expected_items)
                    display_cols = ['Barcode', 'Product Name']
                    valid_display_cols = [c for c in display_cols if c in exp_df.columns]
                    st.dataframe(exp_df[valid_display_cols], use_container_width=True)

                    st.markdown("---")
                    st.markdown("#### 2. ตรวจสอบสินค้า (Scan & Verify)")
                    
                    if not st.session_state.prod_val:
                        col1, col2 = st.columns([3, 1])
                        manual_prod = col1.text_input("พิมพ์ Barcode", key="pack_prod_man").strip()
                        if manual_prod: st.session_state.prod_val = manual_prod; st.rerun()
                        scan_prod = back_camera_input("แตะเพื่อสแกนสินค้า", key=f"prod_cam_{st.session_state.cam_counter}")
                        if scan_prod:
                            res_p = decode(Image.open(scan_prod)); 
                            if res_p: st.session_state.prod_val = res_p[0].data.decode("utf-8"); st.rerun()
                    else:
                        scanned_barcode = st.session_state.prod_val; found_item = None
                        for item in st.session_state.expected_items:
                            if str(item.get('Barcode', '')).strip() == scanned_barcode: found_item = item; break
                        if found_item:
                            already_scanned = any(x['Barcode'] == scanned_barcode for x in st.session_state.current_order_items)
                            if not already_scanned:
                                new_item = {"Barcode": scanned_barcode, "Product Name": found_item.get('Product Name', 'Unknown'), "Location": found_item.get('Location', '-')}
                                st.session_state.current_order_items.append(new_item)
                                play_sound('success'); st.toast(f"✅ ถูกต้อง! เพิ่ม {found_item.get('Product Name', '')}", icon="🛒")
                            else: st.toast(f"⚠️ สินค้านี้สแกนไปแล้ว", icon="ℹ️")
                            st.session_state.prod_val = ""; st.session_state.cam_counter += 1; st.rerun()
                        else:
                            play_sound('error'); st.error(f"⛔ สินค้าผิด! Barcode {scanned_barcode} ไม่อยู่ใน Order นี้")
                            time.sleep(1); 
                            if st.button("❌ สแกนใหม่"): st.session_state.prod_val = ""; st.session_state.cam_counter += 1; st.rerun()

                if st.session_state.current_order_items:
                    st.markdown("---")
                    st.markdown(f"### 🛒 สินค้าที่แพ็คแล้ว ({len(st.session_state.current_order_items)} ชิ้น)")
                    st.dataframe(pd.DataFrame(st.session_state.current_order_items)[['Barcode', 'Product Name']], use_container_width=True)
                    st.button("✅ ยืนยันรายการครบแล้ว (ไปถ่ายวีดีโอ)", type="primary", use_container_width=True, on_click=go_to_pack_phase)

        elif st.session_state.picking_phase == 'pack':
            st.success(f"📦 Tracking: **{st.session_state.order_val}** (ยืนยันรายการครบถ้วน)")
            st.info("📋 รายการสินค้าที่แพ็ค:")
            
            # โชว์ตารางสรุป
            display_df = pd.DataFrame(st.session_state.current_order_items)
            if not display_df.empty:
                st.dataframe(display_df[['Barcode', 'Product Name']], use_container_width=True)
            
            st.markdown("---")
            st.markdown("#### 3. 📸 ถ่ายรูปหลักฐาน (ถ่ายได้หลายรูป)")
            
            # --- ส่วนแสดง Gallery รูปที่ถ่ายไปแล้ว ---
            if st.session_state.photo_gallery:
                st.markdown(f"**รูปที่ถ่ายแล้ว ({len(st.session_state.photo_gallery)} รูป):**")
                cols = st.columns(4) # แสดงแถวละ 4 รูป
                for idx, img in enumerate(st.session_state.photo_gallery):
                    with cols[idx % 4]:
                        st.image(img, use_column_width=True)
                        if st.button("🗑️ ลบ", key=f"del_pack_{idx}"):
                            st.session_state.photo_gallery.pop(idx)
                            st.rerun()
                st.divider()

            # --- กล้องถ่ายรูป ---
            # จำกัดไม่เกิน 5 รูป (ปรับแก้ตัวเลขได้ตามต้องการ)
            if len(st.session_state.photo_gallery) < 5:
                col_cam1, col_cam2 = st.columns([3, 1])
                with col_cam1:
                    st.caption("แตะปุ่มด้านล่างเพื่อถ่ายรูป (เช่น รูปบิล, รูปสินค้า, รูปกล่อง)")
                    pack_img = back_camera_input("ถ่ายรูปเพิ่ม (กล้องหลัง)", key=f"pack_cam_fin_{st.session_state.cam_counter}")
                
                if pack_img:
                    # แปลงไฟล์ภาพและบันทึกลง Session
                    img_pil = Image.open(pack_img)
                    if img_pil.mode in ("RGBA", "P"): img_pil = img_pil.convert("RGB")
                    buf = io.BytesIO(); img_pil.save(buf, format='JPEG', quality=90, optimize=True) # quality 90 ชัดและไฟล์ไม่ใหญ่
                    st.session_state.photo_gallery.append(buf.getvalue())
                    st.session_state.cam_counter += 1
                    play_sound('scan') # เสียงชัตเตอร์ (ใช้เสียง scan แทน)
                    st.rerun()
            else:
                st.info("✅ ถ่ายครบ 5 รูปแล้ว (ถ้าต้องการถ่ายใหม่ ให้ลบรูปเก่าออกก่อน)")

            st.markdown("---")
            
            # --- ปุ่ม Action ---
            col_b1, col_b2 = st.columns([1, 1])
            with col_b1:
                if st.button("⬅️ กลับไปแก้ไขรายการ"): 
                    st.session_state.picking_phase = 'scan'
                    st.session_state.photo_gallery = []
                    st.rerun()
                    
            with col_b2:
                # ปุ่มยืนยันจะกดได้ก็ต่อเมื่อมีรูปอย่างน้อย 1 รูป
                if len(st.session_state.photo_gallery) > 0:
                    if not st.session_state.processing_pack:
                        st.button(f"☁️ ยืนยัน Upload ({len(st.session_state.photo_gallery)} รูป)", type="primary", use_container_width=True, on_click=click_confirm_pack)
                    else:
                        st.info("⏳ กำลังอัปโหลด... (ห้ามปิดหน้าจอ)")
                    
                    if st.session_state.processing_pack:
                        with st.spinner("🚀 กำลังอัปโหลดรูปภาพ..."):
                            srv = authenticate_drive()
                            if srv:
                                fid = get_target_folder_structure(srv, st.session_state.order_val, MAIN_FOLDER_ID)
                                ts = get_thai_ts_filename()
                                uploaded_ids = []
                                
                                # Loop Upload ทุกรูปใน Gallery
                                for i, img_bytes in enumerate(st.session_state.photo_gallery):
                                    seq = i + 1
                                    fn = f"{st.session_state.order_val}_PACKED_{ts}_{seq}.jpg"
                                    uid = upload_photo(srv, img_bytes, fn, fid)
                                    uploaded_ids.append(uid)
                                
                                # บันทึก Log ลง Sheet (ส่ง List ของ ID ไป)
                                for item in st.session_state.current_order_items:
                                    save_log_to_sheet(
                                        st.session_state.current_user_name, 
                                        st.session_state.order_val, 
                                        item['Barcode'], 
                                        item['Product Name'], 
                                        item['Location'], 
                                        item.get('Qty', '1'), 
                                        st.session_state.current_user_id, 
                                        uploaded_ids # [UPDATED] ส่งเป็น List
                                    )
                                    
                                play_sound('success')
                                st.markdown(
                                    """
                                    <div style="text-align: center;">
                                        <div style="font-size: 80px;">✅</div>
                                        <h3 style="color: #28a745; margin-top: -10px;">บันทึกสำเร็จ!</h3>
                                    </div>
                                    """, 
                                    unsafe_allow_html=True
                                )
                                time.sleep(1.5)
                                trigger_reset()
                                st.rerun()
                else:
                    st.warning("⚠️ กรุณาถ่ายรูปอย่างน้อย 1 รูป")

    # ================= MODE 2: RIDER (NO CHANGE) =================
    elif mode == "🚚 Scan ปิดตู้":
        st.title("🚚 Scan ปิดตู้")
        st.info("1. สแกน Tracking\n2. ถ่ายรูปปิดตู้ \n*รูปจะถูกบันทึกใน Folder วันที่ และ Link จะถูกบันทึกให้ทุก Tracking*")
        
        df_order_data_rider = load_sheet_data(ORDER_DATA_SHEET_NAME, ORDER_CHECK_SHEET_ID)
        st.markdown("#### 0. ระบุทะเบียนรถ (Optional)")
        rider_lp = st.text_input("🚛 ทะเบียนรถ", key="rider_lp_input", placeholder="กรอกทะเบียนรถที่มารับสินค้า...").strip()

        if st.session_state.scan_status_msg:
            if st.session_state.scan_status_msg['type'] == 'error': st.error(st.session_state.scan_status_msg['msg']); play_sound('error')
            else: st.success(st.session_state.scan_status_msg['msg']); play_sound('success' if not st.session_state.scan_status_msg['msg'].startswith("✅ เพิ่ม") else 'scan')
            st.session_state.scan_status_msg = None

        st.markdown("#### 1. Scan Tracking")
        col_r1, col_r2 = st.columns([3, 1])
        dynamic_key = f"rider_ord_man_{st.session_state.rider_input_reset_key}"
        man_rider_ord = col_r1.text_input("พิมพ์ Tracking ID", key=dynamic_key).strip().upper()
        with col_r2: st.write(""); st.write(""); manual_submit = st.button("ตกลง", use_container_width=True)

        scan_rider_ord = back_camera_input("แตะเพื่อสแกน Tracking", key=f"rider_cam_ord_{st.session_state.cam_counter}")
        current_rider_order = ""
        if manual_submit and man_rider_ord: current_rider_order = man_rider_ord
        elif scan_rider_ord:
            res = decode(Image.open(scan_rider_ord)); 
            if res: current_rider_order = res[0].data.decode("utf-8").upper()

        if current_rider_order:
            existing_ids = [o['id'] for o in st.session_state.rider_scanned_orders]
            valid_trackings = []
            if not df_order_data_rider.empty and 'Tracking' in df_order_data_rider.columns: valid_trackings = df_order_data_rider['Tracking'].astype(str).str.strip().str.upper().tolist()
            if not valid_trackings: st.session_state.scan_status_msg = {'type': 'error', 'msg': f"⚠️ โหลดข้อมูล Error"}; st.session_state.rider_input_reset_key += 1; st.rerun()
            elif current_rider_order not in valid_trackings: st.session_state.scan_status_msg = {'type': 'error', 'msg': f"⛔ ไม่พบ Tracking"}; st.session_state.rider_input_reset_key += 1; st.session_state.cam_counter += 1; st.rerun()
            elif current_rider_order in existing_ids: st.session_state.scan_status_msg = {'type': 'error', 'msg': f"⚠️ ซ้ำ"}; st.session_state.rider_input_reset_key += 1; st.session_state.cam_counter += 1; st.rerun()
            else:
                history_list = load_rider_history()
                if current_rider_order in history_list: st.session_state.scan_status_msg = {'type': 'error', 'msg': f"⛔ เคยบันทึกแล้ว"}; st.session_state.rider_input_reset_key += 1; st.session_state.cam_counter += 1; st.rerun()
                else: st.session_state.rider_scanned_orders.append({'id': current_rider_order}); st.session_state.scan_status_msg = {'type': 'success', 'msg': f"✅ เพิ่ม: {current_rider_order}"}; st.session_state.rider_input_reset_key += 1; st.session_state.cam_counter += 1; st.rerun()

        if st.session_state.rider_scanned_orders:
            st.markdown(f"##### 📋 รายการที่สแกนแล้ว ({len(st.session_state.rider_scanned_orders)})")
            for idx, order in enumerate(st.session_state.rider_scanned_orders):
                c1, c2, c3 = st.columns([1, 4, 1])
                c1.write(f"{idx+1}."); c2.write(f"**{order['id']}**")
                if c3.button("ลบ", key=f"del_r_{idx}"): st.session_state.rider_scanned_orders.pop(idx); st.rerun()
            if st.button("🗑️ ล้างทั้งหมด", type="secondary"): st.session_state.rider_scanned_orders = []; st.rerun()
            st.markdown("---")
            st.markdown("#### 2. ถ่ายรูปปิดตู้ (สูงสุด 3 รูป)")
            if st.session_state.rider_photo_gallery:
                cols = st.columns(3)
                for idx, img_bytes in enumerate(st.session_state.rider_photo_gallery):
                    with cols[idx]: st.image(img_bytes, use_column_width=True); 
                    if st.button("ลบรูป", key=f"del_rider_img_{idx}"): st.session_state.rider_photo_gallery.pop(idx); st.rerun()
            if len(st.session_state.rider_photo_gallery) < 3:
                rider_img_input = back_camera_input("ถ่ายรูปเพิ่ม (กล้องหลัง)", key=f"rider_cam_act_{st.session_state.cam_counter}")
                if rider_img_input:
                    img_pil = Image.open(rider_img_input); 
                    if img_pil.mode in ("RGBA", "P"): img_pil = img_pil.convert("RGB")
                    buf = io.BytesIO(); img_pil.save(buf, format='JPEG', quality=120, optimize=True)
                    st.session_state.rider_photo_gallery.append(buf.getvalue()); st.session_state.cam_counter += 1; st.rerun()
            if len(st.session_state.rider_photo_gallery) > 0:
                st.write("")
                if not st.session_state.processing_rider: st.button(f"🚀 ยืนยันบันทึก", type="primary", use_container_width=True, on_click=click_confirm_rider)
                else: st.info("⏳ กำลังบันทึกข้อมูล...")
                if st.session_state.processing_rider:
                    with st.spinner("🚀 กำลังอัปโหลด..."):
                        srv = authenticate_drive(); ts = get_thai_ts_filename(); rider_lp_val = rider_lp if rider_lp else "NoPlate"; lp_clean = rider_lp_val.replace(" ", "_")
                        daily_fid, daily_fname = get_rider_daily_folder(srv, MAIN_FOLDER_ID); uploaded_ids = []
                        for i, img_bytes in enumerate(st.session_state.rider_photo_gallery):
                            fn = f"{lp_clean}_{ts}_{i+1}.jpg"; uid = upload_photo(srv, img_bytes, fn, daily_fid); uploaded_ids.append(uid)
                        for order in st.session_state.rider_scanned_orders: save_rider_log(st.session_state.current_user_name, order['id'], uploaded_ids, daily_fname, rider_lp_val)
                        play_sound('success'); st.markdown("""<div style="text-align: center;"><div style="font-size: 100px;">✅</div><h2 style="color: #28a745;">บันทึกครบถ้วน!</h2></div>""", unsafe_allow_html=True); time.sleep(2); trigger_reset(); st.rerun()
        else: st.info("👈 Scan Tracking อย่างน้อย 1 รายการ")
            
    # ================= MODE 3: MANAGE USERS (SAME) =================
    elif mode == "👥 จัดการพนักงาน":
        st.title("👥 จัดการพนักงาน"); df_users_manage = load_sheet_data(USER_SHEET_NAME, ORDER_CHECK_SHEET_ID); col_add, col_del = st.columns([1, 1])
        with col_add:
            st.subheader("➕ เพิ่มพนักงานใหม่")
            new_id = st.text_input("รหัส (ID)", key="input_new_id"); new_name = st.text_input("ชื่อ", key="input_new_name"); new_pass = st.text_input("Pass", type="password", key="input_new_pass"); role_option = st.selectbox("Role", ["staff", "admin"], key="input_new_role")
            def click_add_user():
                uid = st.session_state.input_new_id; uname = st.session_state.input_new_name; upass = st.session_state.input_new_pass; urole = st.session_state.input_new_role
                if uid and uname and upass:
                    success, msg = add_new_user_to_sheet(uid, upass, uname, urole)
                    if success: st.toast(msg, icon="✅"); st.session_state.input_new_id=""; st.session_state.input_new_name=""; st.session_state.input_new_pass=""
                    else: st.toast(msg, icon="❌")
                else: st.toast("กรอกให้ครบ", icon="⚠️")
            st.button("บันทึก", type="primary", use_container_width=True, on_click=click_add_user)
        with col_del:
            st.subheader("🗑️ ลบพนักงาน")
            if not df_users_manage.empty and len(df_users_manage.columns) >= 3:
                 try:
                     user_options = df_users_manage.apply(lambda x: f"{x.iloc[0]}: {x.iloc[2]}", axis=1).tolist(); selected_user_str = st.selectbox("เลือกคนลบ", user_options)
                     def click_del_user():
                         target_id = selected_user_str.split(":")[0]; success, msg = delete_user_from_sheet(target_id)
                         if success: st.toast(msg, icon="✅")
                         else: st.toast(msg, icon="❌")
                     st.button("ลบ", type="secondary", use_container_width=True, on_click=click_del_user)
                 except: st.error("Error displaying users")
            else: st.info("ไม่มีข้อมูล")
        st.divider(); st.subheader("📋 รายชื่อ"); st.dataframe(df_users_manage, use_container_width=True) if not df_users_manage.empty else st.warning("No Data")
