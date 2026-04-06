import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io
import requests
from datetime import date, datetime
import plotly.express as px

# ตั้งค่าหน้าเว็บ
st.set_page_config(page_title="UAR SANSUISHA", layout="wide")

# --- CUSTOM CSS (ตกแต่ง Tabs ให้ดูเป็นมืออาชีพ) ---
st.markdown("""
    <style>
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #f8f9fa;
        border-radius: 8px 8px 0 0;
        padding: 10px 20px;
        box-shadow: inset 0 -2px 0 0 #e0e0e0;
    }
    .stTabs [aria-selected="true"] {
        background-color: white;
        box-shadow: inset 0 -3px 0 0 #0056b3;
        font-weight: 800 !important;
        color: #0056b3 !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- ส่วนหัวของเว็บ (Header & Logo) ---
col_logo, col_title = st.columns([5, 8])
with col_logo:
    # ⬇️ บรรทัดใส่ Logo อยู่ตรงนี้ครับ ⬇️
    st.image("https://lh3.googleusercontent.com/d/1zCjSjSbCO-mbsaGoDI6g0G-bfmyVfqFV", width=200)
    # ⬆️ บรรทัดใส่ Logo อยู่ตรงนี้ครับ ⬆️
    
with col_title:
    st.markdown("""
        <div style="padding-top: 5px;">
            <h1 style="margin: 0; font-size: 38px; font-weight: 900; color: #0056b3; line-height: 1.2;">UAR SANSUISHA</h1>
            <span style="color: #666; font-size: 15px; font-weight: 500;">Quality Assurance & Problem Tracking System</span>
        </div>
    """, unsafe_allow_html=True)

st.write("") # เว้นบรรทัด
st.divider()

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
        "ชื่องาน\nJob Name / ジョブ名", "คะแนน\nScore / สコア", "ไฟล์ PDF\nPDF / PDFファイル"
    ]
    
    if len(all_values) > 2:
        raw_data = all_values[2:] 
        processed_data = []
        for row in raw_data:
            padded_row = row + [""] * (len(headers) - len(row))
            processed_data.append(padded_row[:len(headers)])
        return pd.DataFrame(processed_data, columns=headers)
    return pd.DataFrame(columns=headers)

# --- 2. ฟังก์ชันเสริม (PDF, LINE, สีเกรด และ กราฟ) ---
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

def get_score_grade_html(score):
    if score == 0.0:
        val_color = "#28a745"; grade = "A"; grade_color = "#28a745"
    elif score <= 5.0:
        val_color = "#28a745"; grade = "B"; grade_color = "#28a745"
    elif score <= 20.0:
        val_color = "#dc3545"; grade = "C"; grade_color = "#dc3545"
    else:
        val_color = "#dc3545"; grade = "D"; grade_color = "#8b0000"
    return f'<span style="color:{val_color};">{score:.1f}</span> <span style="color:{grade_color}; font-weight:900; font-size:1.1em; margin-left:5px;">{grade}</span>'

def create_bar_chart(data, model_name, color):
    sections = ["PD1-A", "PD1-B", "ASSY", "MS-1", "MS-2", "Delivery"]
    model_data = data[data['รุ่น\nModel / モデル'] == model_name]
    
    scores = []
    cases = []
    for sec in sections:
        sec_data = model_data[model_data['แผนก\nSection / 部署'] == sec]
        scores.append(sec_data['Score_Num'].sum())
        cases.append(len(sec_data)) 
    
    chart_df = pd.DataFrame({
        "แผนก (Section)": sections, 
        "คะแนนรวม (Total Score)": scores,
        "จำนวนเคส (Cases)": cases
    })
    
    chart_df["Display_Text"] = chart_df.apply(
        lambda row: f"{row['คะแนนรวม (Total Score)']:.1f}<br>({int(row['จำนวนเคส (Cases)'])} case)", axis=1
    )
    
    fig = px.bar(
        chart_df, x="แผนก (Section)", y="คะแนนรวม (Total Score)",
        text="Display_Text",
        title=f"สรุปคะแนนรายแผนก: {model_name}",
        color_discrete_sequence=[color]
    )
    fig.update_traces(texttemplate='%{text}', textposition='outside')
    
    max_score = chart_df["คะแนนรวม (Total Score)"].max()
    fig.update_layout(
        yaxis_range=[0, max_score * 1.3] if max_score > 0 else [0, 5],
        yaxis=dict(title='คะแนน (Score)'),
        xaxis=dict(title='แผนก (Section)'),
        margin=dict(l=20, r=20, t=40, b=20),
        height=400 if model_name == "Combine" else 300,
        plot_bgcolor="rgba(0,0,0,0)"
    )
    return fig

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
    today = date.today()
    current_month_str = today.strftime('%m/%Y')
    df_dash = df.copy()
    
    # เตรียมข้อมูล
    date_strs = df_dash['วันที่\nDate / 日付'].astype(str).str.strip()
    df_dash['Date_Parsed'] = pd.to_datetime(date_strs, errors='coerce', dayfirst=True)
    df_dash['Score_Num'] = pd.to_numeric(df_dash['คะแนน\nScore / สコア'], errors='coerce').fillna(0.0)
    
    valid_dates_df = df_dash.dropna(subset=['Date_Parsed']).copy()
    valid_dates_df['Month_Year'] = valid_dates_df['Date_Parsed'].dt.strftime('%m/%Y')
    
    month_list = sorted(list(valid_dates_df['Month_Year'].unique()), 
                       key=lambda x: datetime.strptime(x, '%m/%Y'), reverse=True)
    
    # ส่วนหัวและตัวเลือก
    col_sel1, col_sel2 = st.columns([1, 1])
    with col_sel1:
        selected_month = st.selectbox("📅 เลือกเดือน (Select Month):", month_list)
    with col_sel2:
        # 📌 เพิ่มฟิลเตอร์แยก UAR / PAR
        view_mode = st.radio("🔍 รูปแบบการแสดงผล:", ["ทั้งหมด (All)", "เฉพาะ UAR (Score > 0)", "เฉพาะ PAR (Score = 0)"], horizontal=True)

    # กล่องแสดงนิยามและเดือน (เน้น UAR/PAR ให้ Khun Kato เห็นชัดๆ)
    st.markdown(f"""
        <div style="background-color:#e9f2fb; padding:20px; border-radius:10px; border-left: 8px solid #0056b3; margin-bottom:20px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
            <div style="float:right; text-align:right;">
                <span style="background-color:#dc3545; color:white; padding:2px 8px; border-radius:4px; font-size:12px;">UAR: หักคะแนน</span>
                <span style="background-color:#28a745; color:white; padding:2px 8px; border-radius:4px; font-size:12px; margin-left:5px;">PAR: 0 คะแนน</span>
            </div>
            <h1 style="margin:0; color:#1f1f1f; font-size:32px;">📅 ประจำเดือน: {selected_month}</h1>
            <p style="margin:0; color:#555;">สรุปสถานะคุณภาพแยกตามแผนกและประเภทรายการ</p>
        </div>
    """, unsafe_allow_html=True)

    # กรองข้อมูลตามเดือนและโหมดที่เลือก
    df_filtered = valid_dates_df[valid_dates_df['Month_Year'] == selected_month]
    
    if view_mode == "เฉพาะ UAR (Score > 0)":
        df_filtered = df_filtered[df_filtered['Score_Num'] > 0]
    elif view_mode == "เฉพาะ PAR (Score = 0)":
        df_filtered = df_filtered[df_filtered['Score_Num'] == 0]

    sections = ["PD1-A", "PD1-B", "ASSY", "MS-1", "MS-2", "Delivery"]

    # ฟังก์ชันช่วยคำนวณเคส UAR/PAR แยกกัน
    def get_uar_par_info(data):
        uar_cases = len(data[data['Score_Num'] > 0])
        par_cases = len(data[data['Score_Num'] == 0])
        total_score = data['Score_Num'].sum()
        return total_score, uar_cases, par_cases

    # --- 🌾 รุ่น Combine ---
    st.markdown("""
        <div style="background-color: #f0fdf4; border-left: 6px solid #28a745; padding: 10px 15px; border-radius: 8px; margin-bottom: 15px;">
            <h3 style="margin:0; color: #15803d;">🌾 รุ่น Combine</h3>
        </div>
    """, unsafe_allow_html=True)
    
    st.plotly_chart(create_bar_chart(df_filtered, "Combine", "#28a745"), use_container_width=True)
    
    combine_df = df_filtered[df_filtered['รุ่น\nModel / モデル'] == 'Combine']
    cols = st.columns(len(sections) + 1)
    
    for i, sec in enumerate(sections):
        sec_data = combine_df[combine_df['แผนก\nSection / 部署'] == sec]
        s_sum, u_case, p_case = get_uar_par_info(sec_data)
        # โชว์ Score และแยก UAR/PAR case
        cols[i].metric(label=sec, value=f"{s_sum:.1f}", delta=f"U:{u_case} | P:{p_case}", delta_color="off")
        
    c_score, c_u, c_p = get_uar_par_info(combine_df)
    cols[-1].markdown("<div style='font-size:12px; color:#555; font-weight:bold;'>TOTAL</div>", unsafe_allow_html=True)
    cols[-1].markdown(f"""
        <div style='margin-top:-5px;'>
            <h3 style='margin:0;'>{get_score_grade_html(c_score)}</h3>
            <div style='font-size:12px; color:gray;'>UAR: {c_u} | PAR: {c_p}</div>
        </div>
    """, unsafe_allow_html=True)
    
    st.divider()

    # --- 🚜 รุ่น Tractor & 🔄 รุ่น Rotary ---
    col_left, col_right = st.columns(2)
    
    with col_left:
        st.markdown("<div style='background-color:#eff6ff; border-left:5px solid #007bff; padding:10px; border-radius:5px;'><b>🚜 รุ่น Tractor</b></div>", unsafe_allow_html=True)
        st.plotly_chart(create_bar_chart(df_filtered, "Tractor", "#007bff"), use_container_width=True)
        t_df = df_filtered[df_filtered['รุ่น\nModel / モデル'] == 'Tractor']
        ts, tu, tp = get_uar_par_info(t_df)
        st.markdown(f"**Score:** {get_score_grade_html(ts)} &nbsp;&nbsp; <span style='color:gray;'>(UAR: {tu} | PAR: {tp})</span>", unsafe_allow_html=True)

    with col_right:
        st.markdown("<div style='background-color:#fffdf0; border-left:5px solid #ffc107; padding:10px; border-radius:5px;'><b>🔄 รุ่น Rotary</b></div>", unsafe_allow_html=True)
        st.plotly_chart(create_bar_chart(df_filtered, "Rotary", "#ffc107"), use_container_width=True)
        r_df = df_filtered[df_filtered['รุ่น\nModel / モデル'] == 'Rotary']
        rs, ru, rp = get_uar_par_info(r_df)
        st.markdown(f"**Score:** {get_score_grade_html(rs)} &nbsp;&nbsp; <span style='color:gray;'>(UAR: {ru} | PAR: {rp})</span>", unsafe_allow_html=True)

    st.divider()
    other_df = df_filtered[df_filtered['รุ่น\nModel / モデル'] == 'Other']
    os, ou, op = get_uar_par_info(other_df)
    st.markdown(f"**⚙️ รุ่น Other (TOTAL):** &nbsp;&nbsp; {get_score_grade_html(os)} &nbsp;&nbsp; <span style='color:gray;'>(UAR: {ou} | PAR: {op})</span>", unsafe_allow_html=True)
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
                input_score = st.text_input("คะแนน (Score / สコア)", value="0.0")
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
# TAB 3: ค้นหาข้อมูล
# ==========================================
with tab3:
    st.header("ฐานข้อมูล UAR ทั้งหมด")
    if not df.empty:
        f_col1, f_col2, f_col3 = st.columns(3)
        with f_col1:
            search_query = st.text_input("🔍 ค้นหาด้วยข้อความ...")
        with f_col2:
            section_list = df['แผนก\nSection / 部署'].dropna().unique().tolist()
            section_list = [s for s in section_list if str(s).strip() != ""] 
            selected_sections = st.multiselect("🏷️ กรองตามแผนก:", section_list)
        with f_col3:
            model_list = df['รุ่น\nModel / モデル'].dropna().unique().tolist()
            model_list = [m for m in model_list if str(m).strip() != ""] 
            selected_models = st.multiselect("🚜 กรองตามรุ่น:", model_list)
        display_df = df.copy()
        if selected_sections:
            display_df = display_df[display_df['แผนก\nSection / 部署'].isin(selected_sections)]
        if selected_models:
            display_df = display_df[display_df['รุ่น\nModel / モデル'].isin(selected_models)]
        if search_query:
            mask = display_df.astype(str).apply(lambda x: x.str.contains(search_query, case=False)).any(axis=1)
            display_df = display_df[mask]
        display_df = display_df.sort_index(ascending=False)
        d_col1, d_col2 = st.columns([1, 2])
        with d_col1:
            st.markdown(f"**จำนวนผลลัพธ์:** {len(display_df)} รายการ")
        with d_col2:
            csv = display_df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
            st.download_button(
                label="📥 ดาวน์โหลดเป็นไฟล์ Excel (CSV)",
                data=csv,
                file_name=f"UAR_Export_{date.today().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        st.dataframe(display_df, use_container_width=True, hide_index=True, column_config={"ไฟล์ PDF\nPDF / PDFファイル": st.column_config.LinkColumn("เปิดไฟล์")})
