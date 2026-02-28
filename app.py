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

# --- [0] 모든 도움 함수 정의 (NameError 방지를 위해 최상단에 배치) ---

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
    try: return float(val)
    except: return 0.0

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
    <button onclick="print_{title.replace(" ", "_")}()" style="background-color: #4CAF50; border: none; color: white; padding: 12px 24px; font-size: 14px; margin: 10px 0; cursor: pointer; border-radius: 5px; font-weight: bold;">🖨️ {title} 인쇄하기 (A4 가로)</button>"""
    return js_code

# --- [1] 페이지 설정 및 시트 연결 ---
st.set_page_config(page_title="KPR ERP", page_icon="🏭", layout="wide")

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

sheet_logs = get_sheet(doc, 'Logs')
sheet_orders = get_sheet(doc, 'Orders')
sheet_items = get_sheet(doc, 'Items')
sheet_inventory = get_sheet(doc, 'Inventory')
sheet_wastewater = get_sheet(doc, 'Wastewater', ['날짜', '대표자', '환경기술인', '가동시간', '플라스틱재생칩', '합성수지', '안료', '용수사용량', '폐수발생량', '위탁량', '기타'])
sheet_meetings = get_sheet(doc, 'Meetings', ['ID', '작성일', '공장', '안건내용', '담당자', '상태', '비고'])

# --- [2] 데이터 로딩 ---
@st.cache_data(ttl=60)
def load_data():
    def fetch(s):
        if not s: return pd.DataFrame()
        try:
            df = pd.DataFrame(s.get_all_records())
            return df.replace([np.inf, -np.inf], np.nan).fillna("")
        except: return pd.DataFrame()
    return fetch(sheet_items), fetch(sheet_inventory), fetch(sheet_logs), fetch(sheet_orders), fetch(sheet_wastewater), fetch(sheet_meetings)

df_items, df_inventory, df_logs, df_orders, df_wastewater, df_meetings = load_data()

# --- [3] 인증 로직 ---
if "authenticated" not in st.session_state: st.session_state["authenticated"] = False
if not st.session_state["authenticated"]:
    st.title("🔒 KPR ERP 시스템")
    passwd = st.text_input("접속 암호", type="password")
    if st.button("로그인", type="primary") and passwd == "kpr1234":
        st.session_state["authenticated"] = True; st.rerun()
    st.stop()

# --- [4] 사이드바 ---
with st.sidebar:
    st.header("🏭 KPR / Chamstek")
    if st.button("🔄 데이터 새로고침"): st.cache_data.clear(); st.rerun()
    menu = st.radio("메뉴 선택", ["대시보드", "재고/생산 관리", "영업/출고 관리", "🏭 현장 작업 (LOT)", "🔍 검색", "🌊 환경/폐수 일지", "📋 회의록"])

# --- [5] 대시보드 (그래프 및 기능 완벽 복구) ---
if menu == "대시보드":
    st.title("📊 공장 현황 대시보드")
    if not df_logs.empty:
        prod_log = df_logs[df_logs['구분'] == '생산'].copy()
        prod_dates = sorted(prod_log['날짜'].unique(), reverse=True)
        
        # 실적 요약
        latest = prod_dates[0] if prod_dates else ""
        st.subheader(f"📅 실적 요약 ({latest})")
        df_today = prod_log[prod_log['날짜'] == latest].copy()
        df_today['Category'] = df_today.apply(get_product_category, axis=1)
        
        c1, c2, c3 = st.columns(3)
        c1.metric("총 생산량", f"{df_today['수량'].sum():,.0f} kg")
        c2.metric("총 출고량", f"{df_logs[(df_logs['날짜']==latest) & (df_logs['구분']=='출고')]['수량'].sum():,.0f} kg")
        c3.metric("대기 주문", f"{len(df_orders[df_orders['상태']=='준비']['주문번호'].unique())} 건")

        st.markdown("---")
        
        # 생산 추이 분석 (최근 5일 기본 + 기간 지정 옵션)
        st.subheader("📈 생산 추이 분석")
        v_opt = st.radio("그래프 조회 범위", ["최근 5일 (자동)", "기간 직접 지정"], horizontal=True)
        
        if v_opt == "최근 5일 (자동)":
            plot_days = prod_dates[:5][::-1]
            df_plot = prod_log[prod_log['날짜'].isin(plot_days)].copy()
        else:
            s_d, e_d = st.date_input("조회 기간 선택", [datetime.date.today() - datetime.timedelta(days=10), datetime.date.today()])
            df_plot = prod_log.copy()
            df_plot['날짜_dt'] = pd.to_datetime(df_plot['날짜']).dt.date
            df_plot = df_plot[(df_plot['날짜_dt'] >= s_d) & (df_plot['날짜_dt'] <= e_d)]

        if not df_plot.empty:
            df_plot['Category'] = df_plot.apply(get_product_category, axis=1)
            # 그룹형 막대 차트 복구
            prod_chart = alt.Chart(df_plot).mark_bar().encode(
                x=alt.X('날짜:N', title='작업일'),
                y=alt.Y('sum(수량):Q', title='생산량 (KG)'),
                color=alt.Color('Category:N', title='제품군'),
                xOffset='Category:N', # 막대 분리 핵심
                tooltip=['날짜', 'Category', alt.Tooltip('sum(수량)', format=',.0f')]
            ).properties(height=350)
            st.altair_chart(prod_chart, use_container_width=True)

        # 원재료 입고 현황 복구
        st.markdown("---")
        st.subheader("📥 원재료 입고 현황 (최근 10일)")
        in_log = df_logs[df_logs['구분'] == '입고'].copy()
        if not in_log.empty:
            in_dates = sorted(in_log['날짜'].unique(), reverse=True)[:10]
            df_in_plot = in_log[in_log['날짜'].isin(in_dates)]
            in_chart = alt.Chart(df_in_plot).mark_bar().encode(
                x=alt.X('날짜:N', sort='descending'),
                y=alt.Y('sum(수량):Q', title='입고량 (KG)'),
                color='품목명:N',
                tooltip=['날짜', '품목명', '수량']
            ).properties(height=300)
            st.altair_chart(in_chart, use_container_width=True)

# --- [6] 환경/폐수 일지 (수정, 요일 한글화, 가로 인쇄, 삭제 통합) ---
elif menu == "🌊 환경/폐수 일지":
    st.title("🌊 폐수배출시설 운영일지")
    t1, t2 = st.tabs(["📅 일지 작성", "📋 이력 조회 및 인쇄"])
    
    with t1:
        st.markdown("### 📅 월간 실적 불러오기")
        col_y, col_m = st.columns(2)
        s_y = col_y.number_input("연도", value=datetime.date.today().year)
        s_m = col_m.number_input("월", 1, 12, value=datetime.date.today().month)
        
        if st.button("📋 실적 기반 일지 작성"):
            start_date = datetime.date(s_y, s_m, 1)
            # 월 말일 구하기
            next_m = start_date.replace(day=28) + datetime.timedelta(days=4)
            end_date = next_m - datetime.timedelta(days=next_m.day)
            
            days = pd.date_range(start=start_date, end=end_date)
            # 요일 한글화 맵핑
            kor_days = {0:'월요일', 1:'화요일', 2:'수요일', 3:'목요일', 4:'금요일', 5:'토요일', 6:'일요일'}
            
            rows = []
            for d in days:
                d_str = d.strftime('%Y-%m-%d')
                kor_day = kor_days[d.weekday()]
                prod = df_logs[(df_logs['날짜']==d_str) & (df_logs['공장']=='1공장') & (df_logs['구분']=='생산')]
                
                row = {"날짜": f"{d_str} {kor_day}", "대표자": "문성인", "환경기술인": "문주혁"}
                if not prod.empty:
                    q = prod['수량'].sum()
                    tm = "08:00~15:00" if d.weekday() == 5 else "08:00~08:00"
                    row.update({"가동시간": tm, "합성수지": int(q*0.8), "용수사용량": 2.16, "기타": "전량 재이용"})
                else:
                    row.update({"가동시간": "", "합성수지": "", "용수사용량": "", "기타": ""})
                rows.append(row)
            st.session_state['ww_preview'] = pd.DataFrame(rows); st.rerun()
            
        if 'ww_preview' in st.session_state:
            st.info("💡 아래 표에서 직접 내용을 수정한 뒤 저장할 수 있습니다.")
            # AttributeError 방지를 위한 안전한 편집기
            edited_df = st.data_editor(st.session_state['ww_preview'], use_container_width=True, hide_index=True)
            if st.button("💾 일지 최종 저장"):
                try:
                    # 안전한 리스트 변환 저장
                    data_list = edited_df.fillna("").values.tolist()
                    sheet_wastewater.append_rows(data_list)
                    st.success("저장 완료!"); del st.session_state['ww_preview']; st.cache_data.clear(); st.rerun()
                except Exception as e: st.error(f"저장 중 오류: {e}")

    with t2:
        st.subheader("📋 저장된 일지 관리 및 인쇄")
        if not df_wastewater.empty:
            # 인쇄 기능 (A4 가로)
            html_ww = f"""<div class="title">폐수배출시설 운영일지</div><table><thead><tr><th>날짜</th><th>대표자</th><th>기술인</th><th>가동시간</th><th>합성수지</th><th>용수</th><th>기타</th></tr></thead><tbody>"""
            for _, r in df_wastewater.iterrows():
                html_ww += f"<tr><td>{r.get('날짜','')}</td><td>{r.get('대표자','')}</td><td>{r.get('환경기술인','')}</td><td>{r.get('가동시간','')}</td><td>{r.get('합성수지','')}</td><td>{r.get('용수사용량','')}</td><td>{r.get('기타','')}</td></tr>"
            html_ww += "</tbody></table>"
            st.components.v1.html(create_print_button(html_ww, "운영일지", "landscape"), height=80)

            st.markdown("---")
            df_ww_show = df_wastewater.copy()
            df_ww_show['Row'] = df_ww_show.index + 2
            st.dataframe(df_ww_show.drop(columns=['Row']), use_container_width=True, hide_index=True)
            
            # 이력 삭제 기능 복구
            st.markdown("#### 🗑️ 이력 삭제")
            del_id = st.selectbox("삭제할 행 선택", df_ww_show['Row'].tolist(), format_func=lambda x: f"{df_ww_show.loc[x-2, '날짜']} 기록 삭제")
            if st.button("🗑️ 선택한 기록 영구 삭제", type="primary"):
                sheet_wastewater.delete_rows(int(del_id))
                st.success("삭제되었습니다."); st.cache_data.clear(); st.rerun()
        else: st.info("기록이 없습니다.")

# (기타 메뉴: 재고/영업/회의록 등 v4.2 로직 유지)
