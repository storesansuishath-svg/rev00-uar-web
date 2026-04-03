import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io
import requests
from datetime import date, datetime

# ตั้งค่าหน้าเว็บ
st.set_page_config(page_title="REV.00 UAR System", layout="wide")
st.title("📂 ระบบ รวม UAR")

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

tab1, tab2, tab3 = st.tabs([
    "📊 แดชบอร์ด (Dashboard / ダッシュボード)", 
    "📝 บันทึกข้อมูล (Input / 入力)", 
    "🔍 ค้นหาข้อมูล (Search / 検索)"
])

# ==========================================
# TAB 1: แดชบอร์ด (Dashboard)
# ==========================================
with tab1:
    # --- ส่วนการจัดการวันที่ปัจจุบัน ---
    today = date.today()
    current_month_str = today.strftime('%m/%Y')
    
    df_dash = df.copy()
    
    # เตรียมข้อมูลวันที่สำหรับการกรอง
    date_strs = df_dash['วันที่\nDate / 日付'].astype(str).str.strip()
    df_dash['Date_Parsed'] = pd.to_datetime(date_strs, errors='coerce', dayfirst=True)
    df_dash['Score_Num'] = pd.to_numeric(df_dash['คะแนน\nScore / スコア'], errors='coerce').fillna(0.0)
    
    # สร้างรายการเดือนที่มีข้อมูล + เพิ่มเดือนปัจจุบันเข้าไปด้วย
    valid_dates_df = df_dash.dropna(subset=['Date_Parsed']).copy()
    valid_dates_df['Month_Year'] = valid_dates_df['Date_Parsed'].dt.strftime('%m/%Y')
    
    month_list = list(valid_dates_df['Month_Year'].unique())
    if current_month_str not in month_list:
        month_list.append(current_month_str)
    
    # เรียงลำดับเดือนจากใหม่ไปเก่า
    month_list = sorted(month_list, key=lambda x: datetime.strptime(x, '%m/%Y'), reverse=True)
    
    # แถบเลือกเดือนด้านบน
    selected_month = st.selectbox("📅 เลือกเดือนที่ต้องการตรวจสอบ (Select Month):", month_list, index=month_list.index(current_month_str))

    # --- ส่วนหัวแดชบอร์ดแบบเด่น (Prominent Header) ---
    st.markdown(f"""
        <div style="background-color:#f0f2f6; padding:20px; border-radius:10px; border-left: 8px solid #007bff; margin-bottom:20px;">
            <h1 style="margin:0; color:#1f1f1f; font-size:40px;">📅 ประจำเดือน: {selected_month}</h1>
            <p style="margin:0; color:#666;">สรุปผลคะแนน UAR/PAR แยกตามแผนก</p>
        </div>
    """, unsafe_allow_html=True)

    # กรองข้อมูล
    df_filtered = valid_dates_df[valid_dates_df['Month_Year'] == selected_month]
    sections = ["PD1-A", "PD1-B", "ASSY", "MS-1", "MS-2", "Delivery"]

    # --- 🌾 รุ่น Combine ---
    st.subheader("🌾 รุ่น Combine")
    combine_df = df_filtered[df_filtered['รุ่น\nModel / モデル'] == 'Combine']
    cols = st.columns(len(sections) + 1)
    for i, sec in enumerate(sections):
        score_sum = combine_df[combine_df['แผนก\nSection / 部署'] == sec]['Score_Num'].sum()
        cols[i].metric(label=sec, value=f"{score_sum:.1f}")
    cols[-1].metric(label="TOTAL", value=f"{combine_df['Score_Num'].sum():.1f}")
    
    st.divider()

    # --- 🚜 รุ่น Tractor ---
    st.markdown("#### 🚜 รุ่น Tractor")
    tractor_df = df_filtered[df_filtered['รุ่น\nModel / モデル'] == 'Tractor']
    t_cols = st.columns(len(sections) + 1)
    for i, sec in enumerate(sections):
        s = tractor_df[tractor_df['แผนก\nSection / 部署'] == sec]['Score_Num'].sum()
        t_cols[i].caption(f"**{sec}**")
        t_cols[i].markdown(f"### {s:.1f}")
    t_cols[-1].caption("**TOTAL**")
    t_cols[-1].markdown(f"### {tractor_df['Score_Num'].sum():.1f}")

    st.write("")

    # --- 🔄 รุ่น Rotary ---
    st.markdown("#### 🔄 รุ่น Rotary")
    rotary_df = df_filtered[df_filtered['รุ่น\nModel / モデル'] == 'Rotary']
    r_cols = st.columns(len(sections) + 1)
    for i, sec in enumerate(sections):
        s = rotary_df[rotary_df['แผนก\nSection / 部署'] == sec]['Score_Num'].sum()
        r_cols[i].caption(f"**{sec}**")
        r_cols[i].markdown(f"### {s:.1f}")
    r_cols[-1].caption("**TOTAL**")
    r_cols[-1].markdown(f"### {rotary_df['Score_Num'].sum():.1f}")

    st.divider()
    other_df = df_filtered[df_filtered['รุ่น\nModel / モデル'] == 'Other']
    st.metric(label="⚙️ รุ่น Other", value=f"{other_df['Score_Num'].sum():.1f}")

# ==========================================
# TAB 2: บันทึกข้อมูล
# ==========================================
with tab2:
    st.header("บันทึก UAR/PAR ใหม่ (New Entry / 新規登録)")

    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:
        with st.container():
            st.warning("🔐 พื้นที่จำกัดเฉพาะเจ้าหน้าที่")
            pwd_input = st.text_input("กรุณาใส่รหัสผ่าน:", type="password")
            if st.button("ยืนยันรหัสผ่าน"):
                if pwd_input == "S1234s":
                    st.session_state["authenticated"] = True
                    st.rerun()
                else:
                    st.error("รหัสผ่านไม่ถูกต้อง")
    else:
        if st.button("🔒 ออกจากระบบ (Logout)"):
            st.session_state["authenticated"] = False
            st.rerun()
        st.divider()
        with st.form("entry_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                next_no = 1
                if not df.empty:
                    col_no = pd.to_numeric(df.iloc[:, 0], errors='coerce')
                    next_no = int(col_no.max()) + 1 if not col_no.dropna().empty else 1
                st.info(f"ลำดับที่ (Auto): {next_no}")
                input_date = st.date_input("วันที่ (Date / 日付)", date.today())
                input_uar = st.text_input("หมายเลข UAR/PAR* (No. / 番号)")
                input_cust = st.text_input("ลูกค้า (Customer / 顧客)")
                input_section = st.selectbox("แผนก (Section / 部署)", ["PD1-A", "PD1-B", "ASSY", "MS-1", "MS-2", "Delivery"])
                input_model = st.selectbox("รุ่น (Model / モデル)", ["Combine", "Tractor", "Rotary", "Other"])
            with col2:
                input_score = st.text_input("คะแนน (Score / スコア)", value="0.0")
                input_prob = st.text_input("ปัญหา* (Problem / 問題)")
                input_detail = st.text_area("รายละเอียดปัญหา (Detail / 詳細)")
                input_job_code = st.text_input("รหัสงาน (Job Code / ジョブコード)")
                input_job_name = st.text_input("ชื่องาน (Job Name / ジョブ名)")
                input_pdf = st.file_uploader("อัพโหลด PDF +", type=["pdf"])
            submitted = st.form_submit_button("💾 บันทึกข้อมูล")
            if submitted:
                if not input_uar or not input_prob:
                    st.error("กรุณากรอกช่องที่มีเครื่องหมาย *")
                else:
                    try:
                        pdf_link = ""
                        if input_pdf:
                            with st.spinner('กำลังอัพโหลด...'):
                                pdf_link = upload_to_drive(input_pdf, f"UAR_{input_uar}_{date.today()}.pdf")
                        try:
                            clean_score = float(input_score)
                        except:
                            clean_score = 0.0
                        row_data = [
                            next_no, input_date.strftime("%d/%m/%Y"), input_uar, 
                            input_cust, input_section, input_model, input_prob, 
                            input_detail, input_job_code, input_job_name, f"{clean_score:.1f}", pdf_link
                        ]
                        get_worksheet().append_row(row_data)
                        send_line_notify(f"\n🔔 UAR ใหม่: {input_uar}\nแผนก: {input_section}\nรุ่น: {input_model}\nคะแนน: {clean_score:.1f}")
                        st.success("บันทึกเรียบร้อย!")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

# ==========================================
# TAB 3: ค้นหาข้อมูล (เพิ่มฟิลเตอร์ & ปุ่มดาวน์โหลด)
# ==========================================
with tab3:
    st.header("ฐานข้อมูล UAR ทั้งหมด")
    
    if not df.empty:
        # แบ่งหน้าจอเป็น 3 คอลัมน์สำหรับกล่องค้นหาและฟิลเตอร์
        f_col1, f_col2, f_col3 = st.columns(3)
        with f_col1:
            search_query = st.text_input("🔍 ค้นหาด้วยข้อความ...")
        with f_col2:
            section_list = df['แผนก\nSection / 部署'].dropna().unique().tolist()
            section_list = [s for s in section_list if str(s).strip() != ""] # กรองช่องว่างออก
            selected_sections = st.multiselect("🏷️ กรองตามแผนก:", section_list)
        with f_col3:
            model_list = df['รุ่น\nModel / モデル'].dropna().unique().tolist()
            model_list = [m for m in model_list if str(m).strip() != ""] # กรองช่องว่างออก
            selected_models = st.multiselect("🚜 กรองตามรุ่น:", model_list)

        # ทำการกรองข้อมูลตามฟิลเตอร์ที่เลือก
        display_df = df.copy()
        
        if selected_sections:
            display_df = display_df[display_df['แผนก\nSection / 部署'].isin(selected_sections)]
            
        if selected_models:
            display_df = display_df[display_df['รุ่น\nModel / モデル'].isin(selected_models)]
            
        if search_query:
            mask = display_df.astype(str).apply(lambda x: x.str.contains(search_query, case=False)).any(axis=1)
            display_df = display_df[mask]
            
        # เรียงข้อมูลใหม่ล่าสุดขึ้นก่อน
        display_df = display_df.sort_index(ascending=False)
        
        # จัดเลย์เอาต์ปุ่มดาวน์โหลดและจำนวนรายการ
        d_col1, d_col2 = st.columns([1, 2])
        with d_col1:
            st.markdown(f"**จำนวนผลลัพธ์:** {len(display_df)} รายการ")
        with d_col2:
            # แปลง DataFrame เป็นไฟล์ CSV (รองรับภาษาไทย/ญี่ปุ่นด้วย utf-8-sig)
            csv = display_df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
            st.download_button(
                label="📥 ดาวน์โหลดเป็นไฟล์ Excel (CSV)",
                data=csv,
                file_name=f"UAR_Export_{date.today().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )

        # แสดงตาราง
        st.dataframe(
            display_df, 
            use_container_width=True, 
            hide_index=True, 
            column_config={"ไฟล์ PDF\nPDF / PDFファイル": st.column_config.LinkColumn("เปิดไฟล์")}
        )
    else:
        st.info("ยังไม่มีข้อมูลในระบบ")
