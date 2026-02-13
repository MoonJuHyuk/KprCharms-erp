import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import datetime
import os
import time
import altair as alt
import base64
import numpy as np
import io
import random

# --- 0. 아이콘 설정 함수 ---
def add_apple_touch_icon(image_path):
    try:
        if os.path.exists(image_path):
            with open(image_path, "rb") as f:
                b64_icon = base64.b64encode(f.read()).decode("utf-8")
                st.markdown(
                    f"""
                    <head>
                        <link rel="icon" type="image/png" href="data:image/png;base64,{b64_icon}">
                        <link rel="shortcut icon" href="data:image/png;base64,{b64_icon}">
                        <link rel="apple-touch-icon" href="data:image/png;base64,{b64_icon}">
                        <link rel="apple-touch-icon" sizes="180x180" href="data:image/png;base64,{b64_icon}">
                        <link rel="icon" sizes="192x192" href="data:image/png;base64,{b64_icon}">
                    </head>
                    """,
                    unsafe_allow_html=True
                )
    except Exception as e: pass

# --- 1. 페이지 설정 ---
if os.path.exists("logo.png"):
    st.set_page_config(page_title="KPR ERP", page_icon="logo.png", layout="wide")
    add_apple_touch_icon("logo.png")
else:
    st.set_page_config(page_title="KPR ERP", page_icon="🏭", layout="wide")

# --- 2. 구글 시트 연결 ---
@st.cache_resource
def get_connection():
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    spreadsheet_id = "1qLWcLwS-aTBPeCn39h0bobuZlpyepfY5Hqn-hsP-hvk"
    try:
        if "gcp_service_account" in st.secrets:
            key_dict = dict(st.secrets["gcp_service_account"])
            creds = Credentials.from_service_account_info(key_dict, scopes=scopes)
            client = gspread.authorize(creds)
            return client.open_by_key(spreadsheet_id)
    except Exception: pass
    key_file = 'key.json'
    if os.path.exists(key_file):
        creds = Credentials.from_service_account_file(key_file, scopes=scopes)
        client = gspread.authorize(creds)
        return client.open_by_key(spreadsheet_id)
    return None

doc = get_connection()

def get_sheet(doc, name):
    try: return doc.worksheet(name)
    except: return None

sheet_items = get_sheet(doc, 'Items')
sheet_inventory = get_sheet(doc, 'Inventory')
sheet_logs = get_sheet(doc, 'Logs')
sheet_bom = get_sheet(doc, 'BOM')
sheet_orders = get_sheet(doc, 'Orders')
sheet_wastewater = get_sheet(doc, 'Wastewater')

# --- 3. 데이터 로딩 ---
@st.cache_data(ttl=60)
def load_data():
    data = []
    sheets = [sheet_items, sheet_inventory, sheet_logs, sheet_bom, sheet_orders, sheet_wastewater]
    for s in sheets:
        df = pd.DataFrame()
        if s:
            for attempt in range(5):
                try:
                    d = s.get_all_records()
                    if d:
                        df = pd.DataFrame(d)
                        df = df.replace([np.inf, -np.inf], np.nan).fillna("")
                        if '수량' in df.columns:
                            df['수량'] = pd.to_numeric(df['수량'], errors='coerce').fillna(0.0)
                    break
                except: time.sleep(1)
        data.append(df)
    
    try:
        s_map = get_sheet(doc, 'Print_Mapping')
        if s_map: df_map = pd.DataFrame(s_map.get_all_records())
        else: df_map = pd.DataFrame(columns=['Code', 'Print_Name'])
    except: df_map = pd.DataFrame(columns=['Code', 'Print_Name'])
    
    data.append(df_map)
    return tuple(data)

def safe_float(val):
    try: return float(val)
    except: return 0.0

# --- 4. 재고 업데이트 ---
def update_inventory(factory, code, qty, p_name="-", p_spec="-", p_type="-", p_color="-", p_unit="-"):
    if not sheet_inventory: return
    try:
        time.sleep(1)
        cells = sheet_inventory.findall(str(code))
        target = None
        if cells:
            for c in cells:
                if c.col == 2: target = c; break
        if target:
            curr = safe_float(sheet_inventory.cell(target.row, 7).value)
            sheet_inventory.update_cell(target.row, 7, curr + qty)
        else:
            sheet_inventory.append_row([factory, code, p_name, p_spec, p_type, p_color, qty])
    except: pass

# --- 5. 헬퍼 함수 ---
def get_shape(code, df_items):
    shape = "-"
    if not df_items.empty:
        item_row = df_items[df_items['코드'].astype(str) == str(code)]
        if not item_row.empty:
            korean_type = str(item_row.iloc[0].get('타입', '-'))
            if "원통" in korean_type: shape = "CYLINDRIC"
            elif "큐빅" in korean_type: shape = "CUBICAL"
            elif "펠렛" in korean_type: shape = "PELLET"
            elif "파우더" in korean_type: shape = "POWDER"
            else: shape = korean_type
    return shape

def create_print_button(html_content, title="Print", orientation="portrait"):
    safe_content = html_content.replace('`', '\`').replace('$', '\$')
    page_css = "@page { size: A4 portrait; margin: 1cm; }"
    if orientation == "landscape": page_css = "@page { size: A4 landscape; margin: 1cm; }"
    js_code = f"""<script>
    function print_{title.replace(" ", "_")}() {{
        var win = window.open('', '', 'width=900,height=700');
        win.document.write('<html><head><title>{title}</title><style>{page_css} body {{ font-family: sans-serif; margin: 0; padding: 0; }} table {{ border-collapse: collapse; width: 100%; }} th, td {{ border: 1px solid black; padding: 4px; }} .page-break {{ page-break-after: always; width: 100vw; height: 100vh; display: flex; justify-content: center; align-items: center; }}</style></head><body>');
        win.document.write(`{safe_content}`);
        win.document.write('</body></html>');
        win.document.close();
        win.focus();
        setTimeout(function() {{ win.print(); }}, 500);
    }}
    </script>
    <button onclick="print_{title.replace(" ", "_")}()" style="background-color: #4CAF50; border: none; color: white; padding: 10px 20px; font-size: 14px; margin: 4px 2px; cursor: pointer; border-radius: 5px;">🖨️ {title} 인쇄하기</button>"""
    return js_code

def get_product_category(row):
    name = str(row['품목명']).upper()
    code = str(row['코드']).upper()
    gubun = str(row.get('구분', '')).strip()
    if 'CP' in name or 'COMPOUND' in name or 'CP' in code: return "Compound"
    if ('KA' in name or 'KA' in code) and (gubun == '반제품' or name.endswith('반') or '반' in name): return "KA반제품"
    if 'KA' in name or 'KA' in code: return "KA"
    if 'KG' in name or 'KG' in code: return "KG"
    if gubun == '반제품' or name.endswith('반'): return "반제품(기타)"
    return "기타"

# --- 6. 로그인 ---
if "authenticated" not in st.session_state: st.session_state["authenticated"] = False
if not st.session_state["authenticated"]:
    st.title("🔒 KPR ERP 시스템")
    c1, c2 = st.columns([1, 2])
    with c1:
        if st.button("로그인", type="primary"):
            if st.text_input("접속 암호", type="password") == "kpr1234":
                st.session_state["authenticated"] = True; st.rerun()
            else: st.error("암호가 틀렸습니다.")
    st.stop()

df_items, df_inventory, df_logs, df_bom, df_orders, df_wastewater, df_mapping = load_data()
if 'cart' not in st.session_state: st.session_state['cart'] = []

# --- 7. 사이드바 ---
with st.sidebar:
    if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
    else: st.header("🏭 KPR / Chamstek")
    if st.button("🔄 새로고침"): st.cache_data.clear(); st.rerun()
    st.markdown("---")
    menu = st.radio("메뉴", ["대시보드", "재고/생산 관리", "영업/출고 관리", "🏭 현장 작업 (LOT 입력)", "🔍 이력/LOT 검색", "🌊 환경/폐수 일지"])
    st.markdown("---")
    date = st.date_input("날짜", datetime.datetime.now())
    time_str = datetime.datetime.now().strftime("%H:%M:%S")
    factory = st.selectbox("공장", ["1공장", "2공장"])

# [0] 대시보드
if menu == "대시보드":
    st.title("📊 공장 현황 대시보드")
    if not df_logs.empty:
        yesterday_date = datetime.date.today() - datetime.timedelta(days=1)
        yesterday_str = yesterday_date.strftime("%Y-%m-%d")
        df_yesterday = df_logs[df_logs['날짜'] == yesterday_str]
        prod_data = df_yesterday[df_yesterday['구분']=='생산'].copy() if '구분' in df_yesterday.columns else pd.DataFrame()
        total_prod=0; ka_prod=0; kg_prod=0; ka_ban_prod=0; cp_prod=0
        if not prod_data.empty:
            prod_data['Category'] = prod_data.apply(get_product_category, axis=1)
            total_prod = prod_data['수량'].sum()
            ka_prod = prod_data[prod_data['Category']=='KA']['수량'].sum()
            kg_prod = prod_data[prod_data['Category']=='KG']['수량'].sum()
            ka_ban_prod = prod_data[prod_data['Category']=='KA반제품']['수량'].sum()
            cp_prod = prod_data[prod_data['Category']=='Compound']['수량'].sum()
        out_val = df_yesterday[df_yesterday['구분']=='출고']['수량'].sum() if '구분' in df_yesterday.columns else 0
        pend_cnt = len(df_orders[df_orders['상태']=='준비']['주문번호'].unique()) if not df_orders.empty and '상태' in df_orders.columns else 0
        st.subheader(f"📅 어제({yesterday_str}) 실적 요약")
        k1, k2, k3 = st.columns(3)
        k1.metric("어제 총 생산", f"{total_prod:,.0f} kg")
        k1.markdown(f"<div style='font-size:14px; color:gray;'>• KA: {ka_prod:,.0f} kg<br>• KG: {kg_prod:,.0f} kg<br>• KA반제품: {ka_ban_prod:,.0f} kg<br>• Compound: {cp_prod:,.0f} kg</div>", unsafe_allow_html=True)
        k2.metric("어제 총 출고", f"{out_val:,.0f} kg")
        k3.metric("출고 대기 주문", f"{pend_cnt} 건", delta="작업 필요", delta_color="inverse")
        st.markdown("---")
        if '구분' in df_logs.columns:
            st.subheader("📈 생산 추이 분석 (제품군별 비교)")
            c_filter1, c_filter2 = st.columns([2, 1])
            with c_filter1:
                week_ago = yesterday_date - datetime.timedelta(days=6)
                search_range = st.date_input("조회 기간 설정", [week_ago, yesterday_date])
            with c_filter2:
                filter_opt = st.selectbox("조회 품목 필터", ["전체", "KA", "KG", "KA반제품", "Compound"])
            df_prod_log = df_logs[df_logs['구분'] == '생산'].copy()
            if len(search_range) == 2:
                s_d, e_d = search_range
                all_dates = pd.date_range(start=s_d, end=e_d)
                categories = ["KA", "KG", "KA반제품", "Compound", "기타"]
                skeleton_data = []
                for d in all_dates:
                    d_str = d.strftime('%Y-%m-%d')
                    for c in categories: skeleton_data.append({'날짜': d_str, 'Category': c, '수량': 0})
                df_skeleton = pd.DataFrame(skeleton_data)
                if not df_prod_log.empty:
                    df_prod_log['날짜'] = pd.to_datetime(df_prod_log['날짜']).dt.strftime('%Y-%m-%d')
                    df_prod_log['Category'] = df_prod_log.apply(get_product_category, axis=1)
                    if filter_opt != "전체": df_prod_log = df_prod_log[df_prod_log['Category'] == filter_opt]
                    real_sum = df_prod_log.groupby(['날짜', 'Category'])['수량'].sum().reset_index()
                else: real_sum = pd.DataFrame(columns=['날짜', 'Category', '수량'])
                if filter_opt != "전체": df_skeleton = df_skeleton[df_skeleton['Category'] == filter_opt]
                final_df = pd.merge(df_skeleton, real_sum, on=['날짜', 'Category'], how='left', suffixes=('_base', '_real'))
                final_df['수량'] = final_df['수량_real'].fillna(0)
                final_df['날짜_dt'] = pd.to_datetime(final_df['날짜'])
                weekday_map = {0:'(월)', 1:'(화)', 2:'(수)', 3:'(목)', 4:'(금)', 5:'(토)', 6:'(일)'}
                final_df['요일'] = final_df['날짜_dt'].dt.dayofweek.map(weekday_map)
                final_df['표시날짜'] = final_df['날짜_dt'].dt.strftime('%m-%d') + " " + final_df['요일']
                domain = ["KA", "KG", "KA반제품", "Compound", "기타"]
                range_ = ["#1f77b4", "#ff7f0e", "#17becf", "#d62728", "#9467bd"] 
                chart = alt.Chart(final_df).mark_bar().encode(
                    x=alt.X('표시날짜', title='날짜 (요일)', axis=alt.Axis(labelAngle=0)),
                    y=alt.Y('수량', title='생산량 (KG)'),
                    color=alt.Color('Category', scale=alt.Scale(domain=domain, range=range_), title='제품군'),
                    xOffset='Category',
                    tooltip=['표시날짜', 'Category', alt.Tooltip('수량', format=',.0f')]
                ).properties(height=400)
                st.altair_chart(chart, use_container_width=True)
            else: st.info("기간을 선택해주세요.")
    else: st.info("데이터를 불러오는 중입니다...")

# [1] 재고/생산 관리
elif menu == "재고/생산 관리":
    with st.sidebar:
        st.markdown("### 📝 작업 입력")
        cat = st.selectbox("구분", ["입고", "생산", "재고실사"])
        sel_code=None; item_info=None; sys_q=0.0
        prod_line = "-"
        if cat == "생산":
            line_options = []
            if factory == "1공장": line_options = [f"압출{i}호" for i in range(1, 6)] + ["기타"]
            elif factory == "2공장": line_options = [f"압출{i}호" for i in range(1, 7)] + [f"컷팅{i}호" for i in range(1, 11)] + ["기타"]
            prod_line = st.selectbox("설비 라인", line_options)
        if not df_items.empty:
            df_f = df_items.copy()
            for c in ['규격', '타입', '색상', '품목명', '구분', 'Group']:
                if c in df_f.columns: df_f[c] = df_f[c].astype(str).str.strip()
            if cat=="입고": df_f = df_f[df_f['구분']=='원자재']
            elif cat=="생산": df_f = df_f[df_f['구분'].isin(['제품', '완제품', '반제품'])]
            def get_group(row):
                name = str(row['품목명']).upper(); grp = str(row['구분'])
                if grp == '반제품' or name.endswith('반'): return "반제품"
                if "CP" in name or "COMPOUND" in name: return "COMPOUND"
                if "KG" in name: return "KG"
                if "KA" in name: return "KA"
                return "기타"
            df_f['Group'] = df_f.apply(get_group, axis=1)
            if not df_f.empty:
                grp_list = sorted(list(set(df_f['Group'])))
                grp = st.selectbox("1.그룹", grp_list)
                df_step1 = df_f[df_f['Group']==grp]
                final = pd.DataFrame()
                if grp == "반제품":
                    p_list = sorted(list(set(df_step1['품목명'])))
                    p_name = st.selectbox("2.품목명", p_list)
                    final = df_step1[df_step1['품목명']==p_name]
                elif grp == "COMPOUND":
                    c_list = sorted(list(set(df_step1['색상'])))
                    clr = st.selectbox("2.색상", c_list)
                    final = df_step1[df_step1['색상']==clr]
                elif cat == "입고":
                    s_list = sorted(list(set(df_step1['규격'])))
                    spc = st.selectbox("2.규격", s_list) if len(s_list)>0 else None
                    final = df_step1[df_step1['규격']==spc] if spc else df_step1
                else:
                    s_list = sorted(list(set(df_step1['규격'])))
                    spc = st.selectbox("2.규격", s_list)
                    df_step2 = df_step1[df_step1['규격']==spc]
                    if not df_step2.empty:
                        c_list = sorted(list(set(df_step2['색상'])))
                        clr = st.selectbox("3.색상", c_list)
                        df_step3 = df_step2[df_step2['색상']==clr]
                        if not df_step3.empty:
                            t_list = sorted(list(set(df_step3['타입'])))
                            typ = st.selectbox("4.타입", t_list)
                            final = df_step3[df_step3['타입']==typ]
                if not final.empty:
                    item_info = final.iloc[0]; sel_code = item_info['코드']
                    st.success(f"선택: {sel_code}")
                    if cat=="재고실사" and not df_inventory.empty:
                        inv_rows = df_inventory[df_inventory['코드'].astype(str)==str(sel_code)]
                        sys_q = inv_rows['현재고'].apply(safe_float).sum()
                        st.info(f"전산 재고(통합): {sys_q}")
                else: item_info = None
        
        qty_in = st.number_input("수량") if cat != "재고실사" else 0.0
        note_in = st.text_input("비고")
        if cat == "재고실사":
            real = st.number_input("실사값(통합)", value=float(sys_q))
            qty_in = real - sys_q
            note_in = f"[실사] {note_in}"
            
        if st.button("저장"):
            if item_info is None: st.error("🚨 품목이 선택되지 않았습니다.")
            elif sheet_logs:
                try:
                    sheet_logs.append_row([date.strftime('%Y-%m-%d'), time_str, factory, cat, sel_code, item_info['품목명'], item_info['규격'], item_info['타입'], item_info['색상'], qty_in, note_in, "-", prod_line])
                    chg = qty_in if cat in ["입고","생산","재고실사"] else -qty_in
                    update_inventory(factory, sel_code, chg, item_info['품목명'], item_info['규격'], item_info['타입'], item_info['색상'], item_info.get('단위','-'))
                    if cat=="생산" and not df_bom.empty:
                        selected_type = item_info['타입']
                        if '타입' in df_bom.columns: bom_targets = df_bom[(df_bom['제품코드'].astype(str) == str(sel_code)) & (df_bom['타입'].astype(str) == str(selected_type))].drop_duplicates(subset=['자재코드'])
                        else: bom_targets = df_bom[df_bom['제품코드'].astype(str) == str(sel_code)].drop_duplicates(subset=['자재코드'])
                        for i,r in bom_targets.iterrows():
                            req = qty_in * safe_float(r['소요량'])
                            update_inventory(factory, r['자재코드'], -req)
                            time.sleep(0.5) 
                            sheet_logs.append_row([date.strftime('%Y-%m-%d'), time_str, factory, "사용(Auto)", r['자재코드'], "System", "-", "-", "-", -req, f"{sel_code} 생산", "-", prod_line])
                    st.cache_data.clear(); st.success("완료"); st.rerun()
                except Exception as e: st.error(f"오류: {e}")

    st.title(f"📦 재고/생산 관리 ({factory})")
    # 🔥 [수정] 탭 추가 (입고 이력)
    t1, t2, t3, t4, t5 = st.tabs(["🏭 생산 이력", "📥 원자재 입고 이력", "📦 재고 현황", "📜 전체 로그", "🔩 BOM"])
    
    # 🏭 1. 생산 이력
    with t1:
        st.subheader("🔍 생산 이력 관리 (조회 및 수정/삭제)")
        if df_logs.empty: st.info("로그 데이터가 없습니다.")
        else:
            df_prod_log = df_logs[df_logs['구분'] == '생산'].copy()
            df_prod_log['No'] = df_prod_log.index + 2 
            if len(df_prod_log.columns) >= 13:
                cols = list(df_prod_log.columns); cols[12] = '라인'; df_prod_log.columns = cols
            else: df_prod_log['라인'] = "-"
            for col in ['코드', '품목명', '라인', '타입']:
                if col in df_prod_log.columns: df_prod_log[col] = df_prod_log[col].astype(str)

            with st.expander("🔎 검색 필터", expanded=True):
                c_s1, c_s2, c_s3, c_s4 = st.columns(4)
                min_dt = pd.to_datetime(df_prod_log['날짜']).min().date() if not df_prod_log.empty else datetime.date.today()
                sch_date = c_s1.date_input("날짜 범위", [min_dt, datetime.date.today()])
                all_lines = ["전체"] + sorted(df_prod_log['라인'].unique().tolist())
                sch_line = c_s2.selectbox("라인 선택", all_lines)
                sch_code = c_s3.text_input("품목 코드/명 검색")
                sch_fac = c_s4.selectbox("공장 필터", ["전체", "1공장", "2공장"])

            df_res = df_prod_log.copy()
            if len(sch_date) == 2:
                s_d, e_d = sch_date
                df_res['날짜'] = pd.to_datetime(df_res['날짜'])
                df_res = df_res[(df_res['날짜'].dt.date >= s_d) & (df_res['날짜'].dt.date <= e_d)]
                df_res['날짜'] = df_res['날짜'].dt.strftime('%Y-%m-%d')
            if sch_line != "전체": df_res = df_res[df_res['라인'] == sch_line]
            if sch_code: df_res = df_res[df_res['코드'].str.contains(sch_code, case=False) | df_res['품목명'].str.contains(sch_code, case=False)]
            if sch_fac != "전체": df_res = df_res[df_res['공장'] == sch_fac]

            st.markdown("---")
            col_del1, col_del2 = st.columns([3, 1])
            with col_del1: st.write(f"📋 검색 결과: {len(df_res)}건")
            disp_cols = ['No', '날짜', '시간', '공장', '라인', '코드', '품목명', '타입', '수량', '비고']
            final_cols = [c for c in disp_cols if c in df_res.columns]
            st.dataframe(df_res[final_cols].sort_values(['날짜', '시간'], ascending=False), use_container_width=True, hide_index=True)
            
            st.markdown("### 🛠️ 기록 수정 및 삭제")
            df_for_select = df_res.sort_values(['날짜', '시간'], ascending=False)
            delete_options = {row['No']: f"No.{row['No']} | {row['날짜']} {row['품목명']} ({row['수량']}kg)" for _, row in df_for_select.iterrows()}
            sel_target_id = st.selectbox("관리할 기록 선택", list(delete_options.keys()), format_func=lambda x: delete_options[x])
            
            col_act1, col_act2 = st.columns(2)
            
            with col_act1:
                if st.button("🗑️ 선택한 기록 삭제 (자동 반제품 복구)", type="primary"):
                    target_row = df_prod_log[df_prod_log['No'] == sel_target_id].iloc[0]
                    del_date = target_row['날짜']; del_time = target_row['시간']; del_fac = target_row['공장']; del_code = target_row['코드']; del_qty = safe_float(target_row['수량'])
                    update_inventory(del_fac, del_code, -del_qty)
                    linked_logs = df_logs[(df_logs['날짜'] == del_date) & (df_logs['시간'] == del_time) & (df_logs['구분'] == '사용(Auto)') & (df_logs['비고'].str.contains(str(del_code), na=False))]
                    rows_to_delete = [sel_target_id]
                    if not linked_logs.empty:
                        for idx, row in linked_logs.iterrows():
                            mat_qty = safe_float(row['수량'])
                            update_inventory(del_fac, row['코드'], -mat_qty)
                            rows_to_delete.append(idx + 2)
                    rows_to_delete.sort(reverse=True)
                    try:
                        for r_idx in rows_to_delete:
                            sheet_logs.delete_rows(int(r_idx))
                            time.sleep(0.5)
                        st.success("삭제 및 복구 완료!"); time.sleep(1); st.cache_data.clear(); st.rerun()
                    except Exception as e: st.error(f"오류: {e}")

            with col_act2:
                if "edit_mode" not in st.session_state: st.session_state["edit_mode"] = False
                if st.button("✏️ 선택한 기록 수정하기"):
                    st.session_state["edit_mode"] = True
            
            if st.session_state["edit_mode"]:
                st.info("💡 수정하면 기존 기록은 삭제되고, 새로운 내용으로 다시 등록됩니다. (반제품 재고 자동 계산)")
                target_row_edit = df_prod_log[df_prod_log['No'] == sel_target_id].iloc[0]
                with st.form("edit_form"):
                    e_date = st.date_input("날짜", pd.to_datetime(target_row_edit['날짜']))
                    e_line = st.selectbox("라인", all_lines, index=all_lines.index(target_row_edit['라인']) if target_row_edit['라인'] in all_lines else 0)
                    e_qty = st.number_input("수량 (kg)", value=float(target_row_edit['수량']))
                    e_note = st.text_input("비고", value=target_row_edit['비고'])
                    
                    if st.form_submit_button("✅ 수정사항 저장"):
                        old_date = target_row_edit['날짜']; old_time = target_row_edit['시간']; old_fac = target_row_edit['공장']; old_code = target_row_edit['코드']; old_qty = safe_float(target_row_edit['수량'])
                        update_inventory(old_fac, old_code, -old_qty)
                        
                        linked_logs_old = df_logs[(df_logs['날짜'] == old_date) & (df_logs['시간'] == old_time) & (df_logs['구분'] == '사용(Auto)') & (df_logs['비고'].str.contains(str(old_code), na=False))]
                        rows_to_del_edit = [sel_target_id]
                        if not linked_logs_old.empty:
                            for idx, row in linked_logs_old.iterrows():
                                mat_qty = safe_float(row['수량'])
                                update_inventory(old_fac, row['코드'], -mat_qty)
                                rows_to_del_edit.append(idx + 2)
                        rows_to_del_edit.sort(reverse=True)
                        for r_idx in rows_to_del_edit:
                            sheet_logs.delete_rows(int(r_idx))
                            time.sleep(0.3)
                        
                        new_time_str = datetime.datetime.now().strftime("%H:%M:%S") 
                        sheet_logs.append_row([e_date.strftime('%Y-%m-%d'), new_time_str, old_fac, "생산", old_code, target_row_edit['품목명'], target_row_edit.get('규격',''), target_row_edit['타입'], target_row_edit.get('색상',''), e_qty, e_note, "-", e_line])
                        update_inventory(old_fac, old_code, e_qty)
                        
                        if not df_bom.empty:
                            sel_type = target_row_edit['타입']
                            if '타입' in df_bom.columns: bom_targets = df_bom[(df_bom['제품코드'].astype(str) == str(old_code)) & (df_bom['타입'].astype(str) == str(sel_type))].drop_duplicates(subset=['자재코드'])
                            else: bom_targets = df_bom[df_bom['제품코드'].astype(str) == str(old_code)].drop_duplicates(subset=['자재코드'])
                            for i,r in bom_targets.iterrows():
                                req = e_qty * safe_float(r['소요량'])
                                update_inventory(old_fac, r['자재코드'], -req)
                                time.sleep(0.3)
                                sheet_logs.append_row([e_date.strftime('%Y-%m-%d'), new_time_str, old_fac, "사용(Auto)", r['자재코드'], "System", "-", "-", "-", -req, f"{old_code} 생산", "-", e_line])
                        
                        st.session_state["edit_mode"] = False
                        st.success("수정 완료!"); time.sleep(1); st.cache_data.clear(); st.rerun()

    # 🔥 2. 입고 이력 (신규)
    with t2:
        st.subheader("📥 원자재 입고 이력 조회 및 취소")
        if df_logs.empty: st.info("데이터가 없습니다.")
        else:
            # 입고 데이터만 필터링
            df_receipt_log = df_logs[df_logs['구분'] == '입고'].copy()
            df_receipt_log['No'] = df_receipt_log.index + 2
            
            with st.expander("🔎 입고 내역 검색", expanded=True):
                c_r1, c_r2 = st.columns(2)
                min_dt_r = pd.to_datetime(df_receipt_log['날짜']).min().date() if not df_receipt_log.empty else datetime.date.today()
                sch_date_r = c_r1.date_input("날짜 범위", [min_dt_r, datetime.date.today()], key="r_date")
                sch_txt_r = c_r2.text_input("품목 검색", key="r_txt")
                
            df_res_r = df_receipt_log.copy()
            if len(sch_date_r) == 2:
                s_d, e_d = sch_date_r
                df_res_r['날짜'] = pd.to_datetime(df_res_r['날짜'])
                df_res_r = df_res_r[(df_res_r['날짜'].dt.date >= s_d) & (df_res_r['날짜'].dt.date <= e_d)]
                df_res_r['날짜'] = df_res_r['날짜'].dt.strftime('%Y-%m-%d')
            if sch_txt_r:
                df_res_r = df_res_r[df_res_r['코드'].str.contains(sch_txt_r, case=False) | df_res_r['품목명'].str.contains(sch_txt_r, case=False)]
            
            # 리스트 표시
            disp_cols_r = ['No', '날짜', '시간', '공장', '코드', '품목명', '규격', '수량', '비고']
            final_cols_r = [c for c in disp_cols_r if c in df_res_r.columns]
            st.dataframe(df_res_r[final_cols_r].sort_values(['날짜', '시간'], ascending=False), use_container_width=True, hide_index=True)
            
            st.markdown("### 🗑️ 잘못된 입고 기록 삭제")
            st.caption("삭제하면 해당 수량만큼 재고가 줄어듭니다 (입고 취소).")
            
            df_for_select_r = df_res_r.sort_values(['날짜', '시간'], ascending=False)
            del_opts_r = {row['No']: f"No.{row['No']} | {row['날짜']} {row['품목명']} ({row['수량']}kg)" for _, row in df_for_select_r.iterrows()}
            
            if del_opts_r:
                sel_del_id_r = st.selectbox("삭제할 기록 선택", list(del_opts_r.keys()), format_func=lambda x: del_opts_r[x], key="sel_del_r")
                
                if st.button("❌ 입고 기록 삭제 (재고 차감)", type="primary", key="btn_del_r"):
                    target_row_r = df_receipt_log[df_receipt_log['No'] == sel_del_id_r].iloc[0]
                    
                    # 재고 차감 (입고 취소니까 -수량)
                    r_fac = target_row_r['공장']
                    r_code = target_row_r['코드']
                    r_qty = safe_float(target_row_r['수량'])
                    
                    update_inventory(r_fac, r_code, -r_qty)
                    
                    # 로그 삭제
                    try:
                        sheet_logs.delete_rows(int(sel_del_id_r))
                        st.success("삭제 완료! 재고가 차감되었습니다.")
                        time.sleep(1)
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"오류: {e}")
            else:
                st.info("삭제할 대상이 없습니다.")

    # 📦 3. 재고 현황
    with t3:
        if not df_inventory.empty:
            df_v = df_inventory.copy()
            if not df_items.empty:
                cmap = df_items.drop_duplicates('코드').set_index('코드')['구분'].to_dict()
                df_v['구분'] = df_v['코드'].map(cmap).fillna('-')
            c1, c2 = st.columns(2)
            fac_f = c1.radio("공장 (위치 확인용)", ["전체", "1공장", "2공장"], horizontal=True)
            cat_f = c2.radio("품목", ["전체", "제품", "반제품", "원자재"], horizontal=True)
            if fac_f != "전체": df_v = df_v[df_v['공장']==fac_f]
            if cat_f != "전체": 
                if cat_f=="제품": df_v = df_v[df_v['구분'].isin(['제품','완제품'])]
                else: df_v = df_v[df_v['구분']==cat_f]
            st.dataframe(df_v, use_container_width=True)

    with t4: st.dataframe(df_logs, use_container_width=True)
    with t5: st.dataframe(df_bom, use_container_width=True)

# [2] 영업/출고 관리
elif menu == "영업/출고 관리":
    # ... (기존과 동일)
    st.title("📑 영업 주문 및 출고 관리")
    if sheet_orders is None: st.error("'Orders' 시트가 없습니다."); st.stop()
    
    tab_o, tab_p, tab_prt, tab_out, tab_cancel = st.tabs(["📝 1. 주문 등록", "✏️ 2. 팔레트 수정/삭제", "🖨️ 3. 명세서/라벨 인쇄", "🚚 4. 출고 확정", "↩️ 5. 출고 취소(복구)"])
    
    with tab_o:
        c1, c2 = st.columns([1, 2])
        with c1:
            st.subheader("주문 입력")
            od_dt = st.date_input("주문일", datetime.datetime.now())
            cl_nm = st.text_input("거래처명 (CUSTOMER)", placeholder="예: SHANGHAI YILIU")
            if not df_items.empty:
                df_sale = df_items[df_items['구분'].isin(['제품','완제품'])].copy()
                df_sale['Disp'] = df_sale['코드'].astype(str) + " (" + df_sale['규격'].astype(str) + "/" + df_sale['색상'].astype(str) + "/" + df_sale['타입'].astype(str) + ")"
                sel_it = st.selectbox("품목 선택", df_sale['Disp'].unique())
                row_it = df_sale[df_sale['Disp']==sel_it].iloc[0]
                ord_q = st.number_input("주문량(kg)", step=100.0)
                ord_rem = st.text_input("📦 포장 단위 (REMARK)", value="BOX", help="명세서 REM란에 표시될 내용 (예: BOX, BAG)")
                if st.button("🛒 담기"):
                    st.session_state['cart'].append({
                        "코드": row_it['코드'], "품목명": row_it['품목명'], "규격": row_it['규격'],
                        "색상": row_it['색상'], "타입": row_it['타입'], "수량": ord_q, "비고": ord_rem
                    })
        with c2:
            st.subheader("장바구니")
            if st.session_state['cart']:
                st.dataframe(pd.DataFrame(st.session_state['cart']), use_container_width=True)
                if st.button("✅ 주문 확정"):
                    oid = "ORD-" + datetime.datetime.now().strftime("%y%m%d%H%M")
                    rows = []
                    plt = 1; cw = 0
                    for it in st.session_state['cart']:
                        rem = it['수량']
                        while rem > 0:
                            sp = 1000 - cw
                            if sp <= 0: plt += 1; cw = 0; sp = 1000
                            load = min(rem, sp)
                            rows.append([oid, od_dt.strftime('%Y-%m-%d'), cl_nm, it['코드'], it['품목명'], load, plt, "준비", it['비고'], ""])
                            cw += load; rem -= load
                    try:
                        time.sleep(1)
                        for r in rows: sheet_orders.append_row(r)
                        st.session_state['cart'] = []; st.cache_data.clear(); st.success("저장 완료"); st.rerun()
                    except Exception as e: st.error(f"저장 실패: {e}")

    with tab_p:
        st.subheader("✏️ 팔레트 구성 상세 수정 및 행 추가")
        st.info("💡 여기서는 자동 배당되지 않습니다. 입력한 수량과 팔레트 번호 그대로 저장됩니다.")
        if not df_orders.empty and '상태' in df_orders.columns:
            pend = df_orders[df_orders['상태']=='준비']
            if not pend.empty:
                unique_ords = pend[['주문번호', '날짜', '거래처']].drop_duplicates().set_index('주문번호')
                order_dict = unique_ords.to_dict('index')
                def format_ord(ord_id):
                    info = order_dict.get(ord_id)
                    return f"{info['날짜']} | {info['거래처']} ({ord_id})" if info else ord_id

                tgt = st.selectbox("수정할 주문 선택", pend['주문번호'].unique(), format_func=format_ord)
                
                original_df = pend[pend['주문번호']==tgt].copy()
                original_df['팔레트번호'] = pd.to_numeric(original_df['팔레트번호'], errors='coerce').fillna(999)
                original_df = original_df.sort_values('팔레트번호')
                
                if not df_items.empty:
                    code_to_type = df_items.set_index('코드')['타입'].to_dict()
                    if '타입' in original_df.columns:
                        original_df['타입'] = original_df.apply(lambda x: x['타입'] if pd.notna(x['타입']) and str(x['타입']).strip() != '' else code_to_type.get(x['코드'], '-'), axis=1)
                    else:
                        original_df['타입'] = original_df['코드'].map(code_to_type).fillna('-')
                else: 
                    if '타입' not in original_df.columns: original_df['타입'] = "-"
                
                original_df['Real_Index'] = range(len(original_df))
                
                display_df = original_df.sort_values('팔레트번호')

                st.write("▼ 현재 팔레트 구성 (보기 전용)")
                display_cols = ['팔레트번호', '코드', '품목명', '타입', '수량', '비고']
                st.dataframe(display_df[display_cols], use_container_width=True, hide_index=True)
                
                st.markdown("---")
                c_mod1, c_mod2 = st.columns(2)
                
                with c_mod1:
                    st.markdown("#### ➕ 품목(행) 추가 (수동)")
                    with st.form(key="add_item_form"):
                        all_item_codes = df_items['코드'].tolist() if not df_items.empty else []
                        new_code = st.selectbox("추가할 제품 코드", all_item_codes)
                        selected_item_info = df_items[df_items['코드'] == new_code].iloc[0] if not df_items.empty and new_code in all_item_codes else None
                        def_type = selected_item_info['타입'] if selected_item_info is not None else "-"
                        def_name = selected_item_info['품목명'] if selected_item_info is not None else "-"
                        c_a1, c_a2 = st.columns(2)
                        new_qty = c_a1.number_input("수량(kg)", min_value=0.0, step=10.0)
                        default_plt = int(original_df['팔레트번호'].max()) if not original_df.empty else 1
                        new_plt = c_a2.number_input("팔레트 번호", min_value=1, step=1, value=default_plt)
                        new_type = st.text_input("타입 (수정 가능)", value=def_type)
                        new_note = st.text_input("비고 (Remark)", value="BOX")
                        
                        if st.form_submit_button("추가하기"):
                            base_info = original_df.iloc[0] 
                            headers = sheet_orders.row_values(1)
                            if '타입' not in headers:
                                sheet_orders.update_cell(1, len(headers) + 1, '타입')
                                headers.append('타입')
                                time.sleep(0.5)
                            new_row = [tgt, base_info['날짜'], base_info['거래처'], new_code, def_name, new_qty, new_plt, "준비", new_note, ""]
                            type_idx = headers.index('타입')
                            while len(new_row) <= type_idx: new_row.append("")
                            new_row[type_idx] = new_type
                            sheet_orders.append_row(new_row)
                            st.success("추가되었습니다!"); st.cache_data.clear(); time.sleep(1); st.rerun()

                with c_mod2:
                    st.markdown("#### 🛠️ 개별 라인 수정/삭제")
                    edit_opts = {r['Real_Index']: f"PLT {r['팔레트번호']} | {r['코드']} ({r['수량']}kg)" for i, r in display_df.iterrows()}
                    sel_real_idx = st.selectbox("수정할 라인 선택", list(edit_opts.keys()), format_func=lambda x: edit_opts[x])
                    target_row = original_df[original_df['Real_Index'] == sel_real_idx].iloc[0]
                    
                    with st.form(key="edit_line_form"):
                        c_e1, c_e2 = st.columns(2)
                        ed_qty = c_e1.number_input("수량", value=float(target_row['수량']))
                        ed_plt = c_e2.number_input("팔레트", value=int(target_row['팔레트번호']))
                        ed_type = st.text_input("타입 (수정 가능)", value=str(target_row['타입']))
                        ed_note = st.text_input("비고", value=str(target_row['비고']))
                        
                        c_btn1, c_btn2 = st.columns(2)
                        with c_btn1:
                            if st.form_submit_button("💾 수정 저장"):
                                all_vals = sheet_orders.get_all_records()
                                headers = sheet_orders.row_values(1)
                                if '타입' not in headers: headers.append('타입'); [r.update({'타입': ""}) for r in all_vals if '타입' not in r]
                                updated_data = []
                                row_counter = 0
                                for r in all_vals:
                                    if '타입' not in r: r['타입'] = ""
                                    if str(r['주문번호']) == str(tgt):
                                        if row_counter == sel_real_idx: # 절대 위치 비교
                                            r['수량'] = ed_qty; r['팔레트번호'] = ed_plt; r['비고'] = ed_note; r['타입'] = ed_type
                                        row_counter += 1
                                    updated_data.append([r.get(h, "") for h in headers])
                                sheet_orders.clear(); sheet_orders.update([headers] + updated_data)
                                st.success("수정 완료!"); st.cache_data.clear(); time.sleep(1); st.rerun()
                                
                        with c_btn2:
                            if st.form_submit_button("🗑️ 삭제"):
                                all_vals = sheet_orders.get_all_records(); headers = sheet_orders.row_values(1)
                                new_data = []; row_counter = 0
                                for r in all_vals:
                                    if str(r['주문번호']) == str(tgt):
                                        if row_counter != sel_real_idx: new_data.append([r.get(h, "") for h in headers])
                                        row_counter += 1
                                    else: new_data.append([r.get(h, "") for h in headers])
                                sheet_orders.clear(); sheet_orders.update([headers] + new_data)
                                st.success("삭제 완료!"); st.cache_data.clear(); time.sleep(1); st.rerun()

            else: st.info("대기 중인 주문이 없습니다.")

    with tab_prt:
        # ... (이전과 동일)
        st.subheader("🖨️ Packing List & Labels")
        if not df_orders.empty and '상태' in df_orders.columns:
            pend = df_orders[df_orders['상태']=='준비']
            if not pend.empty:
                unique_ords_prt = pend[['주문번호', '날짜', '거래처']].drop_duplicates().set_index('주문번호')
                order_dict_prt = unique_ords_prt.to_dict('index')
                def format_ord_prt(ord_id):
                    info = order_dict_prt.get(ord_id)
                    return f"{info['날짜']} | {info['거래처']} ({ord_id})" if info else ord_id

                tgt_p = st.selectbox("출력할 주문", pend['주문번호'].unique(), key='prt_sel', format_func=format_ord_prt)
                dp = pend[pend['주문번호']==tgt_p].copy()
                
                dp['팔레트번호'] = pd.to_numeric(dp['팔레트번호'], errors='coerce').fillna(999)
                dp = dp.sort_values('팔레트번호')
                
                # 🔥 [수정] 출력 시에도 수정된 타입 반영
                if not df_items.empty:
                    code_to_type = df_items.set_index('코드')['타입'].to_dict()
                    if '타입' in dp.columns:
                        dp['타입'] = dp.apply(lambda x: x['타입'] if pd.notna(x['타입']) and str(x['타입']).strip() != '' else code_to_type.get(x['코드'], '-'), axis=1)
                    else:
                        dp['타입'] = dp['코드'].map(code_to_type).fillna('-')
                else:
                    if '타입' not in dp.columns: dp['타입'] = "-"

                if not dp.empty:
                    cli = dp.iloc[0]['거래처']
                    ex_date = dp.iloc[0]['날짜']
                    ship_date = datetime.datetime.now().strftime("%Y-%m-%d")
                    
                    st.markdown("#### ✏️ 출력용 제품명 변경 (선택)")
                    st.caption("아래 표에서 '고객용 제품명'을 바꾸고 [영구 저장]을 누르면, 다음번에도 기억합니다.")
                    
                    unique_codes = sorted(dp['코드'].unique())
                    saved_map = {}
                    if not df_mapping.empty:
                        saved_map = dict(zip(df_mapping['Code'].astype(str), df_mapping['Print_Name'].astype(str)))
                    
                    current_map_data = []
                    for c in unique_codes:
                        c_str = str(c)
                        print_name = saved_map.get(c_str, c_str)
                        current_map_data.append({"Internal": c_str, "Customer_Print_Name": print_name})
                    
                    edited_map = st.data_editor(
                        pd.DataFrame(current_map_data),
                        use_container_width=True,
                        column_config={
                            "Internal": st.column_config.TextColumn("시스템 제품명 (수정불가)", disabled=True),
                            "Customer_Print_Name": st.column_config.TextColumn("📝 고객용 제품명 (수정가능)")
                        },
                        hide_index=True
                    )
                    code_map = dict(zip(edited_map['Internal'], edited_map['Customer_Print_Name']))

                    if st.button("💾 변경된 이름 영구 저장 (시스템 반영)"):
                        try:
                            try: ws = doc.worksheet("Print_Mapping")
                            except: 
                                ws = doc.add_worksheet("Print_Mapping", 1000, 2)
                                ws.append_row(["Code", "Print_Name"])
                            
                            db_map = {}
                            if not df_mapping.empty:
                                db_map = dict(zip(df_mapping['Code'].astype(str), df_mapping['Print_Name'].astype(str)))
                            db_map.update(code_map)
                            
                            rows_to_save = [["Code", "Print_Name"]]
                            for k, v in db_map.items(): rows_to_save.append([k, v])
                            
                            ws.clear(); ws.update(rows_to_save)
                            st.success("저장되었습니다!"); st.cache_data.clear(); time.sleep(1); st.rerun()
                        except Exception as e: st.error(f"저장 실패: {e}")

                    excel_data = []
                    for plt_num, group in dp.groupby('팔레트번호'):
                        for _, r in group.iterrows():
                            # SHAPE 값 결정 (저장된 타입이 있으면 그것을 shape로 사용, 아니면 자동변환)
                            # 보통 SHAPE는 타입(Cubic/Cylindric)을 의미함
                            final_shape = str(r['타입'])
                            if "원통" in final_shape: final_shape = "CYLINDRIC"
                            elif "큐빅" in final_shape: final_shape = "CUBICAL"
                            elif "펠렛" in final_shape: final_shape = "PELLET"
                            elif "파우더" in final_shape: final_shape = "POWDER"
                            
                            excel_data.append({
                                'PLT': plt_num,
                                'ITEM NAME': code_map.get(str(r['코드']), str(r['코드'])),
                                "Q'TY": r['수량'],
                                'COLOR': df_items[df_items['코드'].astype(str)==str(r['코드'])].iloc[0]['색상'] if not df_items.empty else "-",
                                'SHAPE': final_shape,
                                'LOT#': r.get('LOT번호', ''),
                                'REMARK': r['비고']
                            })
                    df_excel = pd.DataFrame(excel_data)
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df_excel.to_excel(writer, index=False, sheet_name='Packing List')
                    excel_data_bin = output.getvalue()

                    sub_t1, sub_t2, sub_t3 = st.tabs(["📄 명세서 (Packing List)", "🔷 다이아몬드 라벨", "📑 표준 라벨 (혼적지원)"])
                    
                    with sub_t1:
                        c_btn1, c_btn2 = st.columns([1, 1])
                        with c_btn1:
                            st.download_button("📥 엑셀 파일로 다운로드", data=excel_data_bin, file_name=f"PackingList_{cli}_{datetime.date.today()}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                        
                        pl_rows = ""; tot_q = 0; tot_plt = dp['팔레트번호'].nunique()
                        for plt_num, group in dp.groupby('팔레트번호'):
                            g_len = len(group); is_first = True
                            for _, r in group.iterrows():
                                final_shape = str(r['타입'])
                                if "원통" in final_shape: final_shape = "CYLINDRIC"
                                elif "큐빅" in final_shape: final_shape = "CUBICAL"
                                
                                rem = r['비고']
                                lot_no = r.get('LOT번호', '')
                                clr = "-"
                                if not df_items.empty:
                                    inf = df_items[df_items['코드'].astype(str)==str(r['코드'])]
                                    if not inf.empty: clr = inf.iloc[0]['색상']
                                display_name = code_map.get(str(r['코드']), str(r['코드']))
                                pl_rows += "<tr>"
                                if is_first: pl_rows += f"<td rowspan='{g_len}'>{plt_num}</td>"
                                pl_rows += f"<td>{display_name}</td><td align='right'>{r['수량']:,.0f}</td><td align='center'>{clr}</td><td align='center'>{final_shape}</td><td align='center'>{lot_no}</td><td align='center'>{rem}</td></tr>"
                                is_first = False; tot_q += r['수량']
                        
                        html_pl_raw = f"""
                        <div style="padding:20px; font-family: 'Arial', sans-serif; font-size:12px;">
                            <h2 style="text-align:center;">PACKING LIST</h2>
                            <table style="width:100%; margin-bottom:10px;">
                                <tr><td><b>EX-FACTORY</b></td><td>: {ex_date}</td></tr>
                                <tr><td><b>SHIP DATE</b></td><td>: {ship_date}</td></tr>
                                <tr><td><b>CUSTOMER(BUYER)</b></td><td>: {cli}</td></tr>
                            </table>
                            <table style="width:100%; border-collapse: collapse; text-align:center; table-layout: fixed;" border="1">
                                <colgroup>
                                    <col style="width: 5%;">
                                    <col style="width: 22%;">
                                    <col style="width: 8%;">
                                    <col style="width: 10%;">
                                    <col style="width: 10%;">
                                    <col style="width: 25%;">
                                    <col style="width: 20%;">
                                </colgroup>
                                <thead style="background-color:#eee;">
                                    <tr>
                                        <th>PLT</th>
                                        <th>ITEM NAME</th>
                                        <th>Q'TY</th>
                                        <th>COLOR</th>
                                        <th>SHAPE</th>
                                        <th>LOT#</th>
                                        <th>REMARK</th>
                                    </tr>
                                </thead>
                                <tbody>{pl_rows}</tbody>
                                <tfoot>
                                    <tr style="font-weight:bold; background-color:#eee;">
                                        <td colspan="2">{tot_plt} PLTS</td>
                                        <td align='right'>{tot_q:,.0f}</td>
                                        <td colspan="4"></td>
                                    </tr>
                                </tfoot>
                            </table>
                        </div>
                        """
                        st.components.v1.html(html_pl_raw, height=400, scrolling=True)
                        btn_html = create_print_button(html_pl_raw, "Packing List", "landscape")
                        st.components.v1.html(btn_html, height=50)

                    with sub_t2:
                        labels_html_diamond = ""
                        for plt_num, group in dp.groupby('팔레트번호'):
                            p_sum = group['수량'].sum()
                            svg_content = f"""
                            <div class="page-break">
                                <svg viewBox="0 0 800 600" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg">
                                    <polygon points="400,20 780,300 400,580 20,300" fill="none" stroke="#003366" stroke-width="15"/>
                                    <foreignObject x="100" y="120" width="600" height="120">
                                        <div xmlns="http://www.w3.org/1999/xhtml" style="font-family: Arial, sans-serif; font-size: 35px; font-weight: bold; text-align: center; word-wrap: break-word; display: flex; justify-content: center; align-items: center; height: 100%;">
                                            {cli}
                                        </div>
                                    </foreignObject>
                                    <text x="400" y="290" text-anchor="middle" font-family="Arial, sans-serif" font-size="80" font-weight="900" fill="black">KPR</text>
                                    <text x="400" y="365" text-anchor="middle" font-family="Arial, sans-serif" font-size="40" font-weight="bold">{plt_num}/{tot_plt}</text>
                                    <text x="400" y="425" text-anchor="middle" font-family="Arial, sans-serif" font-size="30" font-weight="bold">MADE IN KOREA</text>
                                </svg>
                            </div>
                            """
                            labels_html_diamond += svg_content
                        st.caption("▼ 미리보기")
                        preview_dia = labels_html_diamond.replace('width="100%" height="100%"', 'width="100%" height="300px"')
                        st.components.v1.html(preview_dia, height=400, scrolling=True)
                        btn_lbl_d = create_print_button(labels_html_diamond, "Diamond Labels", "landscape")
                        st.components.v1.html(btn_lbl_d, height=50)

                    with sub_t3:
                        labels_html_text = ""
                        for plt_num, group in dp.groupby('팔레트번호'):
                            p_qty = group['수량'].sum()
                            pallet_summary = group.groupby('코드')['수량'].sum().reset_index()
                            
                            row_count = len(pallet_summary)
                            if row_count <= 2: font_size = "60px"
                            elif row_count <= 4: font_size = "50px"
                            else: font_size = "35px"
                            
                            product_lines_html = ""
                            for _, row in pallet_summary.iterrows():
                                code = row['코드']
                                qty = row['수량']
                                disp_name = code_map.get(str(code), str(code))
                                product_lines_html += f"<div style='margin: 10px 0; display:flex; justify-content:center; gap:40px;'><span>{disp_name}</span><span>{qty:,.0f} KG</span></div>"

                            label_div = f"""
                            <div class="page-break" style="border: none; width: 100%; height: 95vh; display: flex; flex-direction: column; justify-content: space-evenly; align-items: center; text-align: center; font-family: 'Arial', sans-serif; font-weight: bold; box-sizing: border-box; padding: 20px;">
                                <div style="font-size: 60px; text-transform: uppercase;">{cli}</div>
                                <div style="font-size: {font_size}; width:100%;">
                                    {product_lines_html}
                                </div>
                                <div style="font-size: 50px; margin-top: 30px;">
                                    <div>&lt;PLASTIC ABRASIVE MEDIA&gt;</div>
                                    <div style="margin-top: 20px;">PLT # : {plt_num} / {tot_plt}</div>
                                    <div style="margin-top: 20px;">TOTAL : {p_qty:,.0f} KG</div>
                                </div>
                            </div>
                            """
                            labels_html_text += label_div
                        
                        st.components.v1.html(labels_html_text, height=400, scrolling=True)
                        btn_lbl_t = create_print_button(labels_html_text, "Standard Labels", "landscape")
                        st.components.v1.html(btn_lbl_t, height=50)

    with tab_out:
        # ... (이전과 동일)
        st.subheader("🚚 출고 확정 및 재고 차감")
        st.warning("주의: '출고 확정'을 누르면 즉시 재고가 차감되며 되돌릴 수 없습니다.")
        if not df_orders.empty and '상태' in df_orders.columns:
            pend = df_orders[df_orders['상태']=='준비']
            if not pend.empty:
                unique_ords_out = pend[['주문번호', '날짜', '거래처']].drop_duplicates().set_index('주문번호')
                order_dict_out = unique_ords_out.to_dict('index')
                def format_ord_out(ord_id):
                    info = order_dict_out.get(ord_id)
                    return f"{info['날짜']} | {info['거래처']} ({ord_id})" if info else ord_id
                tgt_out = st.selectbox("출고할 주문 선택", pend['주문번호'].unique(), format_func=format_ord_out, key="out_sel")
                d_out = pend[pend['주문번호']==tgt_out].copy()
                if not df_items.empty:
                    code_to_type = df_items.set_index('코드')['타입'].to_dict()
                    d_out['타입'] = d_out['코드'].map(code_to_type).fillna('-')
                else: d_out['타입'] = "-"
                
                cols_to_show = ['코드','품목명','타입','수량','팔레트번호']
                if 'LOT번호' in d_out.columns: cols_to_show.append('LOT번호')
                st.write("▼ 출고 내역 확인")
                st.dataframe(d_out[cols_to_show], use_container_width=True)
                
                total_w = d_out['수량'].sum()
                
                c_out1, c_out2 = st.columns([1, 2])
                with c_out1:
                    real_out_date = st.date_input("실제 출고일", datetime.datetime.now())
                with c_out2:
                    st.metric("총 출고 중량", f"{total_w:,.0f} kg")
                
                if st.button("🚀 출고 확정 (재고 차감)", type="primary"):
                    with st.spinner("출고 처리 중..."):
                        try:
                            for idx, row in d_out.iterrows():
                                update_inventory(factory, row['코드'], -safe_float(row['수량']))
                                itm_info = df_items[df_items['코드'].astype(str)==str(row['코드'])]
                                p_nm="-"; p_sp="-"; p_ty="-"; p_co="-"
                                if not itm_info.empty:
                                    p_nm = itm_info.iloc[0]['품목명']; p_sp = itm_info.iloc[0]['규격']; p_ty = itm_info.iloc[0]['타입']; p_co = itm_info.iloc[0]['색상']
                                
                                sheet_logs.append_row([
                                    real_out_date.strftime('%Y-%m-%d'), 
                                    time_str, 
                                    factory, 
                                    "출고", 
                                    row['코드'], 
                                    p_nm, p_sp, p_ty, p_co, 
                                    -safe_float(row['수량']), 
                                    f"주문출고({tgt_out})", 
                                    cli, 
                                    "-"
                                ])
                                time.sleep(0.5)
                            time.sleep(1)
                            all_records = sheet_orders.get_all_records()
                            for r in all_records:
                                if str(r['주문번호']) == str(tgt_out): r['상태'] = '완료'
                            headers = list(all_records[0].keys()) if all_records else ['주문번호', '날짜', '거래처', '코드', '품목명', '수량', '팔레트번호', '상태', '비고', 'LOT번호']
                            update_values = [headers]
                            for r in all_records: update_values.append([r.get(h, "") for h in headers])
                            sheet_orders.clear(); time.sleep(1); sheet_orders.update(update_values)
                            st.cache_data.clear(); st.success(f"출고 완료! 재고가 차감되었습니다. (주문번호: {tgt_out})"); time.sleep(3); st.rerun()
                        except Exception as e: st.error(f"처리 중 오류 발생: {e}")
            else: st.info("출고 대기 중인 주문이 없습니다.")

    with tab_cancel:
        # ... (이전과 동일)
        st.subheader("↩️ 출고 취소 (재고 복구)")
        st.warning("⚠️ 이미 출고 확정된 주문을 취소하고 재고를 되돌립니다.")
        
        if not df_orders.empty and '상태' in df_orders.columns:
            completed = df_orders[df_orders['상태']=='완료']
            if not completed.empty:
                unique_comp_ords = completed[['주문번호', '날짜', '거래처']].drop_duplicates().sort_values('날짜', ascending=False)
                def format_comp_ord(ord_id):
                    row = unique_comp_ords[unique_comp_ords['주문번호'] == ord_id].iloc[0]
                    return f"{row['날짜']} | {row['거래처']} ({ord_id})"

                target_cancel_id = st.selectbox("취소할 출고 건 선택", unique_comp_ords['주문번호'].unique(), format_func=format_comp_ord)
                cancel_details = completed[completed['주문번호'] == target_cancel_id]
                st.write("▼ 취소 대상 품목 (재고가 다시 늘어납니다)")
                st.dataframe(cancel_details[['코드', '품목명', '수량', '팔레트번호']], use_container_width=True)
                
                if st.button("🚫 출고 취소 및 재고 복구", type="primary"):
                    with st.spinner("취소 처리 중..."):
                        try:
                            for idx, row in cancel_details.iterrows():
                                restore_qty = safe_float(row['수량'])
                                update_inventory(factory, row['코드'], restore_qty)
                                sheet_logs.append_row([
                                    date.strftime('%Y-%m-%d'), 
                                    time_str, 
                                    factory, 
                                    "출고취소", 
                                    row['코드'], 
                                    row['품목명'], 
                                    "-", "-", "-", 
                                    restore_qty, 
                                    f"주문복구({target_cancel_id})", 
                                    "-", "-"
                                ])
                                time.sleep(0.5)

                            time.sleep(1)
                            all_records = sheet_orders.get_all_records()
                            for r in all_records:
                                if str(r['주문번호']) == str(target_cancel_id): r['상태'] = '준비'
                            
                            headers = list(all_records[0].keys()) if all_records else ['주문번호', '날짜', '거래처', '코드', '품목명', '수량', '팔레트번호', '상태', '비고', 'LOT번호']
                            update_values = [headers]
                            for r in all_records: update_values.append([r.get(h, "") for h in headers])
                            sheet_orders.clear(); time.sleep(1); sheet_orders.update(update_values)
                            st.cache_data.clear(); st.success(f"취소 완료! 주문 상태가 '준비'로 변경되었으며, 재고가 복구되었습니다."); time.sleep(3); st.rerun()
                        except Exception as e: st.error(f"취소 중 오류 발생: {e}")
            else: st.info("취소할 수 있는 출고 완료 건이 없습니다.")
        else: st.info("데이터가 없습니다.")

# [3] 현장 작업 (LOT 입력)
elif menu == "🏭 현장 작업 (LOT 입력)":
    # ... (이전과 동일)
    st.title("🏭 현장 작업: LOT 번호 입력")
    st.caption("작업자는 할당된 팔레트 구성에 맞춰 LOT번호만 입력해주세요.")
    if sheet_orders is None: st.error("'Orders' 시트가 없습니다."); st.stop()
    if not df_orders.empty and '상태' in df_orders.columns:
        pend = df_orders[df_orders['상태']=='준비']
        if not pend.empty:
            unique_ords = pend[['주문번호', '날짜', '거래처']].drop_duplicates().set_index('주문번호')
            order_dict = unique_ords.to_dict('index')
            def format_ord(ord_id):
                info = order_dict.get(ord_id)
                return f"{info['날짜']} | {info['거래처']} ({ord_id})" if info else ord_id
            tgt = st.selectbox("작업할 주문 선택", pend['주문번호'].unique(), format_func=format_ord, key="wrk_sel")
            original_df = pend[pend['주문번호']==tgt].copy()
            if not df_items.empty:
                code_to_type = df_items.set_index('코드')['타입'].to_dict()
                original_df['타입'] = original_df['코드'].map(code_to_type).fillna('-')
            else: original_df['타입'] = "-"
            if 'LOT번호' not in original_df.columns: original_df['LOT번호'] = ""
            editor_cols = ['팔레트번호', '코드', '품목명', '타입', '수량', 'LOT번호', '비고']
            edited_df = st.data_editor(original_df[editor_cols], num_rows="fixed", key="worker_editor", use_container_width=True, disabled=["팔레트번호", "코드", "품목명", "타입", "수량", "비고"])
            if st.button("💾 LOT 정보 저장", type="primary"):
                with st.spinner("저장 중..."):
                    try:
                        time.sleep(1)
                        all_records = sheet_orders.get_all_records()
                        remaining_data = [r for r in all_records if str(r['주문번호']) != str(tgt)]
                        base_info = original_df.iloc[0]
                        new_rows = []
                        for _, row in edited_df.iterrows():
                            new_rows.append({
                                '주문번호': tgt, '날짜': base_info['날짜'], '거래처': base_info['거래처'], '코드': row['코드'], '품목명': row['품목명'], '수량': row['수량'], '팔레트번호': row['팔레트번호'], '상태': '준비', '비고': row['비고'], 'LOT번호': row.get('LOT번호', '')
                            })
                        final_data = remaining_data + new_rows
                        time.sleep(1)
                        headers = list(all_records[0].keys()) if all_records else ['주문번호', '날짜', '거래처', '코드', '품목명', '수량', '팔레트번호', '상태', '비고', 'LOT번호']
                        if 'LOT번호' not in headers: headers.append('LOT번호')
                        update_values = [headers]
                        for r in final_data: update_values.append([r.get(h, "") for h in headers])
                        sheet_orders.clear(); time.sleep(1); sheet_orders.update(update_values)
                        st.cache_data.clear(); st.success("작업 저장 완료!"); time.sleep(2); st.rerun()
                    except Exception as e: st.error(f"오류: {e}")
        else: st.info("작업 대기 중인 주문이 없습니다.")

# [4] 이력/LOT 검색
elif menu == "🔍 이력/LOT 검색":
    # ... (이전과 동일)
    st.title("🔍 출고 이력 및 LOT 번호 검색")
    if df_orders.empty: st.info("데이터가 없습니다.")
    else:
        df_search = df_orders.copy()
        if 'LOT번호' not in df_search.columns: df_search['LOT번호'] = ""
        for col in ['코드', '거래처', 'LOT번호']:
            if col in df_search.columns: df_search[col] = df_search[col].astype(str)
        view_type = st.radio("조회 대상", ["출고 완료된 건만 보기", "전체 보기 (진행중 포함)"], horizontal=True)
        if view_type == "출고 완료된 건만 보기":
            if '상태' in df_search.columns: df_search = df_search[df_search['상태'] == '완료']
        with st.expander("🔎 검색 필터 열기", expanded=True):
            c1, c2, c3, c4 = st.columns(4)
            search_lot = c1.text_input("LOT 번호 (일부 입력 가능)")
            all_clients = ["전체"] + sorted(df_search['거래처'].unique().tolist())
            sel_client = c2.selectbox("거래처", all_clients)
            all_items = ["전체"] + sorted(df_search['코드'].unique().tolist())
            sel_item = c3.selectbox("품목 코드", all_items)
            min_date = pd.to_datetime(df_search['날짜']).min().date() if not df_search.empty else datetime.date.today()
            date_range = c4.date_input("조회 기간", [min_date, datetime.date.today()])
        if search_lot: df_search = df_search[df_search['LOT번호'].str.contains(search_lot, case=False, na=False)]
        if sel_client != "전체": df_search = df_search[df_search['거래처'] == sel_client]
        if sel_item != "전체": df_search = df_search[df_search['코드'] == sel_item]
        if len(date_range) == 2:
            s_date, e_date = date_range
            df_search['날짜'] = pd.to_datetime(df_search['날짜'])
            df_search = df_search[(df_search['날짜'].dt.date >= s_date) & (df_search['날짜'].dt.date <= e_date)]
            df_search['날짜'] = df_search['날짜'].dt.strftime('%Y-%m-%d')
        st.markdown(f"### 📋 조회 결과: 총 {len(df_search)}건")
        cols = ['날짜', '거래처', '코드', '품목명', '수량', 'LOT번호', '상태', '비고']
        valid_cols = [c for c in cols if c in df_search.columns]
        st.dataframe(df_search[valid_cols].sort_values('날짜', ascending=False), use_container_width=True)
        
        if not df_search.empty:
            html_table = f"<h2>출고 이력 조회 결과</h2><p>조회일: {datetime.date.today()}</p>"
            html_table += "<table style='width:100%; border-collapse: collapse; text-align: center; font-size: 12px; table-layout: fixed;' border='1'>"
            html_table += "<colgroup>"
            html_table += "<col style='width: 10%;'>" # 날짜
            html_table += "<col style='width: 15%;'>" # 거래처
            html_table += "<col style='width: 10%;'>" # 코드
            html_table += "<col style='width: 15%;'>" # 품목명
            html_table += "<col style='width: 8%;'>"  # 수량
            html_table += "<col style='width: 25%;'>" # LOT번호
            html_table += "<col style='width: 7%;'>"  # 상태
            html_table += "<col style='width: 10%;'>" # 비고
            html_table += "</colgroup>"

            html_table += "<thead><tr style='background-color: #f2f2f2;'>"
            for c in valid_cols: html_table += f"<th>{c}</th>"
            html_table += "</tr></thead><tbody>"
            for _, row in df_search[valid_cols].iterrows():
                html_table += "<tr>"
                for c in valid_cols:
                    val = row[c]
                    if c == '수량': val = f"{val:,.0f}"
                    html_table += f"<td>{val}</td>"
                html_table += "</tr>"
            html_table += "</tbody></table>"
            
            st.components.v1.html(create_print_button(html_table, "Shipment History Search Result", orientation="landscape"), height=50)

# 🔥 [신규] 환경/폐수 일지 메뉴
elif menu == "🌊 환경/폐수 일지":
    st.title("🌊 폐수배출시설 운영일지 (자동화)")
    
    if sheet_wastewater is None:
        st.error("⚠️ 'Wastewater' 시트가 없습니다. 구글 시트에 탭을 추가해주세요.")
        st.stop()
    
    # 탭 구성
    tab_w1, tab_w2 = st.tabs(["📅 월간 일지 생성", "📋 조회 및 다운로드"])
    
    # --- 탭 1: 생성 ---
    with tab_w1:
        st.markdown("### 📅 월간 운영일지 자동 생성")
        st.info("💡 1공장에서 생산이 있었던 날짜를 기준으로 일지를 자동 생성합니다.")
        
        c_gen1, c_gen2, c_gen3 = st.columns(3)
        current_year = datetime.date.today().year
        current_month = datetime.date.today().month
        
        sel_year = c_gen1.number_input("연도", 2024, 2030, current_year)
        sel_month = c_gen2.number_input("월", 1, 12, current_month)
        use_random = c_gen3.checkbox("랜덤 변주 적용 (±1%)", value=False, help="체크하면 수치를 조금씩 다르게 생성합니다.")
        
        if st.button("🚀 일지 데이터 생성 (미리보기)"):
            if df_logs.empty:
                st.warning("생산 로그 데이터가 없습니다.")
            else:
                start_date = datetime.date(sel_year, sel_month, 1)
                if sel_month == 12: end_date = datetime.date(sel_year + 1, 1, 1) - datetime.timedelta(days=1)
                else: end_date = datetime.date(sel_year, sel_month + 1, 1) - datetime.timedelta(days=1)
                
                date_list = pd.date_range(start=start_date, end=end_date)
                generated_rows = []
                
                for d in date_list:
                    check_date = d.date()
                    d_str = d.strftime('%Y-%m-%d')
                    
                    # 🔥 휴일 체크 삭제 -> 무조건 생산량 체크
                    # if is_holiday(check_date): continue
                    
                    daily_prod = df_logs[(df_logs['날짜'] == d_str) & (df_logs['공장'] == '1공장') & (df_logs['구분'] == '생산')]
                    
                    if not daily_prod.empty:
                        # 🔥 1공장 생산량 합계 계산
                        total_prod_qty = daily_prod['수량'].sum()
                        
                        # 🔥 원료 사용량 로직 (생산량의 80%)
                        base_resin = round(total_prod_qty * 0.8) # 합성수지 (80%)
                        base_plastic = 0 # 플라스틱 재생칩 (0)
                        base_pigment = 0.2 # 안료 (기본값)
                        base_water = 2.16
                        
                        # 🔥 가동 시간 로직 (토요일 체크)
                        # weekday(): 0=월, 5=토, 6=일
                        if check_date.weekday() == 5: # 토요일
                            base_time_str = "08:00~15:00"
                        else:
                            base_time_str = "08:00~08:00" # 24시간 가동
                        
                        if use_random:
                            # 합성수지만 랜덤 변주 (시간은 고정)
                            base_resin = round(base_resin * random.uniform(0.99, 1.01))
                            base_pigment = round(0.2 * random.uniform(0.95, 1.05), 2)
                        
                        weekday_kor = ["월", "화", "수", "목", "금", "토", "일"][check_date.weekday()]
                        full_date_str = f"{d.strftime('%Y년 %m월 %d일')} {weekday_kor}요일"
                        
                        row = {
                            "날짜": full_date_str,
                            "대표자": "문성인",
                            "환경기술인": "문주혁",
                            "가동시간": base_time_str,
                            "플라스틱재생칩": base_plastic,
                            "합성수지": base_resin,
                            "안료": base_pigment,
                            "용수사용량": base_water,
                            "폐수발생량": 0,
                            "위탁량": "",
                            "기타": "전량 재이용"
                        }
                        generated_rows.append(row)
                
                if generated_rows:
                    st.success(f"총 {len(generated_rows)}건의 데이터를 생성했습니다.")
                    df_preview = pd.DataFrame(generated_rows)
                    st.session_state['wastewater_preview'] = df_preview
                else:
                    st.warning("해당 월에 1공장 생산 기록이 없습니다.")
                    
        if 'wastewater_preview' in st.session_state and not st.session_state['wastewater_preview'].empty:
            st.write("▼ 생성된 데이터 미리보기 (수정 가능)")
            edited_log = st.data_editor(st.session_state['wastewater_preview'], num_rows="dynamic", use_container_width=True)
            
            if st.button("💾 구글 시트에 저장"):
                try:
                    new_values = []
                    for idx, row in edited_log.iterrows():
                        new_values.append([
                            str(row['날짜']), str(row['대표자']), str(row['환경기술인']), str(row['가동시간']),
                            str(row['플라스틱재생칩']), str(row['합성수지']), str(row['안료']),
                            str(row['용수사용량']), str(row['폐수발생량']), str(row['위탁량']), str(row['기타'])
                        ])
                    for row_val in new_values:
                        sheet_wastewater.append_row(row_val)
                        time.sleep(0.1)
                    st.success("저장 완료!"); time.sleep(1); st.cache_data.clear(); st.rerun()
                except Exception as e: st.error(f"저장 실패: {e}")

    # --- 탭 2: 조회 ---
    with tab_w2:
        st.markdown("### 📋 저장된 일지 조회")
        if not df_wastewater.empty:
            st.dataframe(df_wastewater, use_container_width=True)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_wastewater.to_excel(writer, index=False, sheet_name='운영일지')
            excel_data = output.getvalue()
            st.download_button(label="📥 엑셀 파일 다운로드", data=excel_data, file_name=f"Wastewater_Log_{datetime.date.today()}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        else:
            st.info("저장된 데이터가 없습니다.")
