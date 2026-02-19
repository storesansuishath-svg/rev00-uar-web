import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import requests
from datetime import date

st.set_page_config(page_title="REV.00 รวม UAR System", layout="wide")
st.title("📂 ระบบ REV.00 รวม UAR")

# --- 1. ตั้งค่าการเชื่อมต่อ Google Sheets ---
scopes = ["https://www.googleapis.com/auth/spreadsheets"]

# ระบบจะดึงกุญแจมาจาก Secrets ที่เราซ่อนไว้ (ตั้งค่าในหน้าเว็บ Streamlit ทีหลัง)
skey = st.secrets["gcp_service_account"]
credentials = Credentials.from_service_account_info(skey, scopes=scopes)
gc = gspread.authorize(credentials)

# ลิ้งค์ Google Sheet ของคุณ
SHEET_URL = "https://docs.google.com/spreadsheets/d/1iY8d-oyCf0lGZiLQZzJ0C_IbPRABzIb_nM2ChIxFg-M/edit"

@st.cache_data(ttl=10) # สั่งให้รีเฟรชข้อมูลทุก 10 วินาที
def load_data():
    sh = gc.open_by_url(SHEET_URL)
    worksheet = sh.sheet1
    data = worksheet.get_all_records()
    return pd.DataFrame(data), worksheet

df, worksheet = load_data()

# --- 2. ฟังก์ชันส่ง LINE Notify ---
def send_line_notify(message):
    token = st.secrets["line"]["token"]
    url = 'https://notify-api.line.me/api/notify'
    headers = {'Authorization': f'Bearer {token}'}
    data = {'message': message}
    requests.post(url, headers=headers, data=data)

# --- 3. หน้าจอการทำงาน ---
tab1, tab2 = st.tabs(["📝 บันทึกข้อมูล", "🔍 ค้นหาและดูข้อมูล"])

with tab1:
    st.header("บันทึก UAR/PAR ใหม่")
    with st.form("entry_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            # รันลำดับที่อัตโนมัติ (หาค่าแถวสุดท้าย)
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
                st.error("กรุณากรอก หมายเลข UAR/PAR และ ปัญหา")
            else:
                # ลำดับคอลัมน์ให้ตรงกับ Google Sheet (A ถึง H)
                row_data = [
                    next_no, input_date.strftime("%d/%m/%Y"), input_uar, 
                    input_cust, input_prob, input_detail, input_job_code, input_job_name
                ]
                
                # บันทึกลง Sheet
                worksheet.append_row(row_data)
                
                # แจ้งเตือนเข้า LINE
                msg = f"\n🔔 แจ้งเตือน UAR ใหม่!\nวันที่: {input_date.strftime('%d/%m/%Y')}\nUAR/PAR: {input_uar}\nลูกค้า: {input_cust}\nปัญหา: {input_prob}"
                send_line_notify(msg)
                
                st.success(f"บันทึกรายการ {input_uar} เรียบร้อยแล้ว!")
                st.cache_data.clear() # ล้างแคชเพื่อให้ตารางดึงข้อมูลใหม่ทันที

with tab2:
    st.header("ฐานข้อมูล UAR ทั้งหมด")
    search_query = st.text_input("🔍 พิมพ์คำที่ต้องการค้นหา (เช่น ชื่อลูกค้า, เลข UAR, รหัสงาน)")
    
    if not df.empty:
        if search_query:
            # ค้นหาในทุกคอลัมน์
            mask = df.astype(str).apply(lambda x: x.str.contains(search_query, case=False)).any(axis=1)
            filtered_df = df[mask]
            st.dataframe(filtered_df, use_container_width=True)
            st.caption(f"พบข้อมูลจำนวน {len(filtered_df)} รายการ")
        else:
            # ถ้าไม่ได้ค้นหา ให้แสดงทั้งหมดโดยเอารายการใหม่สุดขึ้นก่อน
            if "No." in df.columns:
                st.dataframe(df.sort_values(by="No.", ascending=False), use_container_width=True)
            else:
                st.dataframe(df, use_container_width=True)
            st.caption(f"ข้อมูลทั้งหมดจำนวน {len(df)} รายการ")
    else:
        st.info("ยังไม่มีข้อมูลในระบบ หรือหัวตารางใน Sheet ยังไม่ตรงกัน")
