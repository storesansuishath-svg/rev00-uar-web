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
    headers = [
        "ลำดับที่\nNo. / 番号", "วันที่\nDate / 日付", "หมายเลข UAR/PAR\nNo. / UAR/PAR番号",
        "ลูกค้า\nCustomer / 顧客", "แผนก\nSection / 部署", "รุ่น\nModel / モデル",
        "ปัญหา\nProblem / 問題", "รายละเอียด\nDetail / 詳細", "รหัสงาน\nJob Code / ジョブコード", 
        "ชื่องาน\nJob Name / ジョブ名", "คะแนน\nScore / スコア", "ไฟล์ PDF\nPDF / PDFファイル"
    ]
    
    if len(all_values) > 2:
        raw_data = all_values[2:] 
        processed_data = []
        for row in raw_data:
            padded_row = row + [""] * (len(headers) - len(row))
            processed_data.append(padded_row[:len(headers)])
        return pd.DataFrame(processed_data, columns=headers)
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

tab1, tab2, tab3 = st.tabs(["📊 แดชบอร์ด (Dashboard)", "📝 บันทึกข้อมูล (入力)", "🔍 ค้นหาข้อมูล (検索)"])

# ==========================================
# TAB 1: แดชบอร์ด (Dashboard)
# ==========================================
with tab1:
    st.header("📊 แดชบอร์ดสรุปผลคะแนน")
    
    df_dash = df.copy()
    if not df_dash.empty:
        # ปรับการอ่านวันที่ให้ยืดหยุ่นขึ้น (ไม่ล็อค Format)
        df_dash['Date_Parsed'] = pd.to_datetime(df_dash['วันที่\nDate / 日付'], errors='coerce', dayfirst=True)
        df_dash['Score_Num'] = pd.to_numeric(df_dash['คะแนน\nScore / スコア'], errors='coerce').fillna(0)
        
        # คัดเอาเฉพาะแถวที่ระบบแปลงวันที่สำเร็จ
        valid_dates_df = df_dash.dropna(subset=['Date_Parsed']).copy()
        
        if not valid_dates_df.empty:
            valid_dates_df['Month_Year'] = valid_dates_df['Date_Parsed'].dt.strftime('%m/%Y')
            unique_months = valid_dates_df['Month_Year'].unique()
            unique_months = sorted(unique_months, key=lambda x: pd.to_datetime(x, format='%m/%Y'), reverse=True)
            
            selected_month = st.selectbox("📅 เลือกเดือนที่ต้องการดูข้อมูล:", unique_months)
            df_filtered = valid_dates_df[valid_dates_df['Month_Year'] == selected_month]
            
            st.markdown(f"**จำนวน UAR ทั้งหมดในเดือนนี้:** {len(df_filtered)} รายการ")
            
            # --- การ์ดใหญ่ (Combine) ---
            st.markdown("### 🌾 รุ่น Combine (รวมคะแนนแยกตามแผนก)")
            combine_df = df_filtered[df_filtered['รุ่น\nModel / モデル'] == 'Combine']
            sections = ["PD1-A", "PD1-B", "ASSY", "MS-1", "MS-2", "Delivery"]
            cols = st.columns(len(sections))
            for i, sec in enumerate(sections):
                score_sum = combine_df[combine_df['แผนก\nSection / 部署'] == sec]['Score_Num'].sum()
                cols[i].metric(label=sec, value=f"{int(score_sum)}")
            
            st.divider()
            
            # --- การ์ดเล็ก (Tractor, Rotary, Other) ---
            st.markdown("### 🚜 รุ่นอื่นๆ (รวมคะแนน)")
            cols_small = st.columns(3)
            models_small = ["Tractor", "Rotary", "Other"]
            icons = ["🚜 Tractor", "🔄 Rotary", "⚙️ Other"]
            
            for i, mod in enumerate(models_small):
                score_sum = df_filtered[df_filtered['รุ่น\nModel / モデル'] == mod]['Score_Num'].sum()
                cols_small[i].metric(label=icons[i], value=f"{int(score_sum)}")
                
        else:
            st.warning("⚠️ พบข้อมูลในระบบ แต่ระบบอ่านรูปแบบวันที่ไม่ออก (กรุณาตรวจสอบคอลัมน์ 'วันที่' ใน Google Sheet ว่าใส่ข้อมูลครบหรือไม่)")
    else:
        st.info("ยังไม่มีข้อมูลในระบบ หรือยังไม่ได้บันทึก UAR แรก")

# ==========================================
# TAB 2: บันทึกข้อมูล
# ==========================================
with tab2:
    st.header("บันทึก UAR/PAR ใหม่ (新規登録)")
    with st.form("entry_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            next_no = 1
            if not df.empty:
                col_no = pd.to_numeric(df.iloc[:, 0], errors='coerce')
                next_no = int(col_no.max()) + 1 if not col_no.dropna().empty else 1
            
            st.info(f"ลำดับที่ (Auto): {next_no}")
            
            # วันที่แบบมีปฏิทินให้จิ้มเลือก (จะแสดงผลเป็น YYYY/MM/DD บนฟอร์ม แต่จะเซฟเป็น DD/MM/YYYY)
            input_date = st.date_input("วันที่ (日付)", date.today())
            
            input_uar = st.text_input("หมายเลข UAR/PAR* (番号)")
            input_cust = st.text_input("ลูกค้า (顧客)")
            input_section = st.selectbox("แผนก (Section / 部署)", ["PD1-A", "PD1-B", "ASSY", "MS-1", "MS-2", "Delivery"])
            input_model = st.selectbox("รุ่น (Model / モデル)", ["Combine", "Tractor", "Rotary", "Other"])
            
        with col2:
            input_score = st.text_input("คะแนน (Score / スコア)", value="0")
            input_prob = st.text_input("ปัญหา* (問題)")
            input_detail = st.text_area("รายละเอียดปัญหา (詳細)")
            input_job_code = st.text_input("รหัสงาน (ジョブコード)")
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
                        with st.spinner('กำลังอัพโหลดไฟล์ PDF...'):
                            pdf_link = upload_to_drive(input_pdf, f"UAR_{input_uar}_{date.today()}.pdf")
                    
                    row_data = [
                        next_no, input_date.strftime("%d/%m/%Y"), input_uar, 
                        input_cust, input_section, input_model, input_prob, 
                        input_detail, input_job_code, input_job_name, input_score, pdf_link
                    ]
                    get_worksheet().append_row(row_data)
                    
                    send_line_notify(f"\n🔔 UAR ใหม่: {input_uar}\nแผนก: {input_section}\nรุ่น: {input_model}\nคะแนน: {input_score}")
                    
                    st.success("บันทึกข้อมูลเรียบร้อยแล้ว!")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"เกิดข้อผิดพลาด: {e}")

# ==========================================
# TAB 3: ค้นหาข้อมูล
# ==========================================
with tab3:
    st.header("ฐานข้อมูล UAR ทั้งหมด (データベース)")
    search_query = st.text_input("🔍 ค้นหา (ลูกค้า, แผนก, รุ่น, เลข UAR, ปัญหา)...")
    
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
