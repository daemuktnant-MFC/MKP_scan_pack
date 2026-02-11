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

# --- IMPORT LIBRARY กล้อง ---
try:
    from streamlit_back_camera_input import back_camera_input
except ImportError:
    st.error("⚠️ ต้องเพิ่ม 'streamlit-back-camera-input' ใน requirements.txt")
    st.stop()

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
    </style>
    """,
    unsafe_allow_html=True
)

# --- CONFIGURATION ---
MAIN_FOLDER_ID = '1sZQKOuw4YGazuy4euk4ns7nLr7Zie6cm'

# 1. ไฟล์สำหรับบันทึก Log (ปลายทาง)
LOG_SHEET_ID = '1tZfX9I6Ntbo-Jf2_rcqBc2QYUrCCCSAx8K4YBkly92c' 

# 2. ไฟล์สำหรับตรวจสอบ Order Data (ต้นทาง)
ORDER_CHECK_SHEET_ID = '1Om9qwShA3hBQgKJPQNbJgDPInm9AQ2hY5Z8OuOpkF08' 

ORDER_DATA_SHEET_NAME = 'Order_Data'
LOG_SHEET_NAME = 'Logs'
RIDER_SHEET_NAME = 'Rider_Logs'
USER_SHEET_NAME = 'User'

# --- SOUND HELPER ---
def play_sound(status='success'):
    if status == 'success':
        sound_url = "https://www.soundjay.com/buttons/sounds/beep-07.mp3"
    else:
        sound_url = "https://www.soundjay.com/buttons/sounds/button-10.mp3"
    
    st.markdown(f"""
        <audio autoplay>
            <source src="{sound_url}" type="audio/mp3">
        </audio>
        """, unsafe_allow_html=True)

# --- AUTHENTICATION ---
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

def authenticate_drive():
    try:
        creds = get_credentials()
        if creds: return build('drive', 'v3', credentials=creds)
        return None
    except Exception as e:
        st.error(f"Error Drive: {e}")
        return None

# --- GOOGLE SERVICES ---
@st.cache_data(ttl=600)
def load_sheet_data(sheet_name, spreadsheet_key): 
    try:
        creds = get_credentials()
        if not creds: return pd.DataFrame()
        gc = gspread.authorize(creds)
        
        try:
            sh = gc.open_by_key(spreadsheet_key)
        except Exception as e:
            st.error(f"❌ เปิดไฟล์ Google Sheet ไม่ได้ (ID: {spreadsheet_key}): {e}")
            return pd.DataFrame()
        
        try:
            if isinstance(sheet_name, int): worksheet = sh.get_worksheet(sheet_name)
            else: worksheet = sh.worksheet(sheet_name)
        except Exception as e:
            st.error(f"❌ ไม่พบ Tab ชื่อ '{sheet_name}' ในไฟล์ Sheet: {e}")
            return pd.DataFrame()
        
        rows = worksheet.get_all_values()
        if len(rows) > 1:
            headers = rows[0]; data = rows[1:]
            df = pd.DataFrame(data, columns=headers)
            df.columns = df.columns.str.strip()
            
            # Normalize column names
            for col in df.columns:
                col_clean = col.strip()
                col_lower = col_clean.lower()
                
                if 'tracking' in col_lower or ('order' in col_lower and 'id' in col_lower): 
                    df.rename(columns={col: 'Tracking'}, inplace=True)
                elif 'barcode' in col_lower:
                    df.rename(columns={col: 'Barcode'}, inplace=True)
                    df['Barcode'] = df['Barcode'].astype(str).str.replace(r'\.0$', '', regex=True)
                elif col_clean == 'Name' or 'product name' in col_lower:
                     df.rename(columns={col: 'Product Name'}, inplace=True)
                elif 'qty' in col_lower or 'quantity' in col_lower:
                     df.rename(columns={col: 'Qty'}, inplace=True)
            
            return df
        return pd.DataFrame()
    except Exception as e:
        st.error(f"❌ Load Error Other: {e}") 
        return pd.DataFrame()

# Load Rider History
@st.cache_data(ttl=30)
def load_rider_history():
    try:
        creds = get_credentials()
        if not creds: return []
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(LOG_SHEET_ID) 
        try:
            worksheet = sh.worksheet(RIDER_SHEET_NAME)
            records = worksheet.get_all_records()
            if records:
                df = pd.DataFrame(records)
                target_col = None
                for col in df.columns:
                    if "order" in col.lower() and "id" in col.lower():
                        target_col = col
                        break
                if target_col:
                    return df[target_col].astype(str).str.strip().str.upper().tolist()
        except:
            pass 
        return []
    except:
        return []

# --- TIME HELPER ---
def get_thai_time(): return (datetime.utcnow() + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S")
def get_thai_date_str(): return (datetime.utcnow() + timedelta(hours=7)).strftime("%d-%m-%Y")
def get_thai_time_suffix(): return (datetime.utcnow() + timedelta(hours=7)).strftime("%H-%M")
def get_thai_ts_filename(): return (datetime.utcnow() + timedelta(hours=7)).strftime("%Y%m%d_%H%M%S")

# --- SAVE LOGS ---
def save_log_to_sheet(picker_name, order_id, barcode, prod_name, location, pick_qty, user_col, file_id):
    try:
        creds = get_credentials(); gc = gspread.authorize(creds)
        sh = gc.open_by_key(LOG_SHEET_ID) 
        try: worksheet = sh.worksheet(LOG_SHEET_NAME)
        except: worksheet = sh.add_worksheet(title=LOG_SHEET_NAME, rows="1000", cols="20"); worksheet.append_row(["Timestamp", "Picker Name", "Order ID", "Barcode", "Product Name", "Location", "Pick Qty", "User", "Image Link (Col I)"])
        
        timestamp = get_thai_time(); image_link = f"https://drive.google.com/open?id={file_id}"
        worksheet.append_row([timestamp, picker_name, order_id, barcode, prod_name, location, pick_qty, user_col, image_link])
        
    except Exception as e: st.warning(f"⚠️ บันทึก Log ไม่สำเร็จ: {e}")

# --- SAVE RIDER LOG ---
def save_rider_log(picker_name, order_id, file_ids_list, folder_name, license_plate="-"):
    try:
        creds = get_credentials(); gc = gspread.authorize(creds)
        sh = gc.open_by_key(LOG_SHEET_ID) 
        try: 
            worksheet = sh.worksheet(RIDER_SHEET_NAME)
        except: 
            worksheet = sh.add_worksheet(title=RIDER_SHEET_NAME, rows="1000", cols="10")
            worksheet.append_row(["Timestamp", "User Name", "Order ID", "License Plate", "Folder Name", "Rider Image Link"])
        
        timestamp = get_thai_time()
        
        links = []
        if isinstance(file_ids_list, list):
            for fid in file_ids_list:
                links.append(f"https://drive.google.com/open?id={fid}")
            image_link_str = "\n".join(links) 
        else:
            image_link_str = f"https://drive.google.com/open?id={file_ids_list}"

        worksheet.append_row([timestamp, picker_name, order_id, license_plate, folder_name, image_link_str])
        load_rider_history.clear() 
    except Exception as e: st.warning(f"⚠️ บันทึก Rider Log ไม่สำเร็จ: {e}")

# --- FOLDER STRUCTURE ---
def get_target_folder_structure(service, order_id, main_parent_id):
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

    year_id = _get_or_create(main_parent_id, year_str)
    month_id = _get_or_create(year_id, month_str)
    date_id = _get_or_create(month_id, date_str)

    time_suffix = now.strftime("%H-%M")
    order_folder_name = f"{order_id}_{time_suffix}"
    meta_order = {'name': order_folder_name, 'parents': [date_id], 'mimeType': 'application/vnd.google-apps.folder'}
    order_folder = service.files().create(body=meta_order, fields='id').execute()
    return order_folder.get('id')

def get_rider_daily_folder(service, main_parent_id):
    now = datetime.utcnow() + timedelta(hours=7)
    year_str = now.strftime("%Y")
    month_str = now.strftime("%m")
    date_str = now.strftime("%d-%m-%Y")
    folder_name = f"Rider_{date_str}"

    def _get_or_create(parent_id, name):
        q = f"name = '{name}' and '{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        res = service.files().list(q=q, fields="files(id)").execute()
        files = res.get('files', [])
        if files: return files[0]['id']
        meta = {'name': name, 'parents': [parent_id], 'mimeType': 'application/vnd.google-apps.folder'}
        folder = service.files().create(body=meta, fields='id').execute()
        return folder.get('id')
    
    year_id = _get_or_create(main_parent_id, year_str)
    month_id = _get_or_create(year_id, month_str)
    final_id = _get_or_create(month_id, folder_name)
    return final_id, folder_name

def upload_photo(service, file_obj, filename, folder_id):
    try:
        file_metadata = {'name': filename, 'parents': [folder_id]}
        if isinstance(file_obj, bytes): media_body = io.BytesIO(file_obj)
        else: media_body = file_obj 
        media = MediaIoBaseUpload(media_body, mimetype='image/jpeg', chunksize=1024*1024, resumable=True)
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        return file.get('id')
    except HttpError as error:
        error_reason = json.loads(error.content.decode('utf-8'))
        st.error(f"Google Drive Error: {error_reason}")
        raise error
    except Exception as e:
        raise e

# --- SAFE RESET SYSTEM ---
def trigger_reset():
    st.session_state.need_reset = True

def check_and_execute_reset():
    if st.session_state.get('need_reset'):
        if 'pack_order_man' in st.session_state: st.session_state.pack_order_man = ""
        if 'pack_prod_man' in st.session_state: st.session_state.pack_prod_man = ""
        if 'loc_man' in st.session_state: st.session_state.loc_man = ""
        
        st.session_state.order_val = ""
        st.session_state.current_order_items = []
        st.session_state.expected_items = [] 
        st.session_state.photo_gallery = [] 
        
        st.session_state.rider_photo_gallery = []
        
        st.session_state.rider_photo = None
        st.session_state.picking_phase = 'scan'
        st.session_state.temp_login_user = None
        st.session_state.target_rider_folder_id = None
        st.session_state.target_rider_folder_name = ""
        
        st.session_state.prod_val = ""
        st.session_state.loc_val = ""
        st.session_state.prod_display_name = ""
        st.session_state.pick_qty = 1 
        st.session_state.cam_counter += 1
        st.session_state.need_reset = False
        
        st.session_state.processing_pack = False
        st.session_state.processing_rider = False
        
        st.session_state.rider_scanned_orders = []
        st.session_state.rider_input_reset_key += 1 

def logout_user():
    st.session_state.current_user_name = ""; st.session_state.current_user_id = ""
    trigger_reset(); st.rerun()

# --- CALLBACKS ---
def go_to_pack_phase():
    st.session_state.picking_phase = 'pack'

def click_confirm_pack():
    st.session_state.processing_pack = True

def click_confirm_rider():
    st.session_state.processing_rider = True

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
            else: st.session_state[k] = None if k in ['temp_login_user', 'target_rider_folder_id'] else ""

init_session_state()
check_and_execute_reset()

# --- LOGIN ---
if not st.session_state.current_user_name:
    st.title("🔐 Login พนักงาน")
    df_users = load_sheet_data(USER_SHEET_NAME, LOG_SHEET_ID)

    if st.session_state.temp_login_user is None:
        st.info("กรุณาสแกนรหัสพนักงาน")
        col1, col2 = st.columns([3, 1])
        manual_user = col1.text_input("พิมพ์รหัสพนักงาน", key="input_user_manual").strip()
        cam_key_user = f"cam_user_{st.session_state.cam_counter}"
        scan_user = back_camera_input("แตะเพื่อสแกนบัตรพนักงาน", key=cam_key_user)
        
        user_input_val = None
        if manual_user: user_input_val = manual_user
        elif scan_user:
            res_u = decode(Image.open(scan_user))
            if res_u: user_input_val = res_u[0].data.decode("utf-8")
        
        if user_input_val:
            if not df_users.empty and len(df_users.columns) >= 3:
                match = df_users[df_users.iloc[:, 0].astype(str) == str(user_input_val)]
                if not match.empty:
                    st.session_state.temp_login_user = {'id': str(user_input_val), 'pass': str(match.iloc[0, 1]).strip(), 'name': match.iloc[0, 2]}
                    st.rerun()
                else: st.error(f"❌ ไม่พบรหัสพนักงาน: {user_input_val}")
            else: st.warning("⚠️ โหลดข้อมูลพนักงานไม่ได้")
    else:
        user_info = st.session_state.temp_login_user
        st.info(f"👤 พนักงาน: **{user_info['name']}** ({user_info['id']})")
        password_input = st.text_input("🔑 กรุณากรอกรหัสผ่าน", type="password", key="login_pass_input").strip()
        c1, c2 = st.columns([1, 1])
        with c1:
            if st.button("✅ ยืนยัน Login", type="primary", use_container_width=True):
                if password_input == user_info['pass']:
                    st.session_state.current_user_id = user_info['id']
                    st.session_state.current_user_name = user_info['name']
                    st.session_state.temp_login_user = None
                    st.toast(f"ยินดีต้อนรับคุณ {user_info['name']} 👋", icon="✅")
                    time.sleep(1); st.rerun()
                else: st.error("❌ รหัสผ่านไม่ถูกต้อง")
        with c2:
            if st.button("⬅️ เปลี่ยน User", use_container_width=True):
                st.session_state.temp_login_user = None; st.rerun()
else:
    # --- LOGGED IN ---
    with st.sidebar:
        st.write(f"👤 **{st.session_state.current_user_name}**")
        mode = st.radio("เลือกโหมดทำงาน:", ["📦 แผนกแพ็คสินค้า", "🚚 Scan ปิดตู้"])
        st.divider()
        if st.button("Logout", type="secondary"): logout_user()

    # ================= MODE 1: PACKING =================
    if mode == "📦 แผนกแพ็คสินค้า":
        st.title("📦 ระบบเบิก-แพ็คสินค้า")
        
        # Load Order Data
        df_order_data = load_sheet_data(ORDER_DATA_SHEET_NAME, ORDER_CHECK_SHEET_ID)

        if st.session_state.picking_phase == 'scan':
            st.markdown("#### 1. Scan Tracking (ตรวจสอบ Order Data)")
            
            # --- 1.1 SCAN TRACKING ---
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

            # --- 1.2 FETCH & VALIDATE ---
            if st.session_state.order_val:
                if df_order_data.empty:
                    st.error(f"❌ ไม่พบข้อมูลใน Sheet {ORDER_DATA_SHEET_NAME} (ตรวจสอบสิทธิ์ไฟล์)")
                else:
                    if not st.session_state.expected_items:
                        try:
                            matches = df_order_data[df_order_data['Tracking'] == st.session_state.order_val]
                            
                            # [UPDATED] STRICT VALIDATION MODE 1
                            if matches.empty:
                                play_sound('error')
                                st.error(f"⛔ ไม่พบ Tracking: {st.session_state.order_val} ในระบบ! (กรุณาตรวจสอบ)")
                                time.sleep(2)
                                # Force Reset Logic
                                st.session_state.order_val = ""
                                st.rerun()
                            else:
                                st.session_state.expected_items = matches.to_dict('records')
                        except KeyError:
                             st.error("❌ Sheet Order_Data ต้องมีคอลัมน์ชื่อ 'Tracking' และ 'Barcode'")

                if st.session_state.expected_items:
                    st.info(f"📋 รายการสินค้าที่ต้องแพ็ค ({len(st.session_state.expected_items)} รายการ):")
                    exp_df = pd.DataFrame(st.session_state.expected_items)
                    display_cols = ['Barcode', 'Product Name', 'Qty']
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
                            res_p = decode(Image.open(scan_prod))
                            if res_p: st.session_state.prod_val = res_p[0].data.decode("utf-8"); st.rerun()
                    else:
                        scanned_barcode = st.session_state.prod_val
                        found_item = None
                        for item in st.session_state.expected_items:
                            if str(item.get('Barcode', '')).strip() == scanned_barcode:
                                found_item = item
                                break
                        
                        if found_item:
                            new_item = {
                                "Barcode": scanned_barcode,
                                "Product Name": found_item.get('Product Name', 'Unknown'),
                                "Location": found_item.get('Location', '-'),
                                "Qty": 1
                            }
                            st.session_state.current_order_items.append(new_item)
                            play_sound('success')
                            st.toast(f"✅ ถูกต้อง! เพิ่ม {found_item.get('Product Name', '')}", icon="🛒")
                            st.session_state.prod_val = ""
                            st.session_state.cam_counter += 1
                            st.rerun()
                        else:
                            play_sound('error')
                            st.error(f"⛔ สินค้าผิด! Barcode {scanned_barcode} ไม่อยู่ใน Order นี้")
                            time.sleep(1)
                            if st.button("❌ สแกนใหม่"): 
                                st.session_state.prod_val = ""; st.session_state.cam_counter += 1; st.rerun()

                if st.session_state.current_order_items:
                    st.markdown("---")
                    st.markdown(f"### 🛒 สินค้าที่แพ็คแล้ว ({len(st.session_state.current_order_items)} ชิ้น)")
                    st.dataframe(pd.DataFrame(st.session_state.current_order_items), use_container_width=True)
                    st.button("✅ ยืนยันรายการครบแล้ว (ไปถ่ายรูป)", type="primary", use_container_width=True, on_click=go_to_pack_phase)

        elif st.session_state.picking_phase == 'pack':
            st.success(f"📦 Tracking: **{st.session_state.order_val}** (ยืนยันแล้ว)")
            st.info("รายการสินค้าที่จะแพ็ค:")
            st.dataframe(pd.DataFrame(st.session_state.current_order_items), use_container_width=True)
            st.markdown("#### 3. ถ่ายรูปปิดกล่อง (รวมทุกชิ้น)")
            
            if st.session_state.photo_gallery:
                cols = st.columns(5)
                for idx, img in enumerate(st.session_state.photo_gallery):
                    with cols[idx]:
                        st.image(img, use_column_width=True)
                        if st.button("🗑️", key=f"del_{idx}"): st.session_state.photo_gallery.pop(idx); st.rerun()
            
            if len(st.session_state.photo_gallery) < 5:
                pack_img = back_camera_input("ถ่ายรูปสินค้ากองรวม (กล้องหลัง)", key=f"pack_cam_fin_{st.session_state.cam_counter}")
                if pack_img:
                    img_pil = Image.open(pack_img)
                    if img_pil.mode in ("RGBA", "P"): img_pil = img_pil.convert("RGB")
                    buf = io.BytesIO(); img_pil.save(buf, format='JPEG', quality=120, optimize=True)
                    st.session_state.photo_gallery.append(buf.getvalue())
                    st.session_state.cam_counter += 1; st.rerun()
            
            col_b1, col_b2 = st.columns([1, 1])
            with col_b1:
                if st.button("⬅️ กลับไปแก้ไขรายการ"): st.session_state.picking_phase = 'scan'; st.session_state.photo_gallery = []; st.rerun()
            with col_b2:
                if len(st.session_state.photo_gallery) > 0:
                    
                    if not st.session_state.processing_pack:
                        st.button("☁️ ยืนยัน Upload ทั้งหมด", type="primary", use_container_width=True, on_click=click_confirm_pack)
                    else:
                        st.info("⏳ กำลังอัปโหลด... กรุณารอสักครู่ (ห้ามปิดหน้าจอ)")
                    
                    if st.session_state.processing_pack:
                        with st.spinner("🚀 กำลังเชื่อมต่อ Google Drive..."):
                            srv = authenticate_drive()
                            if srv:
                                fid = get_target_folder_structure(srv, st.session_state.order_val, MAIN_FOLDER_ID)
                                ts = get_thai_ts_filename()
                                total_imgs = len(st.session_state.photo_gallery)
                                final_image_link_id = "" 

                                for i, b in enumerate(st.session_state.photo_gallery):
                                    current_seq = i + 1 
                                    fn = f"{st.session_state.order_val}_PACKED_{ts}_Img{current_seq}.jpg"
                                    uid = upload_photo(srv, b, fn, fid)
                                    if current_seq == total_imgs:
                                        final_image_link_id = uid
                                
                                if not final_image_link_id: final_image_link_id = "-"

                                for item in st.session_state.current_order_items:
                                    save_log_to_sheet(
                                        st.session_state.current_user_name, 
                                        st.session_state.order_val, 
                                        item['Barcode'], 
                                        item['Product Name'], 
                                        item['Location'], 
                                        item['Qty'], 
                                        st.session_state.current_user_id, 
                                        final_image_link_id
                                    )
                                    
                                st.markdown(
                                    """
                                    <div style="text-align: center;">
                                        <div style="font-size: 100px;">✅</div>
                                        <h2 style="color: #28a745; margin-top: -20px;">บันทึกสำเร็จ!</h2>
                                    </div>
                                    """, 
                                    unsafe_allow_html=True
                                )
                                time.sleep(1.5)
                                trigger_reset()
                                st.rerun()

    # ================= MODE 2: RIDER =================
    elif mode == "🚚 Scan ปิดตู้":
        st.title("🚚 Scan ปิดตู้")
        st.info("1. สแกน Tracking\n2. ถ่ายรูปปิดตู้ \n*รูปจะถูกบันทึกใน Folder วันที่ และ Link จะถูกบันทึกให้ทุก Tracking*")
        
        # [UPDATED] Load Order Data for Validation
        df_order_data_rider = load_sheet_data(ORDER_DATA_SHEET_NAME, ORDER_CHECK_SHEET_ID)

        # 0. ระบุทะเบียนรถ
        st.markdown("#### 0. ระบุทะเบียนรถ (Optional)")
        rider_lp = st.text_input("🚛 ทะเบียนรถ", key="rider_lp_input", placeholder="กรอกทะเบียนรถที่มารับสินค้า...").strip()

        # STATUS MESSAGE
        if st.session_state.scan_status_msg:
            if st.session_state.scan_status_msg['type'] == 'error':
                st.error(st.session_state.scan_status_msg['msg'])
                play_sound('error')
            else:
                st.success(st.session_state.scan_status_msg['msg'])
                play_sound('success')
            st.session_state.scan_status_msg = None


        # 1. ส่วนสแกน Tracking
        st.markdown("#### 1. Scan Tracking")
        
        col_r1, col_r2 = st.columns([3, 1])
        dynamic_key = f"rider_ord_man_{st.session_state.rider_input_reset_key}"
        man_rider_ord = col_r1.text_input("พิมพ์ Tracking ID", key=dynamic_key).strip().upper()
        
        with col_r2:
            st.write("") 
            st.write("")
            manual_submit = st.button("ตกลง", use_container_width=True)

        scan_rider_ord = back_camera_input("แตะเพื่อสแกน Tracking", key=f"rider_cam_ord_{st.session_state.cam_counter}")
        
        current_rider_order = ""
        if manual_submit and man_rider_ord:
             current_rider_order = man_rider_ord
        elif scan_rider_ord:
            res = decode(Image.open(scan_rider_ord))
            if res: current_rider_order = res[0].data.decode("utf-8").upper()

        if current_rider_order:
            existing_ids = [o['id'] for o in st.session_state.rider_scanned_orders]
            
            # [UPDATED] STRICT VALIDATION MODE 2
            # Check if order exists in Master Data?
            valid_trackings = []
            if not df_order_data_rider.empty and 'Tracking' in df_order_data_rider.columns:
                 valid_trackings = df_order_data_rider['Tracking'].astype(str).str.strip().str.upper().tolist()
            
            if not valid_trackings:
                 st.session_state.scan_status_msg = {'type': 'error', 'msg': f"⚠️ โหลดข้อมูล Order Data ไม่สำเร็จ หรือไฟล์ว่างเปล่า"}
                 st.session_state.rider_input_reset_key += 1
                 st.rerun()

            elif current_rider_order not in valid_trackings:
                st.session_state.scan_status_msg = {'type': 'error', 'msg': f"⛔ ไม่พบ Tracking: {current_rider_order} ในระบบ!"}
                st.session_state.rider_input_reset_key += 1
                st.session_state.cam_counter += 1
                st.rerun()

            elif current_rider_order in existing_ids:
                st.session_state.scan_status_msg = {'type': 'error', 'msg': f"⚠️ {current_rider_order} มีในตะกร้าแล้ว!"}
                st.session_state.rider_input_reset_key += 1
                st.session_state.cam_counter += 1
                st.rerun()
            else:
                history_list = load_rider_history()
                if current_rider_order in history_list:
                    st.session_state.scan_status_msg = {'type': 'error', 'msg': f"⛔ {current_rider_order} เคยบันทึกไปแล้ว!"}
                    st.session_state.rider_input_reset_key += 1
                    st.session_state.cam_counter += 1
                    st.rerun()
                else:
                    st.session_state.rider_scanned_orders.append({'id': current_rider_order})
                    st.session_state.scan_status_msg = {'type': 'success', 'msg': f"✅ เพิ่ม: {current_rider_order}"}
                    st.session_state.rider_input_reset_key += 1
                    st.session_state.cam_counter += 1
                    st.rerun()

        # รายการ Tracking ที่สแกนแล้ว
        if st.session_state.rider_scanned_orders:
            st.markdown(f"##### 📋 รายการที่สแกนแล้ว ({len(st.session_state.rider_scanned_orders)})")
            
            for idx, order in enumerate(st.session_state.rider_scanned_orders):
                c1, c2, c3 = st.columns([1, 4, 1])
                c1.write(f"{idx+1}.")
                c2.write(f"**{order['id']}**")
                if c3.button("ลบ", key=f"del_r_{idx}"):
                    st.session_state.rider_scanned_orders.pop(idx)
                    st.rerun()
            
            if st.button("🗑️ ล้างทั้งหมด", type="secondary"):
                st.session_state.rider_scanned_orders = []
                st.rerun()
            
            st.markdown("---")

            # 2. ถ่ายรูปส่งมอบ (Multi-Image Gallery)
            st.markdown("#### 2. ถ่ายรูปปิดตู้ (สูงสุด 3 รูป)")
            
            if st.session_state.rider_photo_gallery:
                cols = st.columns(3)
                for idx, img_bytes in enumerate(st.session_state.rider_photo_gallery):
                    with cols[idx]:
                        st.image(img_bytes, use_column_width=True)
                        if st.button("ลบรูป", key=f"del_rider_img_{idx}"):
                            st.session_state.rider_photo_gallery.pop(idx)
                            st.rerun()

            if len(st.session_state.rider_photo_gallery) < 3:
                rider_img_input = back_camera_input("ถ่ายรูปเพิ่ม (กล้องหลัง)", key=f"rider_cam_act_{st.session_state.cam_counter}")
                if rider_img_input:
                    img_pil = Image.open(rider_img_input)
                    if img_pil.mode in ("RGBA", "P"): img_pil = img_pil.convert("RGB")
                    buf = io.BytesIO()
                    img_pil.save(buf, format='JPEG', quality=120, optimize=True)
                    st.session_state.rider_photo_gallery.append(buf.getvalue())
                    st.session_state.cam_counter += 1
                    st.rerun()
            
            if len(st.session_state.rider_photo_gallery) > 0:
                st.write("")
                if not st.session_state.processing_rider:
                    st.button(f"🚀 ยืนยันบันทึก ({len(st.session_state.rider_scanned_orders)} Orders)", type="primary", use_container_width=True, on_click=click_confirm_rider)
                else:
                    st.info("⏳ กำลังบันทึกข้อมูล... กรุณารอสักครู่")
                
                if st.session_state.processing_rider:
                    with st.spinner("🚀 กำลังอัปโหลดรูปภาพ..."):
                        srv = authenticate_drive()
                        ts = get_thai_ts_filename()
                        rider_lp_val = rider_lp if rider_lp else "NoPlate"
                        lp_clean = rider_lp_val.replace(" ", "_")
                        
                        daily_fid, daily_fname = get_rider_daily_folder(srv, MAIN_FOLDER_ID)
                        uploaded_ids = []

                        for i, img_bytes in enumerate(st.session_state.rider_photo_gallery):
                            fn = f"{lp_clean}_{ts}_{i+1}.jpg"
                            uid = upload_photo(srv, img_bytes, fn, daily_fid)
                            uploaded_ids.append(uid)
                        
                        for order in st.session_state.rider_scanned_orders:
                            target_ord_id = order['id']
                            save_rider_log(st.session_state.current_user_name, target_ord_id, uploaded_ids, daily_fname, rider_lp_val)
                        
                        st.markdown("""<div style="text-align: center;"><div style="font-size: 100px;">✅</div><h2 style="color: #28a745; margin-top: -20px;">บันทึกครบถ้วน!</h2></div>""", unsafe_allow_html=True)
                        time.sleep(2)
                        trigger_reset(); st.rerun()
        else:
            st.info("👈 Scan Tracking อย่างน้อย 1 รายการ")
