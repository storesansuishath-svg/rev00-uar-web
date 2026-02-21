import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io
import requests
from datetime import date

st.set_page_config(page_title="REV.00 UAR System", layout="wide")
st.title("📂 ระบบ REV.00 รวม UAR")

# --- 1. ตั้งค่าการเชื่อมต่อ (Sheets & Drive) ---
@st.cache_resource
def get_gcp_services():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file"
    ]
    skey = st.secrets["gcp_service_account"]
    credentials = Credentials.from_service_account_info(skey, scopes=scopes)
    gc = gspread.authorize(credentials)
    drive_service = build('drive', 'v3', credentials=credentials)
    return gc, drive_service

gc, drive_service = get_gcp_services()
SHEET_URL = "https://docs.google.com/spreadsheets/d/1iY8d-oyCf0lGZiLQZzJ0C_IbPRABzIb_nM2ChIxFg-M/edit"
DRIVE_FOLDER_ID = "18XFZzWJtATFOIhUT48S2Xz-NzB7VU735"

def get_worksheet():
    sh = gc.open_by_url(SHEET_URL)
    return sh.sheet1

@st.cache_data(ttl=10)
def load_data_df():
    ws = get_worksheet()
    all_values = ws.get_all_values()
    if len(all_values) > 1:
        # กำหนดหัวตารางใหม่ที่มีภาษาญี่ปุ่นกำกับ
        headers = [
            "ลำดับที่\nNo. / 番号", "วันที่\nDate / 日付", "หมายเลข UAR/PAR\nUAR/PAR No. / UAR/PAR番号",
            "ลูกค้า\nCustomer / 顧客", "ปัญหา\nProblem / 問題", "รายละเอียด\nDetail / 詳細",
            "รหัสงาน\nJob Code / ジョブコード", "ชื่องาน\nJob Name / ジョブ名",
            "คะแนน\nScore / スコア", "ไฟล์ PDF\nPDF / PDFファイル"
        ]
        data = all_values[2:] 
        return pd.DataFrame(data, columns=headers[:len(all_values[1])])
    return pd.DataFrame()

# --- 2. ฟังก์ชันอัพโหลดไฟล์ไป Google Drive ---
def upload_to_drive(file, filename):
    file_metadata = {'name': filename, 'parents': [DRIVE_FOLDER_ID]}
    media = MediaIoBaseUpload(io.BytesIO(file.getvalue()), mimetype='application/pdf')
    uploaded_file = drive_service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
    return uploaded_file.get('webViewLink')

# --- 3. ส่วนการแจ้งเตือน LINE ---
def send_line_notify(message):
    token = st.secrets["line"]["token"]
    headers = {'Authorization': f'Bearer {token}'}
    requests.post('https://notify-api.line.me/api/notify', headers=headers, data={'message': message})

# --- 4. หน้าจอการทำงาน ---
df = load_data_df()
tab1, tab2 = st.tabs(["📝 บันทึกข้อมูล (入力)", "🔍 ค้นหาข้อมูล (検索)"])

with tab1:
    st.header("บันทึก UAR/PAR ใหม่ (新規登録)")
    with st.form("entry_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            st.info(f"ลำดับที่ (Auto): {len(df)+1}")
            input_date = st.date_input("วันที่ (日付)", date.today())
            input_uar = st.text_input("หมายเลข UAR/PAR* (番号)")
            input_cust = st.text_input("ลูกค้า (顧客)")
            input_job_code = st.text_input("รหัสงาน (ジョブコード)")
            input_score = st.slider("คะแนน (スコア)", 0, 100, 50) # เพิ่มช่องคะแนน
        with col2:
            input_prob = st.text_input("ปัญหา* (問題)")
            input_detail = st.text_area("รายละเอียดปัญหา (詳細)")
            input_job_name = st.text_input("ชื่องาน (ジョブ名)")
            input_pdf = st.file_uploader("อัพโหลด PDF (PDFアップロード) +", type=["pdf"]) # เพิ่มช่องอัพโหลด
        
        submitted = st.form_submit_button("💾 บันทึกข้อมูล (保存)")
        
        if submitted:
            if not input_uar or not input_prob:
                st.error("กรุณากรอกข้อมูลที่จำเป็น (*) ให้ครบถ้วน")
            else:
                try:
                    pdf_link = ""
                    if input_pdf:
                        with st.spinner('กำลังอัพโหลดไฟล์...'):
                            pdf_link = upload_to_drive(input_pdf, f"{input_uar}.pdf")
                    
                    ws = get_worksheet()
                    row_data = [
                        len(df)+1, input_date.strftime("%d/%m/%Y"), input_uar, 
                        input_cust, input_prob, input_detail, input_job_code, 
                        input_job_name, input_score, pdf_link
                    ]
                    ws.append_row(row_data)
                    send_line_notify(f"\n🔔 แจ้ง UAR ใหม่!\nเลขที่: {input_uar}\nคะแนน: {input_score}")
                    st.success("บันทึกสำเร็จ! (保存完了)")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

with tab2:
    st.header("ฐานข้อมูล UAR ทั้งหมด (データベース)")
    search_query = st.text_input("🔍 ค้นหา (検索)...")
    if not df.empty:
        # แสดงตารางพร้อมลิ้งค์ PDF ที่กดได้
        st.dataframe(df, use_container_width=True, hide_index=True, column_config={
            "ไฟล์ PDF\nPDF / PDFファイル": st.column_config.LinkColumn("เปิดไฟล์ (開く)")
        })
