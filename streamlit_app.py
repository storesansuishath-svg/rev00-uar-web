import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io
import requests
from datetime import date

# ตั้งค่าหน้าเว็บ
st.set_page_config(page_title="REV.00 UAR System", layout="wide")
st.title("📂 ระบบ REV.00 รวม UAR")

# --- 1. การเชื่อมต่อ Google Services ---
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
DRIVE_FOLDER_ID = "18XFZzWJtATFOIhUT48S2Xz-NzB7VU735"

def get_worksheet():
    sh = gc.open_by_url(SHEET_URL)
    return sh.sheet1

@st.cache_data(ttl=5)
def load_data_df():
    ws = get_worksheet()
    all_values = ws.get_all_values()
    # กำหนดหัวตาราง 12 คอลัมน์ (เพิ่ม รุ่น / Model)
    headers = [
        "ลำดับที่\nNo. / 番号", "วันที่\nDate / 日付", "หมายเลข UAR/PAR\nNo. / UAR/PAR番号",
        "ลูกค้า\nCustomer / 顧客", "แผนก\nSection / 部署", "รุ่น\nModel / モデル",
        "ปัญหา\nProblem / 問題", "รายละเอียด\nDetail / 詳細", "รหัสงาน\nJob Code / ジョブコード", 
        "ชื่องาน\nJob Name / ジョブ名", "คะแนน\nScore / スコア", "ไฟล์ PDF\nPDF / PDFファイル"
    ]
    if len(all_values) > 2:
        data = all_values[2:] 
        return pd.DataFrame(data, columns=headers)
    return pd.DataFrame(columns=headers)

# --- 2. ฟังก์ชันเสริม (PDF & LINE) ---
def upload_to_drive(file, filename):
    file_metadata = {'name': filename, 'parents': [DRIVE_FOLDER_ID]}
    media = MediaIoBaseUpload(io.BytesIO(file.getvalue()), mimetype='application/pdf')
    uploaded_file = drive_service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
    drive_service.permissions().create(fileId=uploaded_file.get('id'), body={'type': 'anyone', 'role': 'viewer'}).execute()
    return uploaded_file.get('webViewLink')

def send_line_notify(message):
    token = st.secrets["line"]["token"]
    headers = {'Authorization': f'Bearer {token}'}
    requests.post('https://notify-api.line.me/api/notify', headers=headers, data={'message': message})

# --- 3. หน้าจอการทำงาน ---
df = load_data_df()
tab1, tab2 = st.tabs(["📝 บันทึกข้อมูล (入力)", "🔍 ค้นหาข้อมูล (検索)"])

with tab1:
    st.header("บันทึก UAR/PAR ใหม่ (新規登録)")
    with st.form("entry_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            next_no = 1
            if not df.empty:
                col_no = pd.to_numeric(df.iloc[:, 0], errors='coerce')
                next_no = int(col_no.max()) + 1 if not col_no.dropna().empty else 1
            
            st.info(f"ลำดับที่ (Auto): {next_no}")
            input_date = st.date_input("วันที่ (日付)", date.today())
            input_uar = st.text_input("หมายเลข UAR/PAR* (番号)")
            input_cust = st.text_input("ลูกค้า (顧客)")
            input_section = st.text_input("แผนก (Section / 部署)")
            # --- เปลี่ยนเป็นช่องเลือก Model ---
            input_model = st.selectbox("รุ่น (Model / モデル)", ["Combine", "Tractor", "Rotary", "Other"])
            
        with col2:
            input_score = st.text_input("คะแนน (Score / スコア)")
            input_prob = st.text_input("ปัญหา* (問題)")
            input_detail = st.text_area("รายละเอียดปัญหา (詳細)")
            input_job_code = st.text_input("รหัสงาน (ジョブコード)")
            input_job_name = st.text_input("ชื่องาน (ジョブ名)")
            input_pdf = st.file_uploader("อัพโหลด PDF (PDFアップโหลด) +", type=["pdf"])
        
        submitted = st.form_submit_button("💾 บันทึกข้อมูล (保存)")
        
        if submitted:
            if not input_uar or not input_prob:
                st.error("กรุณากรอกช่องที่มีเครื่องหมาย *")
            else:
                try:
                    pdf_link = ""
                    if input_pdf:
                        with st.spinner('กำลังอัพโหลดไฟล์ PDF...'):
                            pdf_link = upload_to_drive(input_pdf, f"UAR_{input_uar}_{date.today()}.pdf")
                    
                    # เรียงข้อมูล 12 ช่องให้ตรงกับหัวตารางใหม่
                    row_data = [
                        next_no, input_date.strftime("%d/%m/%Y"), input_uar, 
                        input_cust, input_section, input_model, input_prob, 
                        input_detail, input_job_code, input_job_name, input_score, pdf_link
                    ]
                    get_worksheet().append_row(row_data)
                    
                    # ส่ง LINE Notify พร้อมข้อมูลรุ่น
                    send_line_notify(f"\n🔔 UAR ใหม่: {input_uar}\nรุ่น: {input_model}\nคะแนน: {input_score}")
                    
                    st.success("บันทึกข้อมูลเรียบร้อยแล้ว!")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"เกิดข้อผิดพลาด: {e}")

with tab2:
    st.header("ฐานข้อมูล UAR ทั้งหมด (データベース)")
    search_query = st.text_input("🔍 ค้นหา (ลูกค้า, รุ่น, แผนก, เลข UAR, ปัญหา)...")
    
    if not df.empty:
        if search_query:
            mask = df.astype(str).apply(lambda x: x.str.contains(search_query, case=False)).any(axis=1)
            display_df = df[mask]
        else:
            display_df = df.sort_index(ascending=False)
            
        st.dataframe(
            display_df, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "ไฟล์ PDF\nPDF / PDFファイル": st.column_config.LinkColumn("เปิดไฟล์ (開く)")
            }
        )
        st.caption(f"พบข้อมูลทั้งหมด {len(display_df)} รายการ")
    else:
        st.info("ยังไม่มีข้อมูลในระบบ")
