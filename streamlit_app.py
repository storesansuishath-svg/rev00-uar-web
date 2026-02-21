import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import requests
from datetime import date

st.set_page_config(page_title="REV.00 รวม UAR System", layout="wide")
st.title("📂 ระบบ REV.00 รวม UAR")

# --- 1. ตั้งค่าการเชื่อมต่อ Google Sheets ---
@st.cache_resource
def get_gs_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    skey = st.secrets["gcp_service_account"]
    credentials = Credentials.from_service_account_info(skey, scopes=scopes)
    return gspread.authorize(credentials)

gc = get_gs_client()
SHEET_URL = "https://docs.google.com/spreadsheets/d/1iY8d-oyCf0lGZiLQZzJ0C_IbPRABzIb_nM2ChIxFg-M/edit"

def get_worksheet():
    sh = gc.open_by_url(SHEET_URL)
    return sh.sheet1

@st.cache_data(ttl=10)
def load_data_df():
    ws = get_worksheet()
    # ดึงข้อมูลทั้งหมดเป็น List ของ List
    all_values = ws.get_all_values()
    
    if len(all_values) > 1:
        # ใช้แถวที่ 2 (index 1) ซึ่งเป็นภาษาไทย เป็นหัวตาราง
        headers = all_values[1] 
        # ข้อมูลจริงเริ่มตั้งแต่แถวที่ 3 (index 2) เป็นต้นไป
        data = all_values[2:] 
        return pd.DataFrame(data, columns=headers)
    else:
        return pd.DataFrame()

# --- 2. ฟังก์ชันส่ง LINE ---
def send_line_notify(message):
    token = st.secrets["line"]["token"]
    url = 'https://notify-api.line.me/api/notify'
    headers = {'Authorization': f'Bearer {token}'}
    data = {'message': message}
    response = requests.post(url, headers=headers, data=data)
    return response.status_code

# --- 3. หน้าจอการทำงาน ---
df = load_data_df()
tab1, tab2 = st.tabs(["📝 บันทึกข้อมูล", "🔍 ค้นหาและดูข้อมูล"])

with tab1:
    st.header("บันทึก UAR/PAR ใหม่")
    with st.form("entry_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            # รันเลขลำดับโดยเช็คจากคอลัมน์ "ลำดับที่"
            next_no = 1
            if not df.empty and "ลำดับที่" in df.columns:
                col_no = pd.to_numeric(df["ลำดับที่"], errors='coerce')
                next_no = int(col_no.max()) + 1 if not col_no.dropna().empty else 1
            
            st.info(f"ลำดับที่ (Auto): {next_no}")
            input_date = st.date_input("วันที่", date.today())
            input_uar = st.text_input("หมายเลข UAR/PAR*")
            input_cust = st.text_input("ลูกค้า")
            input_job_code = st.text_input("รหัสงาน")
        with col2:
            input_prob = st.text_input("ปัญหา (หัวข้อ)*")
            input_detail = st.text_area("รายละเอียดปัญหา")
            input_job_name = st.text_input("ชื่องาน")
        
        submitted = st.form_submit_button("💾 บันทึกข้อมูล")
        
        if submitted:
            if input_uar == "" or input_prob == "":
                st.error("กรุณากรอกข้อมูลที่จำเป็น (*) ให้ครบถ้วน")
            else:
                try:
                    ws_to_write = get_worksheet()
                    # เตรียมข้อมูลให้ตรงกับหัวตารางใน Sheet (8 คอลัมน์)
                    row_data = [
                        next_no, 
                        input_date.strftime("%d/%m/%Y"), 
                        input_uar, 
                        input_cust, 
                        input_prob, 
                        input_detail, 
                        input_job_code, 
                        input_job_name
                    ]
                    ws_to_write.append_row(row_data)
                    
                    msg = f"\n🔔 แจ้ง UAR ใหม่!\nลำดับ: {next_no}\nเลขที่: {input_uar}\nลูกค้า: {input_cust}\nปัญหา: {input_prob}"
                    send_line_notify(msg)
                    
                    st.success(f"บันทึกข้อมูล {input_uar} สำเร็จ!")
                    st.cache_data.clear() 
                    st.rerun() # รีโหลดหน้าเพื่ออัปเดตเลขลำดับใหม่ทันที
                except Exception as e:
                    st.error(f"เกิดข้อผิดพลาด: {e}")

with tab2:
    st.header("ฐานข้อมูล UAR ทั้งหมด")
    search_query = st.text_input("🔍 พิมพ์คีย์เวิร์ดเพื่อค้นหา (เช่น ชื่อลูกค้า, เลข UAR, ปัญหา)...")
    if not df.empty:
        if search_query:
            # ค้นหาคำในทุกคอลัมน์
            mask = df.astype(str).apply(lambda x: x.str.contains(search_query, case=False)).any(axis=1)
            st.dataframe(df[mask], use_container_width=True, hide_index=True)
