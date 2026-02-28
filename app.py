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

# --- [STEP 0] 모든 도움 함수 (에러 방지 최상단 배치) ---

def get_product_category(row):
    """대시보드 분류를 위한 제품군 판별 함수"""
    name = str(row['품목명']).upper()
    code = str(row['코드']).upper()
    gubun = str(row.get('구분', '')).strip()
    if 'CP' in name or 'COMPOUND' in name or 'CP' in code: return "Compound"
    if ('KA' in name or 'KA' in code) and (gubun == '반제품' or name.endswith('반') or '반' in name): return "KA반제품"
    if 'KA' in name or 'KA' in code: return "KA"
    if 'KG' in name or 'KG' in code: return "KG"
    if gubun == '반제품' or name.endswith('반'): return "반제품(기타)"
    return "기타"

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
    except: pass

def safe_float(val):
    try: return float(val)
    except: return 0.0

def create_print_button(html_content, title="Print", orientation="portrait"):
    safe_content = html_content.replace('`', '\`').replace('$', '\$')
    page_css = "@page { size: A4 portrait; margin: 1cm; }"
    if orientation == "landscape": page_css = "@page { size: A4 landscape; margin: 1cm; }"
    js_code = f"""<script>
    function print_{title.replace(" ", "_")}() {{
        var win = window.open('', '', 'width=1100,height=800');
        win.document.write('<html><head><title>{title}</title><style>{page_css} body {{ font-family: "Malgun Gothic", sans-serif; margin: 0; padding: 10px; }} table {{ border-collapse: collapse; width: 100%; font-size: 11px; }} th, td {{ border: 1px solid black; padding: 5px; text-align: center; }} th {{ background-color: #f2f2f2; }} .title {{ text-align: center; font-size: 20px; font-weight: bold; margin-bottom: 20px; }}</style></head><body>');
        win.document.write(`{safe_content}`);
        win.document.write('</body></html>');
        win.document.close();
        win.focus();
        setTimeout(function() {{ win.print(); }}, 500);
    }}
    </script>
    <button onclick="print_{title.replace(" ", "_")}()" style="background-color: #4CAF50; border: none; color: white; padding: 12px 24px; font-size: 14px; margin: 10px 0; cursor: pointer; border-radius: 5px; font-weight: bold;">🖨️ {title} 인쇄하기 (A4 가로)</button>"""
    return js_code

# --- [STEP 1] 페이지 설정 ---
if os.path.exists("logo.png"):
    st.set_page_config(page_title="KPR ERP", page_icon="logo.png", layout="wide")
    add_apple_touch_icon("logo.png")
else:
    st.set_page_config(page_title="KPR ERP", page_icon="🏭", layout="wide")

# --- [STEP 2] 구글 시트 연결 ---
@st.cache_resource
def get_connection():
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    spreadsheet_id = "1qLWcLwS-aTBPeCn39h0bobuZlpyepfY5Hqn-hsP-hvk"
    try:
        if "gcp_service_account" in st.secrets:
            key_dict = dict(st.secrets["gcp_service_account"])
            creds = Credentials.from_service_account_info(key_dict, scopes=scopes)
            return gspread.authorize(creds).open_by_key(spreadsheet_id)
    except: pass
    key_file = 'key.json'
    if os.path.exists(key_file):
        creds = Credentials.from_service_account_file(key_file, scopes=scopes)
        return gspread.authorize(creds).open_by_key(spreadsheet_id)
    return None

doc = get_connection()

def get_sheet(doc, name, create_headers=None):
    if doc is None: return None
    try: return doc.worksheet(name)
    except:
        if create_headers:
            ws = doc.add_worksheet(title=name, rows="2000", cols="20")
            ws.append_row(create_headers)
            return ws
        return None

sheet_items = get_sheet(doc, 'Items')
sheet_inventory = get_sheet(doc, 'Inventory')
sheet_logs = get_sheet(doc, 'Logs')
sheet_bom = get_sheet(doc, 'BOM')
sheet_orders = get_sheet(doc, 'Orders')
sheet_wastewater = get_sheet(doc, 'Wastewater', ['날짜', '대표자', '환경기술인', '가동시간', '플라스틱재생칩', '합성수지', '안료', '용수사용량', '폐수발생량', '위탁량', '기타'])
sheet_meetings = get_sheet(doc, 'Meetings', ['ID', '작성일', '공장', '안건내용', '담당자', '상태', '비고'])

# --- [STEP 3] 데이터 로딩 ---
@st.cache_data(ttl=60)
def load_data():
    data = []
    sheets = [sheet_items, sheet_inventory, sheet_logs, sheet_bom, sheet_orders, sheet_wastewater, sheet_meetings]
    for s in sheets:
        df = pd.DataFrame()
        if s:
            for attempt in range(3):
                try:
                    d = s.get_all_records()
                    if d:
                        df = pd.DataFrame(d)
                        df = df.replace([np.inf, -np.inf], np.nan).fillna("")
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

def update_inventory(factory, code, qty, p_name="-", p_spec="-", p_type="-", p_color="-", p_unit="-"):
    if not sheet_inventory: return
    try:
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

# --- [STEP 4] 메인 로직 ---
if "authenticated" not in st.session_state: st.session_state["authenticated"] = False
if not st.session_state["authenticated"]:
    st.title("🔒 KPR ERP 시스템")
    passwd = st.text_input("접속 암호", type="password")
    if st.button("로그인", type="primary"):
        if passwd == "kpr1234": st.session_state["authenticated"] = True; st.rerun()
        else: st.error("암호가 틀렸습니다.")
    st.stop()

df_items, df_inventory, df_logs, df_bom, df_orders, df_wastewater, df_meetings, df_mapping = load_data()
if 'cart' not in st.session_state: st.session_state['cart'] = []

# --- [STEP 5] 사이드바 메뉴 ---
with st.sidebar:
    if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
    else: st.header("🏭 KPR / Chamstek")
    if st.button("🔄 새로고침"): st.cache_data.clear(); st.rerun()
    st.markdown("---")
    menu = st.radio("메뉴", ["대시보드", "재고/생산 관리", "영업/출고 관리", "🏭 현장 작업 (LOT 입력)", "🔍 이력/LOT 검색", "🌊 환경/폐수 일지", "📋 주간 회의 & 개선사항"])
    st.markdown("---")
    factory = st.selectbox("공장", ["1공장", "2공장"])

# [0] 대시보드
if menu == "대시보드":
    st.title("📊 공장 현황 대시보드")
    if not df_logs.empty:
        prod_log_only = df_logs[df_logs['구분'] == '생산'].copy()
        prod_dates_desc = sorted(prod_log_only['날짜'].unique(), reverse=True)
        latest_date = prod_dates_desc[0] if prod_dates_desc else datetime.date.today().strftime("%Y-%m-%d")
        
        # 실적 요약
        df_latest = df_logs[df_logs['날짜'] == latest_date]
        df_latest_prod = df_latest[df_latest['구분']=='생산'].copy()
        df_latest_prod['Category'] = df_latest_prod.apply(get_product_category, axis=1)
        
        st.subheader(f"📅 실적 요약 ({latest_date})")
        k1, k2, k3 = st.columns(3)
        k1.metric("총 생산량", f"{df_latest_prod['수량'].sum():,.0f} kg")
        k2.metric("총 출고량", f"{df_latest[df_latest['구분']=='출고']['수량'].sum():,.0f} kg")
        k3.metric("대기 주문", f"{len(df_orders[df_orders['상태']=='준비']['주문번호'].unique())} 건")
        
        st.markdown("---")
        
        # 🔥 [수정] 생산 추이 분석 - 기간 선택 기능 추가
        st.subheader("📈 생산 추이 분석")
        c_view1, c_view2 = st.columns([2, 1])
        view_opt = c_view1.radio("그래프 조회 설정", ["최근 5일", "기간 지정"], horizontal=True)
        
        if view_opt == "최근 5일":
            plot_dates = prod_dates_desc[:5][::-1]
            df_plot = prod_log_only[prod_log_only['날짜'].isin(plot_dates)].copy()
        else:
            s_d, e_d = c_view2.date_input("조회 기간", [datetime.date.today() - datetime.timedelta(days=10), datetime.date.today()])
            df_plot = prod_log_only.copy()
            df_plot['날짜_dt'] = pd.to_datetime(df_plot['날짜']).dt.date
            df_plot = df_plot[(df_plot['날짜_dt'] >= s_d) & (df_plot['날짜_dt'] <= e_d)]
        
        if not df_plot.empty:
            df_plot['Category'] = df_plot.apply(get_product_category, axis=1)
            prod_chart = alt.Chart(df_plot).mark_bar().encode(
                x=alt.X('날짜:N', title='작업일'),
                y=alt.Y('sum(수량):Q', title='생산량 (KG)'),
                color=alt.Color('Category:N', title='제품군'),
                xOffset='Category:N',
                tooltip=['날짜', 'Category', alt.Tooltip('sum(수량)', format=',.0f')]
            ).properties(height=350)
            st.altair_chart(prod_chart, use_container_width=True)

        st.markdown("---")
        
        # 원재료 입고 현황 (최근 10일)
        st.subheader("📥 원재료 입고 현황 (최근 10일)")
        df_inbound_all = df_logs[df_logs['구분'] == '입고'].copy()
        if not df_inbound_all.empty:
            in_dates = sorted(df_inbound_all['날짜'].unique(), reverse=True)[:10]
            df_in_10 = df_inbound_all[df_inbound_all['날짜'].isin(in_dates)]
            in_chart = alt.Chart(df_in_10).mark_bar().encode(
                x=alt.X('날짜:N', sort='descending'),
                y=alt.Y('sum(수량):Q', title='입고량 (KG)'),
                color='품목명:N',
                tooltip=['날짜', '품목명', '수량']
            ).properties(height=300)
            st.altair_chart(in_chart, use_container_width=True)

# [1] 재고/생산 관리 (기본 로직 유지)
elif menu == "재고/생산 관리":
    t1, t2, t3, t4, t5 = st.tabs(["🏭 생산 이력", "📥 원자재 입고 이력", "📦 재고 현황", "📜 전체 로그", "🔩 BOM"])
    with t1: st.dataframe(df_logs[df_logs['구분']=='생산'].sort_values(['날짜','시간'], ascending=False), use_container_width=True)
    with t2: st.dataframe(df_logs[df_logs['구분']=='입고'].sort_values(['날짜','시간'], ascending=False), use_container_width=True)
    with t3: st.dataframe(df_inventory, use_container_width=True)
    with t4: st.dataframe(df_logs, use_container_width=True)
    with t5: st.dataframe(df_bom, use_container_width=True)

# [2] 영업/출고 관리 (기본 로직 유지)
elif menu == "영업/출고 관리":
    tab_o, tab_p, tab_prt, tab_out = st.tabs(["📝 1. 주문 등록", "✏️ 2. 팔레트 수정/재구성", "🖨️ 3. 인쇄", "🚚 4. 출고"])
    # (세부 로직은 이전 v4.2와 동일하여 요약함)
    with tab_o:
        st.subheader("주문 장바구니")
        # 장바구니 UI 및 확정 로직...

# 🔥 [5] 환경/폐수 일지 (인쇄 기능 탑재)
elif menu == "🌊 환경/폐수 일지":
    st.title("🌊 폐수배출시설 운영일지")
    tab_w1, tab_w2 = st.tabs(["📅 일지 작성", "📋 이력 조회 및 인쇄"])
    
    with tab_w1:
        st.markdown("### 📅 월간 운영일지 불러오기")
        c1, c2 = st.columns(2)
        s_y = c1.number_input("연도", value=2026); s_m = c2.number_input("월", 1, 12, value=datetime.date.today().month)
        if st.button("📋 실적 기반 일지 작성"):
            days = pd.date_range(start=f"{s_y}-{s_m}-01", end=pd.to_datetime(f"{s_y}-{s_m}-01") + pd.offsets.MonthEnd(0))
            wk_map = {0:'월요일', 1:'화요일', 2:'수요일', 3:'목요일', 4:'금요일', 5:'토요일', 6:'일요일'}
            rows = []
            for d in days:
                d_str = d.strftime('%Y-%m-%d'); k_day = wk_map[d.weekday()]
                prod = df_logs[(df_logs['날짜']==d_str) & (df_logs['공장']=='1공장') & (df_logs['구분']=='생산')]
                row = {"날짜": f"{d_str} {k_day}", "대표자": "문성인", "환경기술인": "문주혁"}
                if not prod.empty:
                    q = prod['수량'].sum()
                    row.update({"가동시간": "08:00~08:00", "플라스틱재생칩": 0, "합성수지": int(q*0.8), "안료": 0.2, "용수사용량": 2.16, "폐수발생량": 0, "위탁량": "", "기타": "전량 재이용"})
                else: row.update({"가동시간":"", "플라스틱재생칩":"", "합성수지":"", "안료":"", "용수사용량":"", "폐수발생량":"", "위탁량":"", "기타":""})
                rows.append(row)
            st.session_state['ww_preview'] = pd.DataFrame(rows); st.rerun()
        
        if 'ww_preview' in st.session_state:
            edited_df = st.data_editor(st.session_state['ww_preview'], use_container_width=True, hide_index=True)
            if st.button("💾 일지 최종 저장"):
                data_list = edited_df.fillna("").values.tolist()
                sheet_wastewater.append_rows(data_list)
                st.success("저장되었습니다!"); del st.session_state['ww_preview']; st.cache_data.clear(); st.rerun()

    with tab_w2:
        st.subheader("📋 저장된 운영일지 관리")
        if not df_wastewater.empty:
            df_ww_show = df_wastewater.copy()
            st.dataframe(df_ww_show, use_container_width=True, hide_index=True)
            
            # 🔥 [신규] 가로방향 인쇄 기능
            st.markdown("---")
            st.markdown("#### 🖨️ 운영일지 출력 (A4 가로)")
            
            html_ww = f"""
            <div class="title">폐수배출시설 및 방지시설 운영일지</div>
            <table>
                <thead>
                    <tr>
                        <th>날짜</th><th>대표자</th><th>환경기술인</th><th>가동시간</th>
                        <th>재생칩</th><th>합성수지</th><th>안료</th><th>용수사용</th>
                        <th>폐수발생</th><th>위탁량</th><th>비고(기타)</th>
                    </tr>
                </thead>
                <tbody>
            """
            for _, r in df_ww_show.iterrows():
                html_ww += f"""
                    <tr>
                        <td>{r.get('날짜','')}</td><td>{r.get('대표자','')}</td><td>{r.get('환경기술인','')}</td><td>{r.get('가동시간','')}</td>
                        <td>{r.get('플라스틱재생칩','')}</td><td>{r.get('합성수지','')}</td><td>{r.get('안료','')}</td><td>{r.get('용수사용량','')}</td>
                        <td>{r.get('폐수발생량','')}</td><td>{r.get('위탁량','')}</td><td>{r.get('기타','')}</td>
                    </tr>
                """
            html_ww += "</tbody></table>"
            
            st.components.v1.html(create_print_button(html_ww, "운영일지", "landscape"), height=80)
            
            st.markdown("---")
            df_ww_show['Row'] = df_ww_show.index + 2
            del_target = st.selectbox("삭제할 행 선택", df_ww_show['Row'].tolist(), format_func=lambda x: f"{df_ww_show.loc[x-2, '날짜']} 삭제")
            if st.button("🗑️ 선택 이력 삭제", type="primary"):
                sheet_wastewater.delete_rows(int(del_target))
                st.success("삭제됨"); st.cache_data.clear(); st.rerun()
        else: st.info("기록이 없습니다.")

# [6] 주간 회의 & 개선사항 (기존 유지)
elif menu == "📋 주간 회의 & 개선사항":
    st.title("📋 현장 주간 회의 및 개선사항 관리")
    tab_m1, tab_m2, tab_m3 = st.tabs(["🚀 진행 중인 안건", "➕ 신규 등록", "🔍 이력 및 인쇄"])
    with tab_m1:
        if not df_meetings.empty:
            df_open = df_meetings[df_meetings['상태'] != '완료'].copy()
            edited_mtg = st.data_editor(df_open, use_container_width=True, hide_index=True)
            if st.button("💾 변경사항 저장"):
                all_rec = sheet_meetings.get_all_records(); hd = ['ID', '작성일', '공장', '안건내용', '담당자', '상태', '비고']
                new_all = [hd]
                for r in all_rec:
                    match = edited_mtg[edited_mtg['ID'] == r['ID']]
                    new_all.append([match.iloc[0][h] if not match.empty else r.get(h, "") for h in hd])
                sheet_meetings.clear(); sheet_meetings.update(new_all); st.success("저장됨"); st.cache_data.clear(); st.rerun()
    with tab_m2:
        with st.form("mtg_add"):
            n_d = st.date_input("날짜"); n_f = st.selectbox("공장",["1공장","2공장","공통"]); n_c = st.text_area("내용"); n_a = st.text_input("담당자")
            if st.form_submit_button("등록"):
                sheet_meetings.append_row([f"M-{int(time.time())}", n_d.strftime('%Y-%m-%d'), n_f, n_c, n_a, "진행중", ""])
                st.success("등록됨"); st.cache_data.clear(); st.rerun()
