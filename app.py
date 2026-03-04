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

def get_sheet(doc, name, create_headers=None):
    if doc is None: return None
    try:
        return doc.worksheet(name)
    except:
        if create_headers:
            try:
                ws = doc.add_worksheet(title=name, rows="1000", cols="20")
                ws.append_row(create_headers)
                return ws
            except: return None
        return None

sheet_items = get_sheet(doc, 'Items')
sheet_inventory = get_sheet(doc, 'Inventory')
sheet_logs = get_sheet(doc, 'Logs')
sheet_bom = get_sheet(doc, 'BOM')
sheet_orders = get_sheet(doc, 'Orders')

ww_headers = ['날짜', '대표자', '환경기술인', '가동시간', '플라스틱재생칩', '합성수지', '안료', '용수사용량', '폐수발생량', '위탁량', '기타']
sheet_wastewater = get_sheet(doc, 'Wastewater', ww_headers)

mtg_headers = ['ID', '작성일', '공장', '안건내용', '담당자', '상태', '비고']
sheet_meetings = get_sheet(doc, 'Meetings', mtg_headers)

# --- 3. 데이터 로딩 ---
@st.cache_data(ttl=60)
def load_data():
    data = []
    sheets = [sheet_items, sheet_inventory, sheet_logs, sheet_bom, sheet_orders, sheet_wastewater, sheet_meetings]
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

df_items, df_inventory, df_logs, df_bom, df_orders, df_wastewater, df_meetings, df_mapping = load_data()
if 'cart' not in st.session_state: st.session_state['cart'] = []

# --- 7. 사이드바 ---
with st.sidebar:
    if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
    else: st.header("🏭 KPR / Chamstek")
    if st.button("🔄 새로고침"): st.cache_data.clear(); st.rerun()
    st.markdown("---")
    menu = st.radio("메뉴", ["대시보드", "재고/생산 관리", "영업/출고 관리", "🏭 현장 작업 (LOT 입력)", "🔍 이력/LOT 검색", "🌊 환경/폐수 일지", "📋 주간 회의 & 개선사항"])
    st.markdown("---")
    date = st.date_input("날짜", datetime.datetime.now())
    time_str = datetime.datetime.now().strftime("%H:%M:%S")
    factory = st.selectbox("공장", ["1공장", "2공장"])

# [0] 대시보드
if menu == "대시보드":
    st.title("📊 공장 현황 대시보드")
    if not df_logs.empty:
        today = datetime.date.today()
        target_date_str = (today - datetime.timedelta(days=1)).strftime("%Y-%m-%d") 
        display_label = "어제"

        if '구분' in df_logs.columns and '날짜' in df_logs.columns:
            prod_dates = df_logs[df_logs['구분'] == '생산']['날짜'].unique()
            if len(prod_dates) > 0:
                prod_dates = sorted(prod_dates, reverse=True)
                for d_str in prod_dates:
                    try:
                        d_date = pd.to_datetime(d_str).date()
                        if d_date < today:
                            target_date_str = d_str
                            if d_date == today - datetime.timedelta(days=1): display_label = "어제"
                            else: display_label = "최근 작업일"
                            break
                    except: continue

        df_target_day = df_logs[df_logs['날짜'] == target_date_str]
        prod_data = df_target_day[df_target_day['구분']=='생산'].copy() if '구분' in df_target_day.columns else pd.DataFrame()
        
        total_prod=0; ka_prod=0; kg_prod=0; ka_ban_prod=0; cp_prod=0
        if not prod_data.empty:
            prod_data['Category'] = prod_data.apply(get_product_category, axis=1)
            total_prod = prod_data['수량'].sum()
            ka_prod = prod_data[prod_data['Category']=='KA']['수량'].sum()
            kg_prod = prod_data[prod_data['Category']=='KG']['수량'].sum()
            ka_ban_prod = prod_data[prod_data['Category']=='KA반제품']['수량'].sum()
            cp_prod = prod_data[prod_data['Category']=='Compound']['수량'].sum()

        out_val = df_target_day[df_target_day['구분']=='출고']['수량'].sum() if '구분' in df_target_day.columns else 0
        pend_cnt = len(df_orders[df_orders['상태']=='준비']['주문번호'].unique()) if not df_orders.empty and '상태' in df_orders.columns else 0
        
        st.subheader(f"📅 {display_label}({target_date_str}) 실적 요약")
        k1, k2, k3 = st.columns(3)
        k1.metric(f"{display_label} 총 생산", f"{total_prod:,.0f} kg")
        k1.markdown(f"<div style='font-size:14px; color:gray;'>• KA: {ka_prod:,.0f} kg<br>• KG: {kg_prod:,.0f} kg<br>• KA반제품: {ka_ban_prod:,.0f} kg<br>• Compound: {cp_prod:,.0f} kg</div>", unsafe_allow_html=True)
        k2.metric(f"{display_label} 총 출고", f"{out_val:,.0f} kg")
        k3.metric("출고 대기 주문", f"{pend_cnt} 건", delta="작업 필요", delta_color="inverse")
        st.markdown("---")
        
        if '구분' in df_logs.columns:
            st.subheader("📈 생산 추이 분석 (제품군별 비교)")
            c_filter1, c_filter2 = st.columns([2, 1])
            with c_filter1:
                target_dt_obj = pd.to_datetime(target_date_str).date()
                week_ago = target_dt_obj - datetime.timedelta(days=6)
                search_range = st.date_input("조회 기간 설정", [week_ago, target_dt_obj])
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
                ).properties(height=350)
                st.altair_chart(chart, use_container_width=True)

                # 🔥 [수정 및 강화] 최근 10일치 원재료 입고 리포트
                st.markdown("---")
                st.subheader("📥 최근 10일 원재료 입고 리포트")
                
                df_inbound_all = df_logs[df_logs['구분'] == '입고'].copy()
                if not df_inbound_all.empty:
                    # 1. 실제 입고가 있었던 날짜들 중 최근 10일 추출
                    in_dates = sorted(df_inbound_all['날짜'].unique(), reverse=True)[:10]
                    df_in_10days = df_inbound_all[df_inbound_all['날짜'].isin(in_dates)].copy()
                    
                    if not df_in_10days.empty:
                        # 차트 (날짜별/품목별 합산)
                        in_chart = alt.Chart(df_in_10days).mark_bar().encode(
                            x=alt.X('날짜:N', title='입고일', sort=alt.SortField('날짜', order='descending')),
                            y=alt.Y('sum(수량):Q', title='입고량 (KG)'),
                            color=alt.Color('품목명:N', title='품목명', scale=alt.Scale(scheme='category20')),
                            tooltip=['날짜', '품목명', alt.Tooltip('sum(수량)', format=',.0f', title='총 입고량')]
                        ).properties(height=300)
                        st.altair_chart(in_chart, use_container_width=True)
                        
                        # 상세 데이터 테이블
                        st.markdown("##### 📋 상세 입고 내역 (최근 10일)")
                        df_in_table = df_in_10days[['날짜', '시간', '코드', '품목명', '규격', '수량', '비고']].sort_values(['날짜', '시간'], ascending=False)
                        st.dataframe(df_in_table, use_container_width=True, hide_index=True)
                    else:
                        st.info("표시할 입고 내역이 없습니다.")
                else:
                    st.info("입고 데이터가 존재하지 않습니다.")

            else: st.info("기간을 선택해주세요.")
    else: st.info("데이터를 불러오는 중입니다...")

# [1] 재고/생산 관리
elif menu == "재고/생산 관리":
    # (v2.7/3.2 기존 코드 유지)
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
    t1, t2, t3, t4, t5 = st.tabs(["🏭 생산 이력", "📥 원자재 입고 이력", "📦 재고 현황", "📜 전체 로그", "🔩 BOM"])
    
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
                sch_date = c_s1.date_input("날짜 범위", [min_dt, datetime.date.today()], key="p_date")
                all_lines = ["전체"] + sorted(df_prod_log['라인'].unique().tolist())
                sch_line = c_s2.selectbox("라인 선택", all_lines)
                sch_code = c_s3.text_input("품목 코드/명 검색", key="p_txt")
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
            if delete_options:
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

    with t2:
        st.subheader("📥 원자재 입고 이력 조회 및 취소")
        if df_logs.empty: st.info("데이터가 없습니다.")
        else:
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
            
            disp_cols_r = ['No', '날짜', '시간', '공장', '코드', '품목명', '규격', '수량', '비고']
            st.dataframe(df_res_r[disp_cols_r].sort_values(['날짜', '시간'], ascending=False), use_container_width=True, hide_index=True)
            
            st.markdown("### 🗑️ 잘못된 입고 기록 삭제")
            del_opts_r = {row['No']: f"No.{row['No']} | {row['날짜']} {row['품목명']} ({row['수량']}kg)" for _, row in df_res_r.iterrows()}
            if del_opts_r:
                sel_del_id_r = st.selectbox("삭제할 기록 선택", list(del_opts_r.keys()), format_func=lambda x: del_opts_r[x], key="sel_del_r")
                if st.button("❌ 입고 기록 삭제 (재고 차감)", type="primary"):
                    target_row_r = df_receipt_log[df_receipt_log['No'] == sel_del_id_r].iloc[0]
                    update_inventory(target_row_r['공장'], target_row_r['코드'], -safe_float(target_row_r['수량']))
                    sheet_logs.delete_rows(int(sel_del_id_r))
                    st.success("삭제 완료!"); time.sleep(1); st.cache_data.clear(); st.rerun()

    with t3:
        if not df_inventory.empty:
            df_v = df_inventory.copy()
            if not df_items.empty: cmap = df_items.drop_duplicates('코드').set_index('코드')['구분'].to_dict(); df_v['구분'] = df_v['코드'].map(cmap).fillna('-')
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
    st.title("📑 영업 주문 및 출고 관리")
    if sheet_orders is None: st.error("'Orders' 시트가 없습니다."); st.stop()
    
    tab_o, tab_p, tab_prt, tab_out, tab_cancel = st.tabs(["📝 1. 주문 등록", "✏️ 2. 팔레트 수정/삭제/재구성", "🖨️ 3. 명세서/라벨 인쇄", "🚚 4. 출고 확정", "↩️ 5. 출고 취소(복구)"])
    
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
                ord_rem = st.text_input("📦 포장 단위 (REMARK)", value="BOX")
                if st.button("🛒 장바구니 담기"):
                    st.session_state['cart'].append({
                        "코드": row_it['코드'], "품목명": row_it['품목명'], "규격": row_it['규격'],
                        "색상": row_it['색상'], "타입": row_it['타입'], "수량": ord_q, "비고": ord_rem
                    }); st.rerun()
        with c2:
            st.subheader("🛒 장바구니 목록")
            if st.session_state['cart']:
                for i, it in enumerate(st.session_state['cart']):
                    ci1, ci2, ci3 = st.columns([4, 2, 1])
                    ci1.write(f"**{it['코드']}** ({it['품목명']})")
                    ci2.write(f"{it['수량']:,}kg / {it['비고']}")
                    if ci3.button("❌", key=f"cart_del_{i}"):
                        st.session_state['cart'].pop(i); st.rerun()
                
                st.markdown("---")
                max_pallet_kg = st.number_input("📦 팔레트당 최대 적재량 설정 (kg)", min_value=100.0, value=1000.0, step=100.0)
                
                col_btn1, col_btn2 = st.columns(2)
                if col_btn1.button("🗑️ 장바구니 전체 비우기"):
                    st.session_state['cart'] = []; st.rerun()
                if col_btn2.button("✅ 최종 주문 확정", type="primary"):
                    oid = "ORD-" + datetime.datetime.now().strftime("%y%m%d%H%M")
                    rows = []
                    plt = 1; cw = 0
                    for it in st.session_state['cart']:
                        rem = it['수량']
                        while rem > 0:
                            sp = max_pallet_kg - cw
                            if sp <= 0: plt += 1; cw = 0; sp = max_pallet_kg
                            load = min(rem, sp)
                            rows.append([oid, od_dt.strftime('%Y-%m-%d'), cl_nm, it['코드'], it['품목명'], load, plt, "준비", it['비고'], "", it['타입']])
                            cw += load; rem -= load
                    for r in rows: sheet_orders.append_row(r)
                    st.session_state['cart'] = []; st.cache_data.clear(); st.success("주문 저장 완료!"); st.rerun()

    with tab_p:
        st.subheader("✏️ 팔레트 수정 및 일괄 재구성")
        st.info("💡 여기서는 자동 배당되지 않습니다. 입력한 수량과 팔레트 번호 그대로 저장됩니다.")
        if not df_orders.empty and '상태' in df_orders.columns:
            pend = df_orders[df_orders['상태']=='준비']
            if not pend.empty:
                unique_ords = pend[['주문번호', '날짜', '거래처']].drop_duplicates().set_index('주문번호')
                order_dict = unique_ords.to_dict('index')
                tgt = st.selectbox("수정할 주문 선택", pend['주문번호'].unique(), format_func=lambda x: f"{order_dict[x]['날짜']} | {order_dict[x]['거래처']} ({x})")
                
                original_df = pend[pend['주문번호']==tgt].copy()
                original_df['Real_Index'] = range(len(original_df))
                original_df['팔레트번호'] = pd.to_numeric(original_df['팔레트번호'], errors='coerce').fillna(999)
                display_df = original_df.sort_values('팔레트번호')
                
                st.write("▼ 현재 팔레트 구성")
                st.dataframe(display_df[['팔레트번호', '코드', '품목명', '수량', '비고']], use_container_width=True, hide_index=True)
                
                with st.expander("📦 팔레트 적재량 기준으로 일괄 재구성 (Re-Split)", expanded=False):
                    st.warning("⚠️ 실행 시 기존의 팔레트 번호와 수량이 입력하신 기준에 맞춰 자동으로 다시 계산됩니다.")
                    new_max_kg = st.number_input("새로운 팔레트당 적재량 (kg)", min_value=100.0, value=1200.0, step=100.0, key="resplit_kg")
                    if st.button("🚀 재구성 실행"):
                        with st.spinner("팔레트 재계산 중..."):
                            combined = original_df.groupby(['코드', '품목명', '비고', '타입'])['수량'].sum().reset_index()
                            new_rows_data = []
                            plt_cnt = 1; current_w = 0
                            for _, r in combined.iterrows():
                                rem = r['수량']
                                while rem > 0:
                                    space = new_max_kg - current_w
                                    if space <= 0: plt_cnt += 1; current_w = 0; space = new_max_kg
                                    load = min(rem, space)
                                    new_rows_data.append([tgt, original_df.iloc[0]['날짜'], original_df.iloc[0]['거래처'], r['코드'], r['품목명'], load, plt_cnt, "준비", r['비고'], "", r['타입']])
                                    current_w += load; rem -= load
                            all_records = sheet_orders.get_all_records()
                            headers = sheet_orders.row_values(1)
                            filtered_records = [r for r in all_records if str(r['주문번호']) != str(tgt)]
                            new_final_values = [headers] + [[r.get(h, "") for h in headers] for r in filtered_records] + new_rows_data
                            sheet_orders.clear(); sheet_orders.update(new_final_values)
                            st.success("팔레트 재구성이 완료되었습니다!"); st.cache_data.clear(); time.sleep(1); st.rerun()

                st.markdown("---")
                c_mod1, c_mod2 = st.columns(2)
                with c_mod1:
                    st.markdown("#### ➕ 품목 추가")
                    with st.form("add_form"):
                        new_code = st.selectbox("제품 코드", df_items['코드'].unique())
                        new_qty = st.number_input("수량(kg)", min_value=0.0, step=10.0)
                        new_plt = st.number_input("팔레트 번호", value=int(display_df['팔레트번호'].max()))
                        if st.form_submit_button("추가"):
                            row = [tgt, original_df.iloc[0]['날짜'], original_df.iloc[0]['거래처'], new_code, "", new_qty, new_plt, "준비", "BOX", "", ""]
                            sheet_orders.append_row(row); st.success("추가됨"); st.cache_data.clear(); st.rerun()

                with c_mod2:
                    st.markdown("#### 🛠️ 개별 수정/삭제")
                    edit_opts = {r['Real_Index']: f"PLT {r['팔레트번호']} | {r['코드']} ({r['수량']}kg)" for _, r in display_df.iterrows()}
                    sel_idx = st.selectbox("수정할 라인", list(edit_opts.keys()), format_func=lambda x: edit_opts[x])
                    target = original_df[original_df['Real_Index'] == sel_idx].iloc[0]
                    with st.form("edit_form"):
                        ed_qty = st.number_input("수량", value=float(target['수량']))
                        ed_plt = st.number_input("팔레트", value=int(target['팔레트번호']))
                        if st.form_submit_button("💾 저장"):
                            all_vals = sheet_orders.get_all_records()
                            headers = sheet_orders.row_values(1)
                            updated = []
                            row_count = 0
                            for r in all_vals:
                                if str(r['주문번호']) == str(tgt):
                                    if row_count == sel_idx: r['수량'] = ed_qty; r['팔레트번호'] = ed_plt
                                    row_count += 1
                                updated.append([r.get(h, "") for h in headers])
                            sheet_orders.clear(); sheet_orders.update([headers] + updated)
                            st.success("수정됨"); st.cache_data.clear(); st.rerun()

    with tab_prt:
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
                                    <col style="width: 5%;"><col style="width: 22%;"><col style="width: 8%;">
                                    <col style="width: 10%;"><col style="width: 10%;"><col style="width: 25%;"><col style="width: 20%;">
                                </colgroup>
                                <thead style="background-color:#eee;">
                                    <tr><th>PLT</th><th>ITEM NAME</th><th>Q'TY</th><th>COLOR</th><th>SHAPE</th><th>LOT#</th><th>REMARK</th></tr>
                                </thead>
                                <tbody>{pl_rows}</tbody>
                                <tfoot>
                                    <tr style="font-weight:bold; background-color:#eee;">
                                        <td colspan="2">{tot_plt} PLTS</td><td align='right'>{tot_q:,.0f}</td><td colspan="4"></td>
                                    </tr>
                                </tfoot>
                            </table>
                        </div>
                        """
                        st.components.v1.html(html_pl_raw, height=400, scrolling=True)
                        st.components.v1.html(create_print_button(html_pl_raw, "Packing List", "landscape"), height=50)

                    with sub_t2:
                        labels_html_diamond = ""
                        for plt_num, group in dp.groupby('팔레트번호'):
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
                        st.components.v1.html(create_print_button(labels_html_diamond, "Diamond Labels", "landscape"), height=50)

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
                                disp_name = code_map.get(str(row['코드']), str(row['코드']))
                                product_lines_html += f"<div style='margin: 10px 0; display:flex; justify-content:center; gap:40px;'><span>{disp_name}</span><span>{row['수량']:,.0f} KG</span></div>"
                            label_div = f"""
                            <div class="page-break" style="border: none; width: 100%; height: 95vh; display: flex; flex-direction: column; justify-content: space-evenly; align-items: center; text-align: center; font-family: 'Arial', sans-serif; font-weight: bold; box-sizing: border-box; padding: 20px;">
                                <div style="font-size: 60px; text-transform: uppercase;">{cli}</div>
                                <div style="font-size: {font_size}; width:100%;">{product_lines_html}</div>
                                <div style="font-size: 50px; margin-top: 30px;">
                                    <div>&lt;PLASTIC ABRASIVE MEDIA&gt;</div>
                                    <div style="margin-top: 20px;">PLT # : {plt_num} / {tot_plt}</div>
                                    <div style="margin-top: 20px;">TOTAL : {p_qty:,.0f} KG</div>
                                </div>
                            </div>
                            """
                            labels_html_text += label_div
                        st.components.v1.html(labels_html_text, height=400, scrolling=True)
                        st.components.v1.html(create_print_button(labels_html_text, "Standard Labels", "landscape"), height=50)

    with tab_out:
        st.subheader("🚚 출고 확정 및 재고 차감")
        if not df_orders.empty:
            pend = df_orders[df_orders['상태']=='준비']
            if not pend.empty:
                unique_ords_out = pend[['주문번호', '날짜', '거래처']].drop_duplicates().set_index('주문번호')
                tgt_out = st.selectbox("출고할 주문 선택", pend['주문번호'].unique(), format_func=lambda x: f"{unique_ords_out.loc[x]['날짜']} | {unique_ords_out.loc[x]['거래처']} ({x})")
                d_out = pend[pend['주문번호']==tgt_out]
                st.dataframe(d_out[['코드','품목명','수량','팔레트번호']], use_container_width=True)
                if st.button("🚀 출고 확정", type="primary"):
                    for _, row in d_out.iterrows():
                        update_inventory(factory, row['코드'], -safe_float(row['수량']))
                        sheet_logs.append_row([datetime.date.today().strftime('%Y-%m-%d'), time_str, factory, "출고", row['코드'], row['품목명'], "-", "-", "-", -safe_float(row['수량']), f"주문출고({tgt_out})", row['거래처'], "-"])
                    all_rec = sheet_orders.get_all_records(); hd = sheet_orders.row_values(1)
                    upd = [hd] + [[r.get(h, "") if r['주문번호']!=tgt_out else (r['상태'] if h!='상태' else '완료') for h in hd] for r in all_rec]
                    sheet_orders.clear(); sheet_orders.update(upd); st.success("출고 완료"); st.cache_data.clear(); st.rerun()

    with tab_cancel:
        st.subheader("↩️ 출고 취소 및 재고 복구")
        st.warning("⚠️ 출고 취소 시 Orders 상태가 '준비'로 되돌아가고, 차감된 재고가 복구됩니다.")
        if df_orders.empty or '상태' not in df_orders.columns:
            st.info("주문 데이터가 없습니다.")
        else:
            done = df_orders[df_orders['상태'] == '완료']
            if done.empty:
                st.info("취소할 수 있는 완료된 출고 주문이 없습니다.")
            else:
                unique_done = done[['주문번호', '날짜', '거래처']].drop_duplicates().set_index('주문번호')
                tgt_cancel = st.selectbox(
                    "취소할 주문 선택",
                    done['주문번호'].unique(),
                    format_func=lambda x: f"{unique_done.loc[x]['날짜']} | {unique_done.loc[x]['거래처']} ({x})"
                )
                d_cancel = done[done['주문번호'] == tgt_cancel]
                st.dataframe(d_cancel[['코드', '품목명', '수량', '팔레트번호']], use_container_width=True, hide_index=True)
                st.markdown(f"**총 {d_cancel['수량'].sum():,.0f} kg** 복구 예정")

                if st.button("↩️ 출고 취소 확정", type="primary", key="cancel_confirm"):
                    try:
                        # 재고 복구 (출고 차감분 원복)
                        for _, row in d_cancel.iterrows():
                            update_inventory(factory, row['코드'], safe_float(row['수량']),
                                row['품목명'], "-", "-", "-")
                            sheet_logs.append_row([
                                datetime.date.today().strftime('%Y-%m-%d'), time_str, factory,
                                "출고취소", row['코드'], row['품목명'], "-", "-", "-",
                                safe_float(row['수량']), f"출고취소({tgt_cancel})", row['거래처'], "-"
                            ])
                        # Orders 상태를 '준비'로 복구
                        all_rec = sheet_orders.get_all_records()
                        hd = sheet_orders.row_values(1)
                        upd = [hd] + [
                            [(r['상태'] if h != '상태' else '준비') if str(r['주문번호']) == str(tgt_cancel) else r.get(h, "")
                             for h in hd]
                            for r in all_rec
                        ]
                        sheet_orders.clear(); sheet_orders.update(upd)
                        st.cache_data.clear(); st.success(f"✅ 주문 [{tgt_cancel}] 출고 취소 완료. 재고가 복구되었습니다."); st.rerun()
                    except Exception as e:
                        st.error(f"오류: {e}")


elif menu == "🌊 환경/폐수 일지":
    st.title("🌊 폐수배출시설 운영일지")
    tab_w1, tab_w2 = st.tabs(["📅 운영일지 작성", "📋 이력 조회"])
    with tab_w1:
        st.markdown("### 📅 월간 운영일지 작성")
        c_gen1, c_gen2, c_gen3 = st.columns(3)
        sel_year = c_gen1.number_input("연도", 2024, 2030, datetime.date.today().year)
        sel_month = c_gen2.number_input("월", 1, 12, datetime.date.today().month)
        use_random = c_gen3.checkbox("랜덤 변주 적용 (±1%)", value=False)
        if st.button("📝 일지 내역 작성"):
            start_date = datetime.date(sel_year, sel_month, 1)
            if sel_month == 12: end_date = datetime.date(sel_year + 1, 1, 1) - datetime.timedelta(days=1)
            else: end_date = datetime.date(sel_year, sel_month + 1, 1) - datetime.timedelta(days=1)
            date_list = pd.date_range(start=start_date, end=end_date)
            generated_rows = []
            for d in date_list:
                d_date = d.date(); d_str = d.strftime('%Y-%m-%d'); wk = ["월","화","수","목","금","토","일"][d_date.weekday()]
                full_d = f"{d.strftime('%Y년 %m월 %d일')} {wk}요일"
                daily_prod = df_logs[(df_logs['날짜'] == d_str) & (df_logs['공장'] == '1공장') & (df_logs['구분'] == '생산')]
                if not daily_prod.empty:
                    t_qty = daily_prod['수량'].sum(); res = round(t_qty * 0.8)
                    tm = "08:00~15:00" if d_date.weekday()==5 else "08:00~08:00"
                    if use_random: res = round(res * random.uniform(0.99, 1.01))
                    generated_rows.append({"날짜": full_d, "대표자": "문성인", "환경기술인": "문주혁", "가동시간": tm, "플라스틱재생칩": 0, "합성수지": res, "안료": 0.2, "용수사용량": 2.16, "폐수발생량": 0, "위탁량": "", "기타": "전량 재이용"})
                else:
                    generated_rows.append({"날짜": full_d, "대표자": "", "환경기술인": "", "가동시간": "", "플라스틱재생칩": "", "합성수지": "", "안료": "", "용수사용량": "", "폐수발생량": "", "위탁량": "", "기타": ""})
            st.session_state['wastewater_preview'] = pd.DataFrame(generated_rows); st.rerun()
        if 'wastewater_preview' in st.session_state:
            edited = st.data_editor(st.session_state['wastewater_preview'], num_rows="dynamic", use_container_width=True)
            if st.button("💾 일지 저장"):
                for _, r in edited.iterrows(): sheet_wastewater.append_row(list(r.values))
                st.success("저장됨"); st.cache_data.clear(); st.rerun()

    with tab_w2:
        st.markdown("### 📋 운영일지 이력 조회")
        if df_wastewater.empty:
            st.info("저장된 운영일지가 없습니다.")
        else:
            ww1, ww2 = st.columns(2)
            w_year = ww1.number_input("연도", 2024, 2030, datetime.date.today().year, key="ww_year")
            w_month = ww2.number_input("월 (0=전체)", 0, 12, datetime.date.today().month, key="ww_month")

            df_ww = df_wastewater.copy()
            df_ww = df_ww[df_ww['날짜'].astype(str).str.contains(str(w_year))]
            if w_month != 0:
                month_str = f"{w_month:02d}월"
                df_ww = df_ww[df_ww['날짜'].astype(str).str.contains(month_str)]

            st.caption(f"총 {len(df_ww)}건")
            st.dataframe(df_ww, use_container_width=True, hide_index=True)

            if not df_ww.empty:
                rows_html = ""
                for _, r in df_ww.iterrows():
                    rows_html += "<tr>" + "".join(f"<td>{r.get(c,'')}</td>" for c in df_ww.columns) + "</tr>"
                headers_html = "".join(f"<th>{c}</th>" for c in df_ww.columns)
                html_print = (
                    f"<h2 style='text-align:center'>폐수배출시설 운영일지 ({w_year}년 {w_month if w_month else '전체'}월)</h2>"
                    f"<table border='1' style='width:100%;border-collapse:collapse;font-size:11px;'>"
                    f"<thead><tr style='background:#ccc;'>{headers_html}</tr></thead>"
                    f"<tbody>{rows_html}</tbody></table>"
                )
                st.components.v1.html(create_print_button(html_print, "폐수운영일지", "landscape"), height=55)


elif menu == "📋 주간 회의 & 개선사항":
    st.title("📋 현장 주간 회의 및 개선사항 관리")

    MTG_COLS = ['날짜', '안건번호', '안건내용', '담당자', '공장', '상태', '비고', '완료일', '등록일']

    def gen_mtg_id():
        now = datetime.datetime.now()
        seq = len(df_meetings) + 1 if not df_meetings.empty else 1
        return f"M-{now.strftime('%y%m%d%H%M')}-{seq}"

    def save_meetings_edits(edited_df):
        if not sheet_meetings:
            st.error("시트 연결 실패. API 연결을 확인하세요."); return
        try:
            today_str = datetime.date.today().strftime('%Y-%m-%d')
            edited_df = edited_df.copy()
            mask = (edited_df['상태'].astype(str) == '완료') & (edited_df['완료일'].astype(str).str.strip() == '')
            if mask.any():
                edited_df.loc[mask, '완료일'] = today_str

            # 전체 시트 데이터를 raw values로 로드 (헤더 포함)
            all_vals = sheet_meetings.get_all_values()
            if not all_vals:
                st.error("시트가 비어 있습니다."); return
            headers = all_vals[0]
            df_all = pd.DataFrame(all_vals[1:], columns=headers) if len(all_vals) > 1 else pd.DataFrame(columns=headers)

            # 안건번호로 매칭하여 편집된 행 반영
            for _, erow in edited_df.iterrows():
                key = str(erow.get('안건번호', '')).strip()
                if not key: continue
                row_mask = df_all['안건번호'].astype(str).str.strip() == key
                if row_mask.any():
                    for col in headers:
                        if col in erow.index:
                            val = erow[col]
                            df_all.loc[row_mask, col] = '' if (isinstance(val, float) and pd.isna(val)) else str(val)

            write_data = [headers] + df_all.fillna('').astype(str).values.tolist()
            sheet_meetings.clear()
            sheet_meetings.update(write_data)
            st.success("저장 완료"); st.cache_data.clear(); st.rerun()
        except Exception as e:
            st.error(f"저장 실패: {e}")

    tab_m1, tab_m2, tab_m3 = st.tabs(["📊 안건 현황", "➕ 신규 안건 등록", "🔍 이력 조회 & 인쇄"])

    with tab_m1:
        fc1, fc2, fc3 = st.columns(3)
        m1_fac = fc1.selectbox("공장", ["전체", "1공장", "2공장", "공통"], key="m1_fac")
        m1_sta = fc2.multiselect("상태", ["진행중", "보류", "완료"], default=["진행중", "보류", "완료"], key="m1_sta")
        m1_dan = fc3.text_input("담당자 검색", key="m1_dan")

        df_base = df_meetings.copy() if not df_meetings.empty else pd.DataFrame(columns=MTG_COLS)
        for c in MTG_COLS:
            if c not in df_base.columns: df_base[c] = ""
        df_view = df_base.copy()
        if m1_fac != "전체": df_view = df_view[df_view['공장'] == m1_fac]
        if m1_sta: df_view = df_view[df_view['상태'].isin(m1_sta)]
        if m1_dan: df_view = df_view[df_view['담당자'].str.contains(m1_dan, na=False)]

        # 상태별 요약
        if not df_base.empty and '상태' in df_base.columns:
            s1, s2, s3 = st.columns(3)
            s1.metric("🔵 진행중", len(df_base[df_base['상태'] == '진행중']))
            s2.metric("🟡 보류", len(df_base[df_base['상태'] == '보류']))
            s3.metric("🟢 완료", len(df_base[df_base['상태'] == '완료']))
        st.markdown("---")

        if df_view.empty:
            st.info("조건에 맞는 안건이 없습니다.")
        else:
            edited = st.data_editor(
                df_view[MTG_COLS],
                column_config={
                    "안건번호": st.column_config.TextColumn("안건번호", disabled=True),
                    "등록일": st.column_config.TextColumn("등록일", disabled=True),
                    "상태": st.column_config.SelectboxColumn("상태", options=["진행중", "보류", "완료"]),
                    "완료일": st.column_config.TextColumn("완료일"),
                },
                use_container_width=True, hide_index=True, key="mtg_editor"
            )
            if st.button("💾 변경사항 저장", type="primary", key="m1_save"):
                save_meetings_edits(edited)

    with tab_m2:
        with st.form("new_mtg"):
            r1, r2 = st.columns(2)
            n_date = r1.date_input("회의 날짜")
            n_fac = r2.selectbox("공장", ["1공장", "2공장", "공통"])
            n_con = st.text_area("안건내용", height=120, placeholder="안건 내용을 입력하세요")
            r3, r4 = st.columns(2)
            n_ass = r3.text_input("담당자")
            n_note = r4.text_input("비고")
            if st.form_submit_button("✅ 안건 등록", type="primary"):
                new_id = gen_mtg_id()
                today_str = datetime.date.today().strftime('%Y-%m-%d')
                sheet_meetings.append_row([
                    n_date.strftime('%Y-%m-%d'), new_id, n_con, n_ass,
                    n_fac, "진행중", n_note, "", today_str
                ])
                st.success(f"등록 완료: {new_id}"); st.cache_data.clear(); st.rerun()

    with tab_m3:
        st.markdown("### 🔍 안건 이력 조회")
        s1, s2, s3 = st.columns(3)
        sf_fac = s1.selectbox("공장", ["전체", "1공장", "2공장", "공통"], key="m3_fac")
        sf_sta = s2.multiselect("상태", ["진행중", "보류", "완료"], key="m3_sta")
        sf_dan = s3.text_input("담당자", key="m3_dan")
        d1, d2 = st.columns(2)
        sf_start = d1.date_input("등록일 시작", value=datetime.date(2024, 1, 1), key="m3_start")
        sf_end = d2.date_input("등록일 종료", value=datetime.date.today(), key="m3_end")

        df_hist = df_meetings.copy() if not df_meetings.empty else pd.DataFrame(columns=MTG_COLS)
        for c in MTG_COLS:
            if c not in df_hist.columns: df_hist[c] = ""
        if sf_fac != "전체": df_hist = df_hist[df_hist['공장'] == sf_fac]
        if sf_sta: df_hist = df_hist[df_hist['상태'].isin(sf_sta)]
        if sf_dan: df_hist = df_hist[df_hist['담당자'].str.contains(sf_dan, na=False)]
        try:
            date_col = pd.to_datetime(df_hist['등록일'], errors='coerce').dt.date
            has_date = date_col.notna()
            if has_date.any():
                df_hist = df_hist[~has_date | date_col.between(sf_start, sf_end)]
        except: pass

        st.dataframe(df_hist[MTG_COLS], use_container_width=True, hide_index=True)
        st.caption(f"총 {len(df_hist)}건")

        if not df_hist.empty:
            rows_html = ""
            for _, r in df_hist.iterrows():
                sta = r.get('상태', '')
                bg = "#d4edda" if sta == "완료" else ("#fff3cd" if sta == "보류" else "#cce5ff")
                rows_html += (
                    f"<tr style='background:{bg};'>"
                    f"<td>{r.get('날짜','')}</td><td>{r.get('안건번호','')}</td>"
                    f"<td style='text-align:left;'>{r.get('안건내용','')}</td>"
                    f"<td>{r.get('담당자','')}</td><td>{r.get('공장','')}</td>"
                    f"<td><b>{sta}</b></td><td>{r.get('비고','')}</td>"
                    f"<td>{r.get('완료일','')}</td><td>{r.get('등록일','')}</td></tr>"
                )
            html_print = (
                f"<h2 style='text-align:center'>주간 회의 & 개선사항</h2>"
                f"<table border='1' style='width:100%;border-collapse:collapse;font-size:11px;'>"
                f"<thead><tr style='background:#ccc;'>"
                f"<th>날짜</th><th>안건번호</th><th>안건내용</th><th>담당자</th>"
                f"<th>공장</th><th>상태</th><th>비고</th><th>완료일</th><th>등록일</th>"
                f"</tr></thead><tbody>{rows_html}</tbody></table>"
            )
            st.components.v1.html(create_print_button(html_print, "주간회의안건", "landscape"), height=55)

# ==================== [3] 현장 작업 (LOT 입력) ====================
elif menu == "🏭 현장 작업 (LOT 입력)":
    st.title("🏭 현장 출고 LOT 입력")
    st.caption("출고 예정 주문(팔레트)을 선택해 LOT를 입력하는 화면입니다.")

    st.info("영업에서 등록된 주문(팔레트)을 선택하면 품목이 자동으로 채워집니다.")

    out_date    = st.date_input("출고일", datetime.date.today(), key="od")
    out_factory = st.selectbox("공장", ["1공장", "2공장"], key="of")

    # ── 주문(고객/팔레트) 선택 ──
    if df_orders.empty or '상태' not in df_orders.columns:
        st.warning("주문 데이터가 없습니다. 먼저 영업/출고 관리에서 주문을 등록해주세요.")
    else:
        pend_orders = df_orders[df_orders['상태'] == '준비'].copy()
        if pend_orders.empty:
            st.warning("출고 준비 중인 주문이 없습니다.")
        else:
            # 주문번호+거래처 선택
            pend_orders['주문표시'] = pend_orders['주문번호'].astype(str) + " | " + pend_orders['거래처'].astype(str) + " | " + pend_orders['날짜'].astype(str)
            unique_orders = pend_orders.drop_duplicates(subset=['주문번호'])
            sel_order_disp = st.selectbox("주문 선택 (거래처/주문번호)", unique_orders['주문표시'].tolist(), key="sel_ord")
            sel_order_id   = sel_order_disp.split(" | ")[0]
            sel_order_rows = pend_orders[pend_orders['주문번호'] == sel_order_id].copy()
            sel_order_rows['팔레트번호'] = pd.to_numeric(sel_order_rows['팔레트번호'], errors='coerce').fillna(0).astype(int)
            sel_order_rows = sel_order_rows.sort_values('팔레트번호')

            customer_name = sel_order_rows.iloc[0]['거래처']
            st.markdown(f"**거래처:** {customer_name} | **총 팔레트:** {sel_order_rows['팔레트번호'].nunique()}개 | **총 수량:** {sel_order_rows['수량'].sum():,.0f} kg")

            # 팔레트별 LOT 입력 테이블
            st.markdown("#### 팔레트별 LOT 번호 입력")
            st.caption("각 팔레트의 LOT 번호를 입력하세요. 수량은 주문 기준으로 자동 입력됩니다.")

            palette_groups = sel_order_rows.groupby('팔레트번호')
            lot_entries = []

            for plt_num, grp in palette_groups:
                st.markdown(f"**PLT {plt_num}**")
                for row_idx, (_, row) in enumerate(grp.iterrows()):
                    cols_plt = st.columns([3, 2, 2, 2])
                    cols_plt[0].write(f"{row['코드']} | {row['품목명']}")
                    qty_val = cols_plt[1].number_input("수량(kg)", value=float(row['수량']),
                                                        min_value=0.0, step=10.0,
                                                        key=f"plt_qty_{plt_num}_{row['코드']}_{row_idx}")
                    lot_val = cols_plt[2].text_input("LOT#", key=f"plt_lot_{plt_num}_{row['코드']}_{row_idx}")
                    note_val= cols_plt[3].text_input("비고", key=f"plt_note_{plt_num}_{row['코드']}_{row_idx}")
                    lot_entries.append({
                        '팔레트': plt_num,
                        '코드': row['코드'],
                        '품목명': row['품목명'],
                        '타입': row.get('타입', '-'),
                        '수량': qty_val,
                        'LOT': lot_val,
                        '비고': note_val,
                    })
                st.markdown("---")

            # 재고 확인
            if not df_inventory.empty:
                st.markdown("#### 📦 출고 예정 품목 재고 확인")
                inv_check_cols = st.columns([3,2,2,2])
                inv_check_cols[0].write("**품목**"); inv_check_cols[1].write("**출고예정**"); inv_check_cols[2].write("**현재고**"); inv_check_cols[3].write("**상태**")
                for entry in lot_entries:
                    inv_r = df_inventory[df_inventory['코드'].astype(str) == str(entry['코드'])]
                    stock = inv_r['현재고'].apply(safe_float).sum() if not inv_r.empty else 0
                    ic = st.columns([3,2,2,2])
                    ic[0].write(f"{entry['코드']} {entry['품목명']}")
                    ic[1].write(f"{entry['수량']:,.0f} kg")
                    ic[2].write(f"{stock:,.0f} kg")
                    if stock >= entry['수량']: ic[3].success("✅ 충분")
                    else: ic[3].error("⚠️ 부족")

            if st.button("🚚 전체 출고 LOT 저장", type="primary", key="lot_out_save"):
                if not sheet_logs:
                    st.error("시트 연결 오류.")
                elif not any(e['수량'] > 0 for e in lot_entries):
                    st.error("수량을 입력하세요.")
                else:
                    try:
                        now = datetime.datetime.now().strftime("%H:%M:%S")
                        for entry in lot_entries:
                            if entry['수량'] <= 0: continue
                            remark = f"PLT:{entry['팔레트']} LOT:{entry['LOT']} {entry['비고']}".strip()
                            sheet_logs.append_row([
                                out_date.strftime('%Y-%m-%d'), now, out_factory, "출고",
                                entry['코드'], entry['품목명'], "-",
                                entry['타입'], "-",
                                -entry['수량'], remark, customer_name, "-"
                            ])
                            update_inventory(out_factory, entry['코드'], -entry['수량'])
                            time.sleep(0.2)
                        # 주문 상태를 완료로 변경
                        all_rec = sheet_orders.get_all_records()
                        hd = sheet_orders.row_values(1)
                        upd = [hd] + [[(r.get(h,"") if h!='상태' else ('완료' if r['주문번호']==sel_order_id else r.get('상태',''))) for h in hd] for r in all_rec]
                        sheet_orders.clear(); sheet_orders.update(upd)
                        st.cache_data.clear()
                        st.success(f"✅ {customer_name} 출고 완료! LOT 기록 저장됨")
                        st.rerun()
                    except Exception as e:
                        st.error(f"저장 오류: {e}")

    st.markdown("---")
    st.subheader("📋 오늘 출고 현황")
    if not df_logs.empty and '구분' in df_logs.columns:
        today_s = datetime.date.today().strftime('%Y-%m-%d')
        df_out_today = df_logs[(df_logs['날짜'].astype(str).str[:10] == today_s) & (df_logs['구분'] == '출고')]
        if not df_out_today.empty:
            dc2 = [c for c in ['시간', '공장', '코드', '품목명', '수량', '비고'] if c in df_out_today.columns]
            st.dataframe(df_out_today[dc2].sort_values('시간', ascending=False), use_container_width=True, hide_index=True)
            st.metric("오늘 총 출고량", f"{abs(df_out_today['수량'].sum()):,.0f} kg")
        else:
            st.info("오늘 출고 기록이 없습니다.")


# ==================== [4] 이력/LOT 검색 ====================
elif menu == "🔍 이력/LOT 검색":
    st.title("🔍 이력 및 LOT 통합 검색")

    # ── 탭: 일반검색 / 고객(주문)별 검색 ──
    tab_s1, tab_s2 = st.tabs(["🔎 일반 이력 검색", "📦 고객(주문)별 출고 이력"])

    with tab_s1:
        s1, s2, s3 = st.columns(3)
        kw   = s1.text_input("키워드 (코드/품목명/LOT/비고)", placeholder="예: KA100, LOT-001", key="sk")
        stp  = s2.multiselect("구분 필터", ["생산", "입고", "출고", "사용(Auto)", "재고실사"],
                               default=["생산", "입고", "출고"], key="stp")
        sfac = s3.radio("공장", ["전체", "1공장", "2공장"], horizontal=True, key="sfac")

        d1, d2 = st.columns(2)
        ss = d1.date_input("시작일", datetime.date.today() - datetime.timedelta(days=30), key="ss")
        se = d2.date_input("종료일", datetime.date.today(), key="se")

        st.markdown("---")

        if df_logs.empty:
            st.warning("로그 데이터가 없습니다. 새로고침을 눌러주세요.")
        else:
            df_s = df_logs.copy()
            if '날짜' in df_s.columns:
                df_s['날짜_dt'] = pd.to_datetime(df_s['날짜'], errors='coerce')
                df_s = df_s[df_s['날짜_dt'].notna()]
                df_s = df_s[(df_s['날짜_dt'].dt.date >= ss) & (df_s['날짜_dt'].dt.date <= se)]
                df_s['날짜'] = df_s['날짜_dt'].dt.strftime('%Y-%m-%d')
                df_s = df_s.drop(columns=['날짜_dt'])
            if stp and '구분' in df_s.columns:
                df_s = df_s[df_s['구분'].isin(stp)]
            if sfac != "전체" and '공장' in df_s.columns:
                df_s = df_s[df_s['공장'] == sfac]
            if kw.strip():
                mask = pd.Series(False, index=df_s.index)
                for col in ['코드', '품목명', '비고']:
                    if col in df_s.columns:
                        mask = mask | df_s[col].astype(str).str.contains(kw.strip(), case=False, na=False)
                df_s = df_s[mask]

            st.write(f"검색 결과: **{len(df_s)}건**")
            if not df_s.empty:
                sc = [c for c in ['날짜', '시간', '공장', '구분', '코드', '품목명', '규격', '타입', '색상', '수량', '비고'] if c in df_s.columns]
                srt = [c for c in ['날짜', '시간'] if c in df_s.columns]
                st.dataframe(df_s[sc].sort_values(srt, ascending=False) if srt else df_s[sc],
                             use_container_width=True, hide_index=True)
                st.markdown("---")
                m1, m2, m3 = st.columns(3)
                if '구분' in df_s.columns and '수량' in df_s.columns:
                    m1.metric("총 생산량", f"{df_s[df_s['구분']=='생산']['수량'].sum():,.0f} kg")
                    m2.metric("총 출고량", f"{abs(df_s[df_s['구분']=='출고']['수량'].sum()):,.0f} kg")
                    m3.metric("총 입고량", f"{df_s[df_s['구분']=='입고']['수량'].sum():,.0f} kg")
                gc = [c for c in ['코드', '품목명', '구분'] if c in df_s.columns]
                if gc and '수량' in df_s.columns:
                    ag = df_s.groupby(gc)['수량'].sum().reset_index()
                    ag['수량'] = ag['수량'].round(2)
                    st.markdown("##### 품목별 집계")
                    st.dataframe(ag.sort_values('수량', ascending=False), use_container_width=True, hide_index=True)
            else:
                st.info("검색 결과가 없습니다.")

    with tab_s2:
        st.subheader("📦 고객(팔레트/주문)별 출고 이력 조회")
        st.caption("영업에서 등록된 주문번호 기준으로 출고 이력과 LOT를 확인합니다.")

        if df_orders.empty:
            st.warning("주문 데이터가 없습니다.")
        else:
            # 전체 주문(준비+완료) 대상
            all_orders = df_orders.copy()
            all_orders['주문표시'] = all_orders['주문번호'].astype(str) + " | " + all_orders['거래처'].astype(str) + " | " + all_orders['날짜'].astype(str) + " | " + all_orders['상태'].astype(str)
            unique_all = all_orders.drop_duplicates(subset=['주문번호']).sort_values('날짜', ascending=False)

            # 거래처 필터
            ca1, ca2 = st.columns(2)
            all_customers = ["전체"] + sorted(all_orders['거래처'].dropna().unique().tolist())
            sel_cust = ca1.selectbox("거래처 필터", all_customers, key="hist_cust")
            sel_status = ca2.selectbox("상태 필터", ["전체", "준비", "완료"], key="hist_status")

            filtered_orders = unique_all.copy()
            if sel_cust != "전체": filtered_orders = filtered_orders[filtered_orders['거래처'] == sel_cust]
            if sel_status != "전체": filtered_orders = filtered_orders[filtered_orders['상태'] == sel_status]

            if filtered_orders.empty:
                st.info("조건에 맞는 주문이 없습니다.")
            else:
                disp_opts = filtered_orders['주문표시'].tolist()
                sel_ord_disp = st.selectbox("조회할 주문 선택", disp_opts, key="hist_ord")
                sel_ord_id   = sel_ord_disp.split(" | ")[0]

                ord_detail = all_orders[all_orders['주문번호'] == sel_ord_id].copy()
                ord_detail['팔레트번호'] = pd.to_numeric(ord_detail['팔레트번호'], errors='coerce').fillna(0).astype(int)
                ord_detail = ord_detail.sort_values('팔레트번호')

                customer = ord_detail.iloc[0]['거래처']
                ord_date = ord_detail.iloc[0]['날짜']
                ord_status = ord_detail.iloc[0]['상태']

                st.markdown(f"**거래처:** {customer} | **주문일:** {ord_date} | **상태:** {'✅ 완료' if ord_status=='완료' else '🔄 준비중'}")

                # 주문 팔레트 구성
                st.markdown("#### 📋 팔레트 구성")
                show_cols = [c for c in ['팔레트번호', '코드', '품목명', '수량', '타입', '비고'] if c in ord_detail.columns]
                st.dataframe(ord_detail[show_cols], use_container_width=True, hide_index=True)
                st.metric("총 주문 수량", f"{ord_detail['수량'].sum():,.0f} kg")

                # 실제 출고 로그 매칭 (주문번호가 비고에 포함되거나, 거래처+날짜 기준)
                st.markdown("#### 🚚 실제 출고 로그 (LOT 포함)")
                if not df_logs.empty and '구분' in df_logs.columns:
                    df_out_hist = df_logs[df_logs['구분'] == '출고'].copy()
                    # 주문번호 또는 거래처명으로 매칭
                    mask_log = df_out_hist['비고'].astype(str).str.contains(sel_ord_id, case=False, na=False)
                    if '거래처' in df_out_hist.columns:
                        mask_log = mask_log | (df_out_hist['거래처'].astype(str) == customer)
                    df_out_matched = df_out_hist[mask_log].copy()

                    if not df_out_matched.empty:
                        log_cols = [c for c in ['날짜', '시간', '코드', '품목명', '수량', '비고'] if c in df_out_matched.columns]
                        st.dataframe(df_out_matched[log_cols].sort_values(['날짜','시간'], ascending=False),
                                     use_container_width=True, hide_index=True)
                        actual_out = abs(df_out_matched['수량'].sum())
                        planned    = ord_detail['수량'].sum()
                        col_a, col_b, col_c = st.columns(3)
                        col_a.metric("계획 수량", f"{planned:,.0f} kg")
                        col_b.metric("실제 출고", f"{actual_out:,.0f} kg")
                        diff = planned - actual_out
                        col_c.metric("미출고 잔량", f"{diff:,.0f} kg", delta=f"{diff:+,.0f}", delta_color="inverse" if diff>0 else "normal")
                    else:
                        st.info("해당 주문의 출고 로그가 없습니다. (아직 출고 전이거나 LOT 입력 전)")
                else:
                    st.info("로그 데이터가 없습니다.")
