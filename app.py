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

# --- [STEP 0] 모든 도움 함수 (에러 방지를 위해 최상단 배치) ---

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

# --- [STEP 1] 페이지 설정 ---
if os.path.exists("logo.png"):
    st.set_page_config(page_title="KPR ERP", page_icon="logo.png", layout="wide")
    add_apple_touch_icon("logo.png")
else:
    st.set_page_config(page_title="KPR ERP", page_icon="🏭", layout="wide")

# --- [STEP 2] 구글 시트 연결 및 자동 생성 기능 ---
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
    except: pass
    key_file = 'key.json'
    if os.path.exists(key_file):
        creds = Credentials.from_service_account_file(key_file, scopes=scopes)
        client = gspread.authorize(creds)
        return client.open_by_key(spreadsheet_id)
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

# --- [STEP 4] 메인 로직 시작 ---
if "authenticated" not in st.session_state: st.session_state["authenticated"] = False
if not st.session_state["authenticated"]:
    st.title("🔒 KPR ERP 시스템")
    passwd = st.text_input("접속 암호", type="password")
    if st.button("로그인", type="primary"):
        if passwd == "kpr1234":
            st.session_state["authenticated"] = True; st.rerun()
        else: st.error("암호가 틀렸습니다.")
    st.stop()

df_items, df_inventory, df_logs, df_bom, df_orders, df_wastewater, df_meetings, df_mapping = load_data()
if 'cart' not in st.session_state: st.session_state['cart'] = []

# --- [STEP 5] 사이드바 ---
with st.sidebar:
    if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
    else: st.header("🏭 KPR / Chamstek")
    if st.button("🔄 새로고침"): st.cache_data.clear(); st.rerun()
    st.markdown("---")
    menu = st.radio("메뉴", ["대시보드", "재고/생산 관리", "영업/출고 관리", "🏭 현장 작업 (LOT 입력)", "🔍 이력/LOT 검색", "🌊 환경/폐수 일지", "📋 주간 회의 & 개선사항"])
    st.markdown("---")
    factory = st.selectbox("공장", ["1공장", "2공장"])

# [0] 대시보드 (그래프 완벽 복구 버전)
if menu == "대시보드":
    st.title("📊 공장 현황 대시보드")
    if not df_logs.empty:
        # 최근 생산일 찾기
        prod_log_only = df_logs[df_logs['구분'] == '생산'].copy()
        prod_dates_desc = sorted(prod_log_only['날짜'].unique(), reverse=True)
        latest_date = prod_dates_desc[0] if prod_dates_desc else datetime.date.today().strftime("%Y-%m-%d")
        
        # 1. 요약 실적 (최근 작업일 기준)
        df_latest = df_logs[df_logs['날짜'] == latest_date]
        df_latest_prod = df_latest[df_latest['구분']=='생산'].copy()
        df_latest_prod['Category'] = df_latest_prod.apply(get_product_category, axis=1)
        
        total_q = df_latest_prod['수량'].sum()
        ka_q = df_latest_prod[df_latest_prod['Category']=='KA']['수량'].sum()
        kg_q = df_latest_prod[df_latest_prod['Category']=='KG']['수량'].sum()
        kab_q = df_latest_prod[df_latest_prod['Category']=='KA반제품']['수량'].sum()
        cp_q = df_latest_prod[df_latest_prod['Category']=='Compound']['수량'].sum()

        st.subheader(f"📅 실적 요약 ({latest_date})")
        k1, k2, k3 = st.columns(3)
        k1.metric("총 생산량", f"{total_q:,.0f} kg")
        k1.markdown(f"<div style='font-size:14px; color:gray;'>• KA: {ka_q:,.0f} kg / KG: {kg_q:,.0f} kg<br>• KA반제품: {kab_q:,.0f} kg / CP: {cp_q:,.0f} kg</div>", unsafe_allow_html=True)
        k2.metric("총 출고량", f"{df_latest[df_latest['구분']=='출고']['수량'].sum():,.0f} kg")
        k3.metric("대기 주문", f"{len(df_orders[df_orders['상태']=='준비']['주문번호'].unique())} 건")
        
        st.markdown("---")
        
        # 2. 생산 추이 분석 (최근 5일 작업일 기준)
        st.subheader("📈 최근 5일 생산 추이")
        recent_5_dates = prod_dates_desc[:5][::-1] # 최신 5개를 가져와서 날짜순 정렬
        df_prod_5days = prod_log_only[prod_log_only['날짜'].isin(recent_5_dates)].copy()
        df_prod_5days['Category'] = df_prod_5days.apply(get_product_category, axis=1)
        
        # 🔥 그룹형 막대 그래프 복구
        prod_chart = alt.Chart(df_prod_5days).mark_bar().encode(
            x=alt.X('날짜:N', title='작업일'),
            y=alt.Y('sum(수량):Q', title='생산량 (KG)'),
            color=alt.Color('Category:N', title='제품군', scale=alt.Scale(scheme='tableau10')),
            xOffset='Category:N', # 막대 쪼개기
            tooltip=['날짜', 'Category', alt.Tooltip('sum(수량)', format=',.0f')]
        ).properties(height=350)
        st.altair_chart(prod_chart, use_container_width=True)

        st.markdown("---")
        
        # 3. 원재료 입고 현황 (최근 10일치 기록)
        st.subheader("📥 원재료 입고 현황 (최근 10일)")
        df_inbound_all = df_logs[df_logs['구분'] == '입고'].copy()
        if not df_inbound_all.empty:
            in_dates = sorted(df_inbound_all['날짜'].unique(), reverse=True)[:10]
            df_in_10 = df_inbound_all[df_inbound_all['날짜'].isin(in_dates)]
            
            in_chart = alt.Chart(df_in_10).mark_bar().encode(
                x=alt.X('날짜:N', title='입고일', sort='descending'),
                y=alt.Y('sum(수량):Q', title='입고량 (KG)'),
                color=alt.Color('품목명:N', title='원재료명'),
                tooltip=['날짜', '품목명', alt.Tooltip('수량', format=',.0f')]
            ).properties(height=300)
            st.altair_chart(in_chart, use_container_width=True)
            
            with st.expander("📋 상세 입고 리스트"):
                st.dataframe(df_in_10[['날짜', '코드', '품목명', '수량', '비고']].sort_values('날짜', ascending=False), use_container_width=True, hide_index=True)
        else:
            st.info("입고 내역이 없습니다.")

# [1] 재고/생산 관리
elif menu == "재고/생산 관리":
    # (v2.7/3.2 기존 코드 유지)
    with st.sidebar:
        st.markdown("### 📝 작업 입력")
        cat = st.selectbox("구분", ["입고", "생산", "재고실사"])
        item_info = None; sel_code = None
        if not df_items.empty:
            df_f = df_items.copy()
            if cat=="입고": df_f = df_f[df_f['구분']=='원자재']
            elif cat=="생산": df_f = df_f[df_f['구분'].isin(['제품', '완제품', '반제품'])]
            grp_list = sorted(list(df_f['구분'].unique())) if not df_f.empty else []
            if grp_list:
                sel_grp = st.selectbox("품목 분류", grp_list)
                df_step = df_f[df_f['구분']==sel_grp]
                sel_it_name = st.selectbox("품목 선택", sorted(list(df_step['품목명'].unique())))
                final_it = df_step[df_step['품목명']==sel_it_name].iloc[0]
                sel_code = final_it['코드']; item_info = final_it
                st.info(f"코드: {sel_code}")

        qty_in = st.number_input("수량", min_value=0.0)
        note_in = st.text_input("비고")
        if st.button("저장"):
            if sel_code:
                sheet_logs.append_row([datetime.date.today().strftime('%Y-%m-%d'), datetime.datetime.now().strftime("%H:%M:%S"), factory, cat, sel_code, item_info['품목명'], item_info['규격'], item_info['타입'], item_info['색상'], qty_in, note_in])
                update_inventory(factory, sel_code, qty_in if cat != "출고" else -qty_in)
                st.success("저장 완료!"); st.cache_data.clear(); st.rerun()

    t1, t2, t3, t4, t5 = st.tabs(["🏭 생산 이력", "📥 원자재 입고 이력", "📦 재고 현황", "📜 전체 로그", "🔩 BOM"])
    with t1:
        st.dataframe(df_logs[df_logs['구분']=='생산'].sort_values(['날짜', '시간'], ascending=False), use_container_width=True)
    with t2:
        df_r = df_logs[df_logs['구분']=='입고'].copy()
        st.dataframe(df_r.sort_values(['날짜', '시간'], ascending=False), use_container_width=True)
        if not df_r.empty:
            df_r['Row'] = df_r.index + 2
            sel_del = st.selectbox("취소할 입고 선택", df_r['Row'].tolist(), format_func=lambda x: f"No.{x} | {df_r.loc[x-2, '품목명']} ({df_r.loc[x-2, '수량']}kg)")
            if st.button("❌ 선택 입고 취소", type="primary"):
                target = df_r[df_r['Row']==sel_del].iloc[0]
                update_inventory(target['공장'], target['코드'], -safe_float(target['수량']))
                sheet_logs.delete_rows(int(sel_del))
                st.success("취소 완료"); st.cache_data.clear(); st.rerun()
    with t3:
        st.dataframe(df_inventory, use_container_width=True)
    with t4:
        st.dataframe(df_logs, use_container_width=True)
    with t5:
        st.dataframe(df_bom, use_container_width=True)

# [2] 영업/출고 관리
elif menu == "영업/출고 관리":
    st.title("📑 영업 주문 및 출고 관리")
    tab_o, tab_p, tab_prt, tab_out = st.tabs(["📝 1. 주문 등록", "✏️ 2. 팔레트 수정/재구성", "🖨️ 3. 인쇄", "🚚 4. 출고"])
    
    with tab_o:
        c1, c2 = st.columns([1, 2])
        with c1:
            st.subheader("주문 담기")
            o_it = st.selectbox("제품 선택", sorted(df_items[df_items['구분'].isin(['제품','완제품'])]['품목명'].unique()))
            o_q = st.number_input("수량(kg)", step=100.0)
            if st.button("🛒 담기"):
                it_data = df_items[df_items['품목명']==o_it].iloc[0]
                st.session_state['cart'].append({"코드": it_data['코드'], "품목명": o_it, "수량": o_q, "타입": it_data['타입']})
                st.rerun()
        with c2:
            st.subheader("🛒 장바구니")
            for i, item in enumerate(st.session_state['cart']):
                cols = st.columns([4, 1])
                cols[0].write(f"{item['품목명']} - {item['수량']:,}kg")
                if cols[1].button("❌", key=f"cart_del_{i}"):
                    st.session_state['cart'].pop(i); st.rerun()
            
            if st.session_state['cart']:
                max_p = st.number_input("팔레트당 적재량(kg)", value=1000.0)
                if st.button("✅ 최종 주문 확정", type="primary"):
                    oid = f"ORD-{int(time.time())}"
                    for it in st.session_state['cart']:
                        rem = it['수량']; plt = 1
                        while rem > 0:
                            load = min(rem, max_p)
                            sheet_orders.append_row([oid, datetime.date.today().strftime('%Y-%m-%d'), "거래처", it['코드'], it['품목명'], load, plt, "준비", "BOX", "", it['타입']])
                            rem -= load; plt += 1
                    st.session_state['cart'] = []; st.success("확정됨"); st.cache_data.clear(); st.rerun()

    with tab_p:
        if not df_orders.empty:
            pend_ids = df_orders[df_orders['상태']=='준비']['주문번호'].unique()
            if len(pend_ids) > 0:
                sel_ord = st.selectbox("수정할 주문", pend_ids)
                df_ord = df_orders[df_orders['주문번호']==sel_ord].copy()
                st.write("현재 구성")
                st.dataframe(df_ord[['팔레트번호', '품목명', '수량']], use_container_width=True, hide_index=True)
                
                with st.expander("📦 팔레트 일괄 재구성 (Re-Split)"):
                    new_limit = st.number_input("새 적재량(kg)", value=1200.0)
                    if st.button("🚀 재구성 실행"):
                        total_q = df_ord['수량'].sum(); it_main = df_ord.iloc[0]
                        all_recs = sheet_orders.get_all_records(); hd = sheet_orders.row_values(1)
                        filtered = [r for r in all_recs if str(r['주문번호']) != str(sel_ord)]
                        new_rows = []
                        rem = total_q; plt = 1
                        while rem > 0:
                            load = min(rem, new_limit)
                            new_rows.append([sel_ord, it_main['날짜'], it_main['거래처'], it_main['코드'], it_main['품목명'], load, plt, "준비", it_main['비고'], "", it_main['타입']])
                            rem -= load; plt += 1
                        sheet_orders.clear(); sheet_orders.update([hd] + [[r.get(h,"") for h in hd] for r in filtered] + new_rows)
                        st.success("재구성 완료!"); st.cache_data.clear(); st.rerun()

# [5] 환경/폐수 일지 (수정 및 삭제 기능 포함)
elif menu == "🌊 환경/폐수 일지":
    st.title("🌊 폐수배출시설 운영일지")
    tab_w1, tab_w2 = st.tabs(["📅 일지 작성", "📋 이력 조회 및 삭제"])
    
    with tab_w1:
        st.markdown("### 📅 월간 운영일지 불러오기")
        c1, c2 = st.columns(2)
        s_y = c1.number_input("연도", value=datetime.date.today().year)
        s_m = c2.number_input("월", 1, 12, value=datetime.date.today().month)
        
        if st.button("📋 실적 기반 일지 작성"):
            start_date = datetime.date(s_y, s_m, 1)
            next_month = start_date.replace(day=28) + datetime.timedelta(days=4)
            end_date = next_month - datetime.timedelta(days=next_month.day)
            days = pd.date_range(start=start_date, end=end_date)
            
            wk_map = {0:'월요일', 1:'화요일', 2:'수요일', 3:'목요일', 4:'금요일', 5:'토요일', 6:'일요일'}
            rows = []
            for d in days:
                d_str = d.strftime('%Y-%m-%d'); k_day = wk_map[d.weekday()]
                prod = df_logs[(df_logs['날짜']==d_str) & (df_logs['공장']=='1공장') & (df_logs['구분']=='생산')]
                row = {"날짜": f"{d_str} {k_day}", "대표자": "문성인", "환경기술인": "문주혁"}
                if not prod.empty:
                    q = prod['수량'].sum()
                    tm = "08:00~15:00" if d.weekday() == 5 else "08:00~08:00"
                    row.update({"가동시간": tm, "합성수지": int(q*0.8), "안료": 0.2, "용수사용량": 2.16, "기타": "전량 재이용"})
                else: row.update({"가동시간": "", "합성수지": "", "안료": "", "용수사용량": "", "기타": ""})
                rows.append(row)
            st.session_state['ww_preview'] = pd.DataFrame(rows); st.rerun()
        
        if 'ww_preview' in st.session_state:
            st.info("💡 표 안의 내용을 직접 수정한 뒤 저장할 수 있습니다.")
            edited_df = st.data_editor(st.session_state['ww_preview'], use_container_width=True, hide_index=True)
            if st.button("💾 일지 최종 저장"):
                try:
                    # 안전하게 리스트로 변환하여 저장
                    data_list = edited_df.fillna("").values.tolist()
                    sheet_wastewater.append_rows(data_list)
                    st.success("저장되었습니다!"); del st.session_state['ww_preview']; st.cache_data.clear(); st.rerun()
                except Exception as e: st.error(f"저장 오류: {e}")

    with tab_w2:
        st.subheader("📋 저장된 일지 조회 및 삭제")
        if not df_wastewater.empty:
            df_ww_m = df_wastewater.copy()
            df_ww_m['Row'] = df_ww_m.index + 2
            st.dataframe(df_ww_m.drop(columns=['Row']), use_container_width=True, hide_index=True)
            st.markdown("---")
            del_target = st.selectbox("삭제할 날짜 선택", df_ww_m['Row'].tolist(), format_func=lambda x: f"{df_ww_m.loc[x-2, '날짜']} 기록 삭제")
            if st.button("🗑️ 선택 기록 삭제", type="primary"):
                sheet_wastewater.delete_rows(int(del_target))
                st.success("삭제됨"); st.cache_data.clear(); st.rerun()
        else: st.info("데이터가 없습니다.")

# [6] 주간 회의 & 개선사항
elif menu == "📋 주간 회의 & 개선사항":
    st.title("📋 현장 주간 회의 및 개선사항 관리")
    tab_m1, tab_m2, tab_m3 = st.tabs(["🚀 진행 중인 안건", "➕ 신규 등록", "🔍 이력 및 인쇄"])
    
    with tab_m1:
        if not df_meetings.empty:
            df_open = df_meetings[df_meetings['상태'] != '완료'].copy()
            edited_mtg = st.data_editor(df_open, use_container_width=True, hide_index=True)
            if st.button("💾 변경사항 저장"):
                all_rec = sheet_meetings.get_all_values(); hd = ['ID', '작성일', '공장', '안건내용', '담당자', '상태', '비고']
                new_all = [hd]
                for r in sheet_meetings.get_all_records():
                    match = edited_mtg[edited_mtg['ID'] == r['ID']]
                    if not match.empty: new_all.append([match.iloc[0][h] for h in hd])
                    else: new_all.append([r.get(h, "") for h in hd])
                sheet_meetings.clear(); sheet_meetings.update(new_all)
                st.success("저장됨"); st.cache_data.clear(); st.rerun()
    with tab_m2:
        with st.form("mtg_new"):
            n_d = st.date_input("날짜", datetime.date.today()); n_f = st.selectbox("공장", ["1공장","2공장","공통"]); n_c = st.text_area("안건"); n_a = st.text_input("담당자")
            if st.form_submit_button("등록"):
                sheet_meetings.append_row([f"M-{int(time.time())}", n_d.strftime('%Y-%m-%d'), n_f, n_c, n_a, "진행중", ""])
                st.success("등록됨"); st.cache_data.clear(); st.rerun()
    with tab_m3:
        f_fac = st.selectbox("공장 선택", ["전체", "1공장", "2공장", "공통"])
        df_f = df_meetings.copy()
        if f_fac != "전체": df_f = df_f[df_f['공장']==f_fac]
        st.dataframe(df_f.sort_values('작성일', ascending=False), use_container_width=True, hide_index=True)
