import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import requests
from datetime import date

st.set_page_config(page_title="REV.00 รวม UAR System", layout="wide")
st.title("📂 ระบบ REV.00 รวม UAR")

# --- 1. ตั้งค่าการเชื่อมต่อ Google Sheets ---
# ใช้ cache_resource สำหรับการเชื่อมต่อหลัก (ไม่ตายบ่อย)
@st.cache_resource
def get_gs_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    skey = st.secrets["gcp_service_account"]
    credentials = Credentials.from_service_account_info(skey, scopes=scopes)
    return gspread.authorize(credentials)

gc = get_gs_client()
SHEET_URL = "https://docs.google.com/spreadsheets/d/1iY8d-oyCf0lGZiLQZzJ0C_IbPRABzIb_nM2ChIxFg-M/edit"

# ฟังก์ชันดึง Worksheet แบบสดๆ (ไม่ใช้ Cache)
def get_worksheet():
    sh = gc.open_by_url(SHEET_URL)
    return sh.sheet1

# ฟังก์ชันดึง Data (ใช้ Cache เพื่อความเร็ว)
@st.cache_data(ttl=10)
def load_data_df():
    ws = get_worksheet()
    data = ws.get_all_records()
    return pd.DataFrame(data)

# --- 2. ฟังก์ชันส่ง LINE ---
def send_line_notify(message):
    token = st.secrets["line"]["token"]
    url = 'https://notify-api.line.me/api/notify'
    headers = {'Authorization': f'Bearer {token}'}
    data = {'message': message}
    # ตรวจสอบว่าส่งสำเร็จไหม
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
            next_no = 1
            if not df.empty and "No." in df.columns:
                df['No.'] = pd.to_numeric(df['No.'], errors='coerce')
                next_no = int(df["No."].max(skipna=True)) + 1 if pd.notna(df["No."].max(skipna=True)) else 1
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
                    # ดึง Worksheet สดๆ มาเขียน
                    ws_to_write = get_worksheet()
                    row_data = [
                        next_no, input_date.strftime("%d/%m/%Y"), input_uar, 
                        input_cust, input_prob, input_detail, input_job_code, input_job_name
                    ]
                    ws_to_write.append_row(row_data)
                    
                    # แจ้งเตือน LINE
                    msg = f"\n🔔 แจ้ง UAR ใหม่!\nเลขที่: {input_uar}\nลูกค้า: {input_cust}\nปัญหา: {input_prob}"
                    status = send_line_notify(msg)
                    
                    st.success(f"บันทึกข้อมูล {input_uar} สำเร็จ!")
                    if status != 200:
                        st.warning("⚠️ บันทึกเข้า Sheet สำเร็จ แต่ส่ง LINE ไม่ได้ (ตรวจสอบ Token)")
                    
                    st.cache_data.clear() # ล้างแคชเพื่อให้ตารางอัปเดต
                except Exception as e:
                    st.error(f"เกิดข้อผิดพลาด: {e}")

with tab2:
    st.header("ฐานข้อมูล UAR ทั้งหมด")
    search_query = st.text_input("🔍 พิมพ์คีย์เวิร์ดที่ต้องการค้นหา...")
    if not df.empty:
        if search_query:
            mask = df.astype(str).apply(lambda x: x.str.contains(search_query, case=False)).any(axis=1)
            st.dataframe(df[mask], use_container_width=True)
        else:
            st.dataframe(df.sort_values(by="No.", ascending=False), use_container_width=True)
    else:
        st.info("ไม่พบข้อมูลในระบบ")
