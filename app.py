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

# --- 3. 데이터 로딩 ---
@st.cache_data(ttl=60)
def load_data():
    data = []
    sheets = [sheet_items, sheet_inventory, sheet_logs, sheet_bom, sheet_orders]
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

df_items, df_inventory, df_logs, df_bom, df_orders, df_mapping = load_data()
if 'cart' not in st.session_state: st.session_state['cart'] = []

# --- 7. 사이드바 ---
with st.sidebar:
    if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
    else: st.header("🏭 KPR / Chamstek")
    if st.button("🔄 새로고침"): st.cache_data.clear(); st.rerun()
    st.markdown("---")
    menu = st.radio("메뉴", ["대시보드", "재고/생산 관리", "영업/출고 관리", "🏭 현장 작업 (LOT 입력)", "🔍 이력/LOT 검색"])
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
    t1, t2, t3, t4 = st.tabs(["🏭 생산 이력 (조회/수정/삭제)", "📦 재고 현황", "📜 전체 로그", "🔩 BOM"])
    
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
            
            # 1. 삭제 버튼
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

            # 2. 수정 버튼 및 폼
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
                        # 1. 기존 기록 삭제 (Rollback)
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
                        
                        # 2. 새로운 기록 추가 (Re-Insert)
                        new_time_str = datetime.datetime.now().strftime("%H:%M:%S") # 수정 시각으로 갱신
                        sheet_logs.append_row([e_date.strftime('%Y-%m-%d'), new_time_str, old_fac, "생산", old_code, target_row_edit['품목명'], target_row_edit.get('규격',''), target_row_edit['타입'], target_row_edit.get('색상',''), e_qty, e_note, "-", e_line])
                        update_inventory(old_fac, old_code, e_qty)
                        
                        # 3. 새로운 BOM 차감
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

    with t2:
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

    with t3: st.dataframe(df_logs, use_container_width=True)
    with t4: st.dataframe(df_bom, use_container_width=True)

# [2] 영업/출고 관리
elif menu == "영업/출고 관리":
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
                
                # 🔥 [수정] 원본 데이터 인덱스 보존 로직 추가 (수정 오류 원인 해결)
                # 1. 전체 데이터를 먼저 가져와서 인덱스를 보존함
                original_df = pend[pend['주문번호']==tgt].copy()
                
                # 2. 타입 로직 적용
                if not df_items.empty:
                    code_to_type = df_items.set_index('코드')['타입'].to_dict()
                    if '타입' in original_df.columns:
                        original_df['타입'] = original_df.apply(lambda x: x['타입'] if pd.notna(x['타입']) and str(x['타입']).strip() != '' else code_to_type.get(x['코드'], '-'), axis=1)
                    else:
                        original_df['타입'] = original_df['코드'].map(code_to_type).fillna('-')
                else: 
                    if '타입' not in original_df.columns: original_df
