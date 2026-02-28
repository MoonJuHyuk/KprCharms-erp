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

# --- [0] 모든 도움 함수 정의 (에러 방지 최상단 배치) ---

def get_product_category(row):
    """대시보드 제품군 분류 로직"""
    name = str(row.get('품목명', '')).upper()
    code = str(row.get('코드', '')).upper()
    gubun = str(row.get('구분', '')).strip()
    if 'CP' in name or 'COMPOUND' in name or 'CP' in code: return "Compound"
    if ('KA' in name or 'KA' in code) and (gubun == '반제품' or name.endswith('반') or '반' in name): return "KA반제품"
    if 'KA' in name or 'KA' in code: return "KA"
    if 'KG' in name or 'KG' in code: return "KG"
    return "기타"

def add_apple_touch_icon(image_path):
    try:
        if os.path.exists(image_path):
            with open(image_path, "rb") as f:
                b64_icon = base64.b64encode(f.read()).decode("utf-8")
                st.markdown(f"""<head><link rel="apple-touch-icon" href="data:image/png;base64,{b64_icon}"></head>""", unsafe_allow_html=True)
    except: pass

def safe_float(val):
    try: return float(str(val).replace(',', ''))
    except: return 0.0

def get_shape(code, df_items):
    if df_items.empty: return "-"
    row = df_items[df_items['코드'].astype(str) == str(code)]
    if not row.empty:
        t = str(row.iloc[0].get('타입', '-'))
        if "원통" in t: return "CYLINDRIC"
        if "큐빅" in t: return "CUBICAL"
        return t
    return "-"

def create_print_button(html_content, title="Print", orientation="portrait"):
    safe_content = html_content.replace('`', '\`').replace('$', '\$')
    page_css = "@page { size: A4 portrait; margin: 1cm; }"
    if orientation == "landscape": page_css = "@page { size: A4 landscape; margin: 1cm; }"
    js_code = f"""<script>
    function print_{title.replace(" ", "_")}() {{
        var win = window.open('', '', 'width=1100,height=800');
        win.document.write('<html><head><title>{title}</title><style>{page_css} body {{ font-family: "Malgun Gothic", sans-serif; padding: 10px; }} table {{ border-collapse: collapse; width: 100%; font-size: 11px; }} th, td {{ border: 1px solid black; padding: 5px; text-align: center; }} th {{ background-color: #f2f2f2; }} .title {{ text-align: center; font-size: 20px; font-weight: bold; margin-bottom: 20px; }}</style></head><body>');
        win.document.write(`{safe_content}`);
        win.document.write('</body></html>');
        win.document.close(); win.focus();
        setTimeout(function() {{ win.print(); }}, 500);
    }}
    </script>
    <button onclick="print_{title.replace(" ", "_")}()" style="background-color: #4CAF50; border: none; color: white; padding: 12px 24px; font-size: 14px; margin: 10px 0; cursor: pointer; border-radius: 5px; font-weight: bold;">🖨️ {title} 인쇄하기</button>"""
    return js_code

# --- [1] 시트 연결 설정 ---
@st.cache_resource
def get_connection():
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    spreadsheet_id = "1qLWcLwS-aTBPeCn39h0bobuZlpyepfY5Hqn-hsP-hvk"
    try:
        if "gcp_service_account" in st.secrets:
            creds = Credentials.from_service_account_info(dict(st.secrets["gcp_service_account"]), scopes=scopes)
            return gspread.authorize(creds).open_by_key(spreadsheet_id)
    except: pass
    return None

doc = get_connection()

def get_sheet(doc, name, headers=None):
    if doc is None: return None
    try: return doc.worksheet(name)
    except:
        if headers:
            ws = doc.add_worksheet(title=name, rows="2000", cols="20")
            ws.append_row(headers); return ws
        return None

sheet_items = get_sheet(doc, 'Items')
sheet_inventory = get_sheet(doc, 'Inventory')
sheet_logs = get_sheet(doc, 'Logs')
sheet_bom = get_sheet(doc, 'BOM')
sheet_orders = get_sheet(doc, 'Orders')
sheet_wastewater = get_sheet(doc, 'Wastewater', ['날짜', '대표자', '환경기술인', '가동시간', '플라스틱재생칩', '합성수지', '안료', '용수사용량', '폐수발생량', '위탁량', '기타'])
sheet_meetings = get_sheet(doc, 'Meetings', ['ID', '작성일', '공장', '안건내용', '담당자', '상태', '비고'])

# --- [2] 데이터 로딩 ---
@st.cache_data(ttl=30)
def load_data():
    def fetch(s):
        if not s: return pd.DataFrame()
        try:
            df = pd.DataFrame(s.get_all_records())
            return df.replace([np.inf, -np.inf], np.nan).fillna("")
        except: return pd.DataFrame()
    
    # Print_Mapping은 별도로 처리
    try:
        s_map = doc.worksheet("Print_Mapping")
        df_map = pd.DataFrame(s_map.get_all_records())
    except:
        df_map = pd.DataFrame(columns=['Code', 'Print_Name'])
        
    return fetch(sheet_items), fetch(sheet_inventory), fetch(sheet_logs), fetch(sheet_orders), fetch(sheet_wastewater), fetch(sheet_meetings), df_map

df_items, df_inventory, df_logs, df_orders, df_wastewater, df_meetings, df_mapping = load_data()

def update_inventory(factory, code, qty):
    if not sheet_inventory: return
    try:
        cells = sheet_inventory.findall(str(code))
        target = None
        for c in cells:
            if c.col == 2: target = c; break
        if target:
            curr = safe_float(sheet_inventory.cell(target.row, 7).value)
            sheet_inventory.update_cell(target.row, 7, curr + qty)
    except: pass

# --- [3] 인증 및 사이드바 ---
st.set_page_config(page_title="KPR ERP", page_icon="🏭", layout="wide")
if "authenticated" not in st.session_state: st.session_state["authenticated"] = False
if not st.session_state["authenticated"]:
    st.title("🔒 KPR ERP 시스템")
    if st.text_input("접속 암호", type="password") == "kpr1234":
        if st.button("로그인", type="primary"): st.session_state["authenticated"] = True; st.rerun()
    st.stop()

if 'cart' not in st.session_state: st.session_state['cart'] = []

with st.sidebar:
    st.header("🏭 KPR / Chamstek")
    if st.button("🔄 데이터 새로고침"): st.cache_data.clear(); st.rerun()
    st.markdown("---")
    menu = st.radio("메뉴 선택", ["대시보드", "재고/생산 관리", "영업/출고 관리", "🏭 현장 작업 (LOT 입력)", "🔍 이력/LOT 검색", "🌊 환경/폐수 일지", "📋 주간 회의 & 개선사항"])
    st.markdown("---")
    factory_sel = st.selectbox("접속 공장", ["1공장", "2공장"])

# --- [4] 메뉴별 로직 (하나도 빠짐없이 복구) ---

# 1. 대시보드
if menu == "대시보드":
    st.title("📊 공장 현황 대시보드")
    if not df_logs.empty:
        prod_log = df_logs[df_logs['구분'] == '생산'].copy()
        prod_dates = sorted(prod_log['날짜'].unique(), reverse=True)
        latest = prod_dates[0] if prod_dates else datetime.date.today().strftime("%Y-%m-%d")
        
        st.subheader(f"📅 최근 실적 요약 ({latest})")
        df_target = df_logs[df_logs['날짜'] == latest].copy()
        df_target_prod = df_target[df_target['구분']=='생산'].copy()
        df_target_prod['Category'] = df_target_prod.apply(get_product_category, axis=1)
        
        c1, c2, c3 = st.columns(3)
        c1.metric("총 생산량", f"{df_target_prod['수량'].sum():,.0f} kg")
        c2.metric("총 출고량", f"{df_target[df_target['구분']=='출고']['수량'].sum():,.0f} kg")
        c3.metric("대기 주문", f"{len(df_orders[df_orders['상태']=='준비']['주문번호'].unique())} 건")

        st.markdown("---")
        st.subheader("📈 생산 추이 분석")
        v_opt = st.radio("조회 기준", ["최근 5일", "기간 지정"], horizontal=True)
        if v_opt == "최근 5일":
            plot_days = prod_dates[:5][::-1]
            df_plot = prod_log[prod_log['날짜'].isin(plot_days)].copy()
        else:
            sd, ed = st.date_input("조회 기간", [datetime.date.today()-datetime.timedelta(days=7), datetime.date.today()])
            df_plot = prod_log.copy()
            df_plot['날짜_dt'] = pd.to_datetime(df_plot['날짜']).dt.date
            df_plot = df_plot[(df_plot['날짜_dt'] >= sd) & (df_plot['날짜_dt'] <= ed)]

        if not df_plot.empty:
            df_plot['Category'] = df_plot.apply(get_product_category, axis=1)
            chart = alt.Chart(df_plot).mark_bar().encode(
                x=alt.X('날짜:N', title='작업일'), y=alt.Y('sum(수량):Q', title='수량'),
                color='Category:N', xOffset='Category:N', tooltip=['날짜', 'Category', 'sum(수량)']
            ).properties(height=350)
            st.altair_chart(chart, use_container_width=True)

# 2. 재고/생산 관리
elif menu == "재고/생산 관리":
    st.title("📦 재고 및 생산 관리")
    tab1, tab2, tab3 = st.tabs(["🏭 실적 입력", "📊 현황 조회", "📥 입고 취소"])
    with tab1:
        with st.sidebar:
            st.markdown("### 📝 데이터 입력")
            cat = st.selectbox("구분", ["생산", "입고", "재고실사"])
            if not df_items.empty:
                items_filtered = df_items[df_items['구분'] == ('원자재' if cat == '입고' else '제품')]
                sel_name = st.selectbox("품목 선택", sorted(items_filtered['품목명'].unique()))
                qty = st.number_input("수량(kg)", min_value=0.0)
                if st.button("💾 저장하기"):
                    it_row = df_items[df_items['품목명']==sel_name].iloc[0]
                    sheet_logs.append_row([datetime.date.today().strftime('%Y-%m-%d'), datetime.datetime.now().strftime("%H:%M:%S"), factory_sel, cat, it_row['코드'], sel_name, it_row['규격'], it_row['타입'], it_row['색상'], qty, ""])
                    update_inventory(factory_sel, it_row['코드'], qty if cat != "출고" else -qty)
                    st.success("저장 완료"); st.cache_data.clear(); st.rerun()
    with tab2:
        st.subheader("📦 현재고 현황")
        st.dataframe(df_inventory, use_container_width=True)
    with tab3:
        st.subheader("📥 입고 취소")
        df_r = df_logs[df_logs['구분']=='입고'].copy()
        if not df_r.empty:
            df_r['Row'] = df_r.index + 2
            sel_row = st.selectbox("취소할 입고", df_r['Row'].tolist(), format_func=lambda x: f"{df_r.loc[x-2, '날짜']} | {df_r.loc[x-2, '품목명']}")
            if st.button("❌ 입고 취소 실행"):
                target = df_r[df_r['Row']==sel_row].iloc[0]
                update_inventory(target['공장'], target['코드'], -safe_float(target['수량']))
                sheet_logs.delete_rows(int(sel_row))
                st.success("취소됨"); st.cache_data.clear(); st.rerun()

# 3. 영업/출고 관리
elif menu == "영업/출고 관리":
    st.title("📑 영업 주문 관리")
    tab_o, tab_p, tab_out = st.tabs(["📝 주문 등록", "✏️ 팔레트 재구성", "🚚 출고 확정"])
    with tab_o:
        c1, c2 = st.columns([1, 2])
        with c1:
            o_it = st.selectbox("제품 선택", sorted(df_items[df_items['구분'].isin(['제품','완제품'])]['품목명'].unique()))
            o_q = st.number_input("주문량(kg)", step=100.0)
            if st.button("🛒 담기"):
                st.session_state['cart'].append({"품목명": o_it, "수량": o_q})
                st.rerun()
        with c2:
            st.subheader("🛒 장바구니")
            for i, it in enumerate(st.session_state['cart']):
                col_i = st.columns([4, 1])
                col_i[0].write(f"{it['품목명']} ({it['수량']:,}kg)")
                if col_i[1].button("❌", key=f"cart_{i}"): st.session_state['cart'].pop(i); st.rerun()
            if st.session_state['cart']:
                max_p = st.number_input("팔레트당 적재량(kg)", value=1000.0)
                if st.button("✅ 주문 확정", type="primary"):
                    oid = f"ORD-{int(time.time())}"
                    for it in st.session_state['cart']:
                        rem = it['수량']; plt = 1; it_d = df_items[df_items['품목명']==it['품목명']].iloc[0]
                        while rem > 0:
                            load = min(rem, max_p)
                            sheet_orders.append_row([oid, datetime.date.today().strftime('%Y-%m-%d'), "거래처", it_d['코드'], it['품목명'], load, plt, "준비", "BOX", "", it_d['타입']])
                            rem -= load; plt += 1
                    st.session_state['cart'] = []; st.success("확정됨"); st.cache_data.clear(); st.rerun()
    with tab_p:
        if not df_orders.empty:
            pend_ids = df_orders[df_orders['상태']=='준비']['주문번호'].unique()
            if len(pend_ids) > 0:
                sel_ord = st.selectbox("수정할 주문", pend_ids)
                df_ord_p = df_orders[df_orders['주문번호']==sel_ord]
                st.dataframe(df_ord_p[['팔레트번호', '품목명', '수량']], use_container_width=True)
                new_limit = st.number_input("새로운 적재량(kg)", value=1200.0)
                if st.button("🚀 팔레트 일괄 재구성"):
                    total_q = df_ord_p['수량'].sum(); main = df_ord_p.iloc[0]
                    all_recs = sheet_orders.get_all_records(); hd = sheet_orders.row_values(1)
                    filtered = [r for r in all_recs if str(r['주문번호']) != str(sel_ord)]
                    new_rows = []
                    rem = total_q; plt = 1
                    while rem > 0:
                        load = min(rem, new_limit)
                        new_rows.append([sel_ord, main['날짜'], main['거래처'], main['코드'], main['품목명'], load, plt, "준비", main['비고'], "", main['타입']])
                        rem -= load; plt += 1
                    sheet_orders.clear(); sheet_orders.update([hd] + [[r.get(h,"") for h in hd] for r in filtered] + new_rows)
                    st.success("재구성 완료"); st.cache_data.clear(); st.rerun()

# 4. 현장 작업 (LOT 입력)
elif menu == "🏭 현장 작업 (LOT 입력)":
    st.title("🏭 현장 작업 (LOT 번호 입력)")
    if not df_orders.empty:
        ready_ords = df_orders[df_orders['상태']=='준비']['주문번호'].unique()
        if len(ready_ords) > 0:
            sel_oid = st.selectbox("작업 주문 선택", ready_ords)
            df_work = df_orders[df_orders['주문번호']==sel_oid].copy()
            edited = st.data_editor(df_work[['팔레트번호', '품목명', '수량', 'LOT번호']], use_container_width=True, hide_index=True)
            if st.button("💾 LOT 정보 저장"):
                all_o = sheet_orders.get_all_records(); hd = sheet_orders.row_values(1)
                new_o = [hd]
                for r in all_o:
                    if str(r['주문번호']) == str(sel_oid):
                        # 매칭되는 팔레트번호의 LOT 업데이트
                        match = edited[edited['팔레트번호']==r['팔레트번호']]
                        if not match.empty: r['LOT번호'] = str(match.iloc[0]['LOT번호'])
                    new_o.append([r.get(h, "") for h in hd])
                sheet_orders.clear(); sheet_orders.update(new_o); st.success("저장됨"); st.cache_data.clear(); st.rerun()
        else: st.info("대기 중인 작업이 없습니다.")

# 5. 검색
elif menu == "🔍 이력/LOT 검색":
    st.title("🔍 이력 및 LOT 검색")
    c1, c2 = st.columns(2)
    s_lot = c1.text_input("LOT 번호 검색")
    s_cli = c2.text_input("거래처 검색")
    res = df_orders.copy()
    if s_lot: res = res[res['LOT번호'].str.contains(s_lot)]
    if s_cli: res = res[res['거래처'].str.contains(s_cli)]
    st.dataframe(res, use_container_width=True)

# 6. 환경/폐수 일지 (최종 수정판)
elif menu == "🌊 환경/폐수 일지":
    st.title("🌊 폐수배출시설 운영일지")
    t1, t2 = st.tabs(["📅 일지 작성", "📋 이력 조회 및 인쇄"])
    with t1:
        st.markdown("### 📅 월간 실적 불러오기")
        col_y, col_m = st.columns(2)
        s_y = col_y.number_input("연도", value=datetime.date.today().year)
        s_m = col_m.number_input("월", 1, 12, value=datetime.date.today().month)
        if st.button("📋 실적 기반 일지 작성"):
            start = datetime.date(s_y, s_m, 1)
            next_m = start.replace(day=28) + datetime.timedelta(days=4)
            end = next_m - datetime.timedelta(days=next_m.day)
            days = pd.date_range(start, end)
            wk_map = {0:'월요일', 1:'화요일', 2:'수요일', 3:'목요일', 4:'금요일', 5:'토요일', 6:'일요일'}
            rows = []
            for d in days:
                d_str = d.strftime('%Y-%m-%d'); kor_day = wk_map[d.weekday()]
                prod = df_logs[(df_logs['날짜']==d_str) & (df_logs['공장']=='1공장') & (df_logs['구분']=='생산')]
                row = {"날짜": f"{d_str} {kor_day}", "대표자": "문성인", "환경기술인": "문주혁"}
                if not prod.empty:
                    q = prod['수량'].sum()
                    row.update({"가동시간": "08:00~08:00", "합성수지": int(q*0.8), "안료": 0.2, "용수사용량": 2.16, "폐수발생량": 0, "기타": "전량 재이용"})
                else: row.update({"가동시간":"","합성수지":"","안료":"","용수사용량":"","폐수발생량":"","기타":""})
                rows.append(row)
            st.session_state['ww_preview'] = pd.DataFrame(rows); st.rerun()
        if 'ww_preview' in st.session_state:
            edited_df = st.data_editor(st.session_state['ww_preview'], use_container_width=True, hide_index=True)
            if st.button("💾 일지 최종 저장"):
                data_list = edited_df.fillna("").values.tolist()
                sheet_wastewater.append_rows(data_list)
                st.success("저장 완료!"); del st.session_state['ww_preview']; st.cache_data.clear(); st.rerun()
    with t2:
        if not df_wastewater.empty:
            html = "<h3>운영일지</h3><table border='1' style='width:100%; border-collapse:collapse;'><thead><tr style='background:#eee;'><th>날짜</th><th>기술인</th><th>가동시간</th><th>합성수지</th><th>용수</th></tr></thead><tbody>"
            for _, r in df_wastewater.iterrows():
                html += f"<tr><td>{r.get('날짜','')}</td><td>{r.get('환경기술인','')}</td><td>{r.get('가동시간','')}</td><td>{r.get('합성수지','')}</td><td>{r.get('용수사용량','')}</td></tr>"
            html += "</tbody></table>"
            st.components.v1.html(create_print_button(html, "운영일지", "landscape"), height=80)
            df_ww_show = df_wastewater.copy(); df_ww_show['Row'] = df_ww_show.index + 2
            st.dataframe(df_ww_show.drop(columns=['Row']), use_container_width=True)
            del_id = st.selectbox("삭제할 행", df_ww_show['Row'].tolist(), format_func=lambda x: f"{df_ww_show.loc[x-2, '날짜']} 삭제")
            if st.button("🗑️ 삭제 실행"):
                sheet_wastewater.delete_rows(int(del_id)); st.success("삭제됨"); st.cache_data.clear(); st.rerun()

# 7. 주간 회의 & 개선사항
elif menu == "📋 주간 회의 & 개선사항":
    st.title("📋 주간 회의록 관리")
    tab1, tab2 = st.tabs(["🚀 진행 중 안건", "➕ 신규 등록"])
    with tab1:
        if not df_meetings.empty:
            df_open = df_meetings[df_meetings['상태'] != '완료'].copy()
            edited_mtg = st.data_editor(df_open, use_container_width=True, hide_index=True)
            if st.button("💾 변경사항 저장"):
                all_m = sheet_meetings.get_all_records(); hd = sheet_meetings.row_values(1)
                new_m = [hd]
                for r in all_m:
                    match = edited_mtg[edited_mtg['ID']==r['ID']]
                    if not match.empty:
                        for h in hd: r[h] = match.iloc[0][h]
                    new_m.append([r.get(h, "") for h in hd])
                sheet_meetings.clear(); sheet_meetings.update(new_m); st.success("저장됨"); st.cache_data.clear(); st.rerun()
    with tab2:
        with st.form("new_mtg"):
            n_d = st.date_input("날짜"); n_f = st.selectbox("공장", ["1공장","2공장","공통"]); n_c = st.text_area("내용"); n_a = st.text_input("담당자")
            if st.form_submit_button("등록"):
                sheet_meetings.append_row([f"M-{int(time.time())}", n_d.strftime('%Y-%m-%d'), n_f, n_c, n_a, "진행중", ""])
                st.success("등록됨"); st.cache_data.clear(); st.rerun()
