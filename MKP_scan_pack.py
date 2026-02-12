# --- MANAGE USERS FUNCTIONS ---
def add_new_user_to_sheet(user_id, password, name, role):
    try:
        creds = get_credentials(); gc = gspread.authorize(creds)
        sh = gc.open_by_key(ORDER_CHECK_SHEET_ID)
        ws = sh.worksheet(USER_SHEET_NAME)
        
        # [UPDATED FIX] ตรวจสอบ ID ซ้ำ (Normalizing)
        existing_ids = ws.col_values(1) # ดึง ID ทั้งหมดมา
        
        # แปลง ID ในระบบให้เป็นตัวเล็กและตัดช่องว่าง เพื่อการตรวจสอบ
        clean_existing = [str(x).strip().lower() for x in existing_ids if str(x).strip() != '']
        
        # แปลง ID ที่กรอกเข้ามาเหมือนกัน
        clean_new_id = str(user_id).strip().lower()

        if clean_new_id in clean_existing:
            return False, f"❌ ID '{user_id}' มีอยู่ในระบบแล้ว (ห้ามซ้ำ)"
        
        # เพิ่มข้อมูล (บันทึกค่าจริงตามที่ User พิมพ์)
        ws.append_row([str(user_id).strip(), str(password).strip(), str(name).strip(), str(role)])
        load_sheet_data.clear() 
        return True, f"✅ เพิ่มพนักงาน {name} ({role}) เรียบร้อย"
    except Exception as e:
        return False, f"Error: {e}"
