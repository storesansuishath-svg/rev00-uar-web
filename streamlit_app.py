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

# --- 1. ตั้งค่าการเชื่อมต่อ ---
@st.cache_resource
def get_gcp_services():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive.file"]
    skey = st.secrets["gcp_service_account"]
    credentials = Credentials.from_service_account_info(skey, scopes=scopes)
    gc = gspread.authorize(credentials)
    drive_service = build('drive', 'v3', credentials=credentials)
    return gc, drive_service

gc, drive_service = get_gcp_services()
SHEET_URL = "https://docs.google.com/spreadsheets/d/1iY8d-oyCf0lGZiLQZzJ0C_IbPRABzIb_nM2ChIxFg-M/edit"
DRIVE_FOLDER_ID = "18XFZzWJtATFOIhUT48S2Xz-NzB7VU735" # ใส่ Folder ID ของคุณแล้ว

def get_worksheet():
    sh = gc.open_by_url(SHEET_URL)
    return sh.sheet1

@st.cache_data(ttl=10)
def load_data_df():
    ws = get_worksheet()
    all_values = ws.get_all_values()
    if len(all_values) > 1:
        # หัวตารางแบบ 3 ภาษา
        headers = [
            "ลำดับที่\nNo. / 番号", "วันที่\nDate / 日付", "หมายเลข UAR/PAR\nNo. / UAR/PAR番号",
            "ลูกค้า\nCustomer / 顧客", "ปัญหา\nProblem / 問題", "รายละเอียด\nDetail / 詳細",
            "รหัสงาน\nJob Code / ジョブコード", "ชื่องาน\nJob Name / ジョブ名",
            "คะแนน\nScore / スコア", "ไฟล์ PDF\nPDF / PDFファイル"
        ]
        data = all_values[2:] 
        return pd.DataFrame(data, columns=headers[:len(all_values[1])])
    return pd.DataFrame()

# --- 2. ฟังก์ชันอัพโหลด PDF ---
def upload_to_drive(file, filename):
    file_metadata = {'name': filename, 'parents': [DRIVE_FOLDER_ID]}
    media = MediaIoBaseUpload(io.BytesIO(file.getvalue()), mimetype='application/pdf')
    uploaded_file = drive_service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
    # ปรับสิทธิ์ให้ทุกคนที่มีลิ้งค์ดูได้
    drive_service.permissions().create(fileId=uploaded_file.get('id'), body={'type': 'anyone', 'role': 'viewer'}).execute()
    return uploaded_file.get('webViewLink')

# --- 3. หน้าจอการทำงาน ---
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
            input_score = st.number_input("คะแนน (スコア)", 0, 100, 0)
        with col2:
            input_prob = st.text_input("ปัญหา* (問題)")
            input_detail = st.text_area("รายละเอียดปัญหา (詳細)")
            input_job_name = st.text_input("ชื่องาน (ジョブ名)")
            input_pdf = st.file_uploader("อัพโหลด PDF (PDFアップロード) +", type=["pdf"])
        
        submitted = st.form_submit_button("💾 บันทึกข้อมูล (保存)")
        
        if submitted:
            if not input_uar or not input_prob:
                st.error("กรุณากรอกช่องที่มีเครื่องหมาย *")
            else:
                try:
                    pdf_link = ""
                    if input_pdf:
                        with st.spinner('กำลังอัพโหลดไฟล์...'):
                            pdf_link = upload_to_drive(input_pdf, f"{input_uar}.pdf")
                    
                    row_data = [
                        len(df)+1, input_date.strftime("%d/%m/%Y"), input_uar, 
                        input_cust, input_prob, input_detail, "", # รหัสงาน (ถ้าไม่ได้ใส่ช่อง input)
                        input_job_name, input_score, pdf_link
                    ]
                    get_worksheet().append_row(row_data)
                    st.success("บันทึกและอัพโหลดไฟล์เรียบร้อย!")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"เกิดข้อผิดพลาด: {e}")

with tab2:
    st.header("ฐานข้อมูล UAR ทั้งหมด (データベース)")
    if not df.empty:
        st.dataframe(df, use_container_width=True, hide_index=True, column_config={
            "ไฟล์ PDF\nPDF / PDFファイル": st.column_config.LinkColumn("คลิกเพื่อเปิด (開く)")
        })
