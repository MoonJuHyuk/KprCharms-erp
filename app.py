import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import datetime
import os
import time
import altair as alt
import base64

# --- 1. 구글 시트 연결 ---
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

# 안전하게 시트 가져오기
def get_sheet(doc, name):
    try: return doc.worksheet(name)
    except: return None

sheet_items = get_sheet(doc, 'Items')
sheet_inventory = get_sheet(doc, 'Inventory')
sheet_logs = get_sheet(doc, 'Logs')
sheet_bom = get_sheet(doc, 'BOM')
sheet_orders = get_sheet(doc, 'Orders')

# --- 2. 데이터 로딩 (캐싱 적용) ---
@st.cache_data(ttl=60)
def load_data():
    data = []
    sheets = [sheet_items, sheet_inventory, sheet_logs, sheet_bom, sheet_orders]
    for s in sheets:
        if s:
            for attempt in range(3):
                try:
                    data.append(pd.DataFrame(s.get_all_records()))
                    break
                except:
                    time.sleep(1)
                    if attempt == 2: data.append(pd.DataFrame())
        else: data.append(pd.DataFrame())
    return tuple(data)

def safe_float(val):
    try: return float(val)
    except: return 0.0

# --- 3. 재고 업데이트 ---
def update_inventory(factory, code, qty, p_name="-", p_spec="-", p_type="-", p_color="-", p_unit="-"):
    if not sheet_inventory: return
    try:
        time.sleep(1)
        cells = sheet_inventory.findall(str(code))
        target = None
        for c in cells:
            if sheet_inventory.cell(c.row, 1).value == factory:
                target = c; break
        if target:
            curr = safe_float(sheet_inventory.cell(target.row, 7).value)
            sheet_inventory.update_cell(target.row, 7, curr + qty)
        else:
            sheet_inventory.append_row([factory, code, p_name, p_spec, p_type, p_color, qty])
    except: pass

# --- 4. 헬퍼 함수 ---
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

# 🔥 팝업 인쇄 버튼 생성 함수
def create_print_button(html_content, title="Print", orientation="portrait"):
    safe_content = html_content.replace('`', '\`').replace('$', '\$')
    page_css = "@page { size: A4 portrait; margin: 1cm; }"
    if orientation == "landscape":
        page_css = "@page { size: A4 landscape; margin: 1cm; }"

    js_code = f"""
    <script>
    function print_{title.replace(" ", "_")}() {{
        var win = window.open('', '', 'width=900,height=700');
        win.document.write('<html><head><title>{title}</title>');
        win.document.write('<style>');
        win.document.write('{page_css}');
        win.document.write('body {{ font-family: sans-serif; -webkit-print-color-adjust: exact; margin: 0; padding: 0; }}');
        win.document.write('table {{ border-collapse: collapse; width: 100%; }} th, td {{ border: 1px solid black; padding: 4px; }}');
        win.document.write('.page-break {{ page-break-after: always; width: 100vw; height: 100vh; display: flex; justify-content: center; align-items: center; }}');
        win.document.write('</style></head><body>');
        win.document.write(`{safe_content}`);
        win.document.write('</body></html>');
        win.document.close();
        win.focus();
        setTimeout(function() {{ win.print(); }}, 500);
    }}
    </script>
    <button onclick="print_{title.replace(" ", "_")}()" style="
        background-color: #4CAF50; border: none; color: white; padding: 10px 20px;
        text-align: center; text-decoration: none; display: inline-block;
        font-size: 14px; margin: 4px 2px; cursor: pointer; border-radius: 5px;">
        🖨️ {title} 인쇄하기
    </button>
    """
    return js_code

def add_apple_touch_icon(image_path):
    try:
        with open(image_path, "rb") as f:
            img_data = f.read()
            b64_icon = base64.b64encode(img_data).decode("utf-8")
            st.markdown(
                f"""<head>
                <link rel="apple-touch-icon" sizes="180x180" href="data:image/png;base64,{b64_icon}">
                <link rel="icon" type="image/png" sizes="32x32" href="data:image/png;base64,{b64_icon}">
                </head>""", unsafe_allow_html=True
            )
    except Exception: pass

# --- 5. 메인 앱 설정 ---
if os.path.exists("logo.png"):
    st.set_page_config(page_title="KPR ERP", page_icon="logo.png", layout="wide")
    add_apple_touch_icon("logo.png")
else:
    st.set_page_config(page_title="KPR ERP", page_icon="🏭", layout="wide")

# 🔒 로그인
if "authenticated" not in st.session_state: st.session_state["authenticated"] = False
if not st.session_state["authenticated"]:
    st.title("🔒 KPR ERP 시스템")
    c1, c2 = st.columns([1, 2])
    with c1:
        pw = st.text_input("접속 암호", type="password")
        if st.button("로그인"):
            if pw == "kpr1234":
                st.session_state["authenticated"] = True; st.rerun()
            else: st.error("암호가 틀렸습니다.")
    st.stop()

df_items, df_inventory, df_logs, df_bom, df_orders = load_data()
if 'cart' not in st.session_state: st.session_state['cart'] = []

# --- 사이드바 ---
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
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        df_today = df_logs[df_logs['날짜'] == today]
        k1, k2, k3 = st.columns(3)
        prod = df_today[df_today['구분']=='생산']['수량'].sum() if '구분' in df_today.columns else 0
        out = df_today[df_today['구분']=='출고']['수량'].sum() if '구분' in df_today.columns else 0
        k1.metric("오늘 생산", f"{prod:,.0f} kg")
        k2.metric("오늘 출고", f"{out:,.0f} kg")
        pend = len(df_orders[df_orders['상태']=='준비']['주문번호'].unique()) if not df_orders.empty and '상태' in df_orders.columns else 0
        k3.metric("출고 대기 주문", f"{pend} 건", delta="작업 필요", delta_color="inverse")
        st.markdown("---")
        if '구분' in df_logs.columns:
            df_prod = df_logs[df_logs['구분'] == '생산'].copy()
            if not df_prod.empty:
                st.subheader("📈 최근 7일 생산 추이")
                daily_prod = df_prod.groupby('날짜')['수량'].sum().reset_index().sort_values('날짜').tail(7)
                chart = alt.Chart(daily_prod).mark_bar().encode(x='날짜', y='수량', tooltip=['날짜', '수량']).properties(height=300)
                st.altair_chart(chart, use_container_width=True)

# [1] 재고/생산 관리
elif menu == "재고/생산 관리":
    with st.sidebar:
        st.markdown("### 📝 작업 입력")
        cat = st.selectbox("구분", ["입고", "생산", "이동", "재고실사"])
        
        sel_code=None; item_info=None; sys_q=0.0
        
        # [NEW] 생산일 경우 라인 선택 기능
        prod_line = "-"
        if cat == "생산":
            prod_line = st.selectbox("설비 라인", ["압출1호", "압출2호", "압출3호", "압출4호", "기타"])

        if not df_items.empty:
            df_f = df_items.copy()
            df_f['Group'] = df_f['품목명'].apply(lambda x: "KG" if "KG" in str(x).upper() else ("KA" if "KA" in str(x).upper() else ("COMPOUND" if "CP" in str(x).upper() else str(x))))
            if cat=="입고": df_f = df_f[df_f['구분']=='원자재']
            elif cat=="생산": df_f = df_f[df_f['구분'].isin(['제품','완제품'])]
            
            if not df_f.empty:
                grp = st.selectbox("1.그룹", sorted(df_f['Group'].unique()))
                df_step1 = df_f[df_f['Group']==grp]
                final = pd.DataFrame()
                if grp=="COMPOUND":
                    clr = st.selectbox("2.색상", sorted(df_step1['색상'].unique()))
                    final = df_step1[df_step1['색상']==clr]
                elif cat=="입고":
                    spc = st.selectbox("2.규격", sorted(df_step1['규격'].unique())) if len(df_step1['규격'].unique())>1 else None
                    final = df_step1[df_step1['규격']==spc] if spc else df_step1
                else:
                    typ = st.selectbox("2.타입", sorted(df_step1['타입'].unique()))
                    df_step2 = df_step1[df_step1['타입']==typ]
                    clr = st.selectbox("3.색상", sorted(df_step2['색상'].unique()))
                    df_step3 = df_step2[df_step2['색상']==clr]
                    spc = st.selectbox("4.규격", sorted(df_step3['규격'].unique()))
                    final = df_step3[df_step3['규격']==spc]
                
                if not final.empty:
                    item_info = final.iloc[0]; sel_code = item_info['코드']
                    st.success(f"선택: {sel_code}")
                    if cat=="재고실사" and not df_inventory.empty:
                        r = df_inventory[(df_inventory['공장']==factory)&(df_inventory['코드'].astype(str)==str(sel_code))]
                        if not r.empty: sys_q = safe_float(r.iloc[0]['현재고'])
                        st.info(f"전산: {sys_q}")
        
        qty_in = 0.0; note_in = ""
        if cat=="재고실사":
            real = st.number_input("실사값", value=float(sys_q))
            qty_in = real - sys_q
            note_in = f"[실사] {st.text_input('비고')}"
        else:
            qty_in = st.number_input("수량")
            note_in = st.text_input("비고")
            
        if st.button("저장"):
            if sheet_logs:
                try:
                    # [NEW] 저장 구조 변경: [..., 비고, 거래처(L), 라인(M)]
                    # 생산이므로 거래처는 "-", 라인은 prod_line 저장
                    sheet_logs.append_row([date.strftime('%Y-%m-%d'), time_str, factory, cat, sel_code, item_info['품목명'], item_info['규격'], item_info['타입'], item_info['색상'], qty_in, note_in, "-", prod_line])
                    chg = qty_in if cat in ["입고","생산","재고실사"] else -qty_in
                    update_inventory(factory, sel_code, chg, item_info['품목명'], item_info['규격'], item_info['타입'], item_info['색상'], item_info.get('단위','-'))
                    if cat=="생산" and not df_bom.empty:
                        for i,r in df_bom[df_bom['제품코드'].astype(str)==str(sel_code)].iterrows():
                            req = qty_in * safe_float(r['소요량'])
                            update_inventory(factory, r['자재코드'], -req)
                            time.sleep(0.5) 
                            # BOM 차감 시에도 라인 정보 기록
                            sheet_logs.append_row([date.strftime('%Y-%m-%d'), time_str, factory, "사용(Auto)", r['자재코드'], "System", "-", "-", "-", -req, f"{sel_code} 생산", "-", prod_line])
                    st.cache_data.clear(); st.success("완료"); st.rerun()
                except Exception as e: st.error(f"오류: {e}")

    st.title(f"📦 재고/생산 관리 ({factory})")
    
    t1, t2, t3, t4, t5 = st.tabs(["📦 재고 현황", "🏭 생산 기록(검색/인쇄)", "📜 전체 로그", "🔩 BOM", "📊 분석/실사"])
    
    with t1:
        if not df_inventory.empty:
            df_v = df_inventory.copy()
            if not df_items.empty:
                cmap = df_items.drop_duplicates('코드').set_index('코드')['구분'].to_dict()
                df_v['구분'] = df_v['코드'].map(cmap).fillna('-')
            c1, c2 = st.columns(2)
            fac_f = c1.radio("공장", ["전체", "1공장", "2공장"], horizontal=True)
            cat_f = c2.radio("품목", ["전체", "제품", "반제품", "원자재"], horizontal=True)
            if fac_f != "전체": df_v = df_v[df_v['공장']==fac_f]
            if cat_f != "전체": 
                if cat_f=="제품": df_v = df_v[df_v['구분'].isin(['제품','완제품'])]
                else: df_v = df_v[df_v['구분']==cat_f]
            st.dataframe(df_v, use_container_width=True)
    
    # [NEW] 생산 기록 검색 및 인쇄 기능
    with t2:
        st.subheader("🔍 생산 이력 검색 및 인쇄")
        if df_logs.empty:
            st.info("로그 데이터가 없습니다.")
        else:
            # 생산 데이터만 필터링
            df_prod_log = df_logs[df_logs['구분'] == '생산'].copy()
            
            # 컬럼 매핑 (M열이 라인)
            if len(df_prod_log.columns) >= 13:
                cols = list(df_prod_log.columns)
                cols[12] = '라인' # M열(인덱스 12)
                df_prod_log.columns = cols
            else:
                df_prod_log['라인'] = "-"

            # 문자열 변환
            for col in ['코드', '품목명', '라인']:
                if col in df_prod_log.columns:
                    df_prod_log[col] = df_prod_log[col].astype(str)

            with st.expander("🔎 검색 옵션 (클릭해서 열기)", expanded=True):
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

            st.write(f"📋 검색 결과: {len(df_res)}건")
            disp_cols = ['날짜', '시간', '공장', '라인', '코드', '품목명', '수량', '비고']
            final_cols = [c for c in disp_cols if c in df_res.columns]
            st.dataframe(df_res[final_cols].sort_values(['날짜', '시간'], ascending=False), use_container_width=True)
            total_prod = df_res['수량'].sum() if not df_res.empty else 0
            st.metric("총 생산량 (검색 결과)", f"{total_prod:,.0f} KG")

            if not df_res.empty:
                html_table = f"""<h2 style='text-align:center;'>생산 실적 기록서</h2><p style='text-align:center;'>기간: {sch_date[0]} ~ {sch_date[1] if len(sch_date)>1 else sch_date[0]} | 라인: {sch_line}</p><table style='width:100%; border-collapse: collapse; font-size: 12px; text-align: center;' border='1'><thead><tr style='background-color: #f2f2f2;'><th>날짜</th><th>시간</th><th>공장</th><th>라인</th><th>코드</th><th>품목명</th><th>수량(KG)</th><th>비고</th></tr></thead><tbody>"""
                for _, row in df_res.sort_values(['날짜', '시간']).iterrows():
                    line_val = row.get('라인', '-')
                    html_table += f"<tr><td>{row['날짜']}</td><td>{row['시간']}</td><td>{row['공장']}</td><td>{line_val}</td><td>{row['코드']}</td><td>{row['품목명']}</td><td style='text-align:right;'>{row['수량']:,.0f}</td><td>{row['비고']}</td></tr>"
                html_table += f"""</tbody><tfoot><tr style='font-weight:bold; background-color: #f2f2f2;'><td colspan='6'>합계</td><td style='text-align:right;'>{total_prod:,.0f}</td><td></td></tr></tfoot></table>"""
                st.components.v1.html(create_print_button(html_table, "Production Report"), height=50)

    with t3: st.dataframe(df_logs, use_container_width=True)
    with t4: st.dataframe(df_bom, use_container_width=True)
    with t5:
        st.header("📊 생산 분석 및 재고 실사 결과")
        if not df_logs.empty and '구분' in df_logs.columns:
            df_prod = df_logs[df_logs['구분'] == '생산'].copy()
            if not df_prod.empty:
                st.subheader("🏭 일별 생산량 추이")
                daily = df_prod.groupby('날짜')['수량'].sum().reset_index().sort_values('날짜')
                chart = alt.Chart(daily).mark_line(point=True).encode(x='날짜', y='수량', tooltip=['날짜', '수량']).properties(height=350).interactive()
                st.altair_chart(chart, use_container_width=True)
            else: st.info("생산 데이터가 없습니다.")
            st.markdown("---")
            st.subheader("📉 재고 실사 및 조정 내역")
            df_audit = df_logs[df_logs['구분'].isin(['재고실사', '재고조정'])].copy()
            if not df_audit.empty: st.dataframe(df_audit.tail(5).sort_index(ascending=False), use_container_width=True)
            else: st.info("재고 실사 기록이 없습니다.")

# [2] 영업/출고 관리
elif menu == "영업/출고 관리":
    st.title("📑 영업 주문 및 출고 관리")
    if sheet_orders is None: st.error("'Orders' 시트가 없습니다."); st.stop()
    
    tab_o, tab_p, tab_prt, tab_out = st.tabs(["📝 1. 주문 등록", "✏️ 2. 팔레트 수정/삭제", "🖨️ 3. 명세서/라벨 인쇄", "🚚 4. 출고 확정"])
    
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
        st.subheader("✏️ 팔레트 구성 수정 및 삭제")
        if not df_orders.empty and '상태' in df_orders.columns:
            pend = df_orders[df_orders['상태']=='준비']
            if not pend.empty:
                unique_ords = pend[['주문번호', '날짜', '거래처']].drop_duplicates().set_index('주문번호')
                order_dict = unique_ords.to_dict('index')
                def format_ord(ord_id):
                    info = order_dict.get(ord_id)
                    return f"{info['날짜']} | {info['거래처']} ({ord_id})" if info else ord_id

                tgt = st.selectbox("수정/삭제할 주문 선택", pend['주문번호'].unique(), format_func=format_ord)
                original_df = pend[pend['주문번호']==tgt].copy()
                if not df_items.empty:
                    code_to_type = df_items.set_index('코드')['타입'].to_dict()
                    original_df['타입'] = original_df['코드'].map(code_to_type).fillna('-')
                else: original_df['타입'] = "-"
                if 'LOT번호' not in original_df.columns: original_df['LOT번호'] = ""

                editor_cols = ['팔레트번호', '코드', '품목명', '타입', '수량', 'LOT번호', '비고']
                edited_df = st.data_editor(
                    original_df[editor_cols], num_rows="dynamic", key="pallet_editor", use_container_width=True, disabled=["타입"]
                )
                c_edit1, c_edit2 = st.columns([1, 1])
                with c_edit1:
                    if st.button("💾 수정사항 저장", type="primary"):
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
                                st.cache_data.clear(); st.success("수정 완료!"); time.sleep(2); st.rerun()
                            except Exception as e: st.error(f"오류: {e}")
                with c_edit2:
                    if st.button("🗑️ 이 주문 전체 삭제"):
                        with st.spinner("삭제 중..."):
                            try:
                                time.sleep(1)
                                all_records = sheet_orders.get_all_records()
                                remaining_data = [r for r in all_records if str(r['주문번호']) != str(tgt)]
                                headers = list(all_records[0].keys()) if all_records else ['주문번호', '날짜', '거래처', '코드', '품목명', '수량', '팔레트번호', '상태', '비고']
                                update_values = [headers]
                                for r in remaining_data: update_values.append([r.get(h, "") for h in headers])
                                sheet_orders.clear(); time.sleep(1); sheet_orders.update(update_values)
                                st.cache_data.clear(); st.success("삭제 완료!"); time.sleep(2); st.rerun()
                            except Exception as e: st.error(f"오류: {e}")
            else: st.info("대기 중인 주문이 없습니다.")

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
                if not dp.empty:
                    cli = dp.iloc[0]['거래처']
                    ex_date = dp.iloc[0]['날짜']
                    ship_date = datetime.datetime.now().strftime("%Y-%m-%d")
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown("### 📄 Packing List")
                        pl_rows = ""; tot_q = 0; tot_plt = dp['팔레트번호'].nunique()
                        for plt_num, group in dp.groupby('팔레트번호'):
                            g_len = len(group); is_first = True
                            for _, r in group.iterrows():
                                shp = get_shape(r['코드'], df_items)
                                rem = r['비고']
                                lot_no = r.get('LOT번호', '')
                                clr = "-"
                                if not df_items.empty:
                                    inf = df_items[df_items['코드'].astype(str)==str(r['코드'])]
                                    if not inf.empty: clr = inf.iloc[0]['색상']
                                pl_rows += "<tr>"
                                if is_first: pl_rows += f"<td rowspan='{g_len}'>{plt_num}</td>"
                                pl_rows += f"<td>{r['코드']}</td><td align='right'>{r['수량']:,.0f}</td><td align='center'>{clr}</td><td align='center'>{shp}</td><td align='center'>{lot_no}</td><td align='center'>{rem}</td></tr>"
                                is_first = False; tot_q += r['수량']
                        html_pl = f"""<div style="padding:20px; font-family: 'Arial', sans-serif; font-size:12px;"><h2 style="text-align:center;">PACKING LIST</h2><table style="width:100%; margin-bottom:10px;"><tr><td><b>EX-FACTORY</b></td><td>: {ex_date}</td></tr><tr><td><b>SHIP DATE</b></td><td>: {ship_date}</td></tr><tr><td><b>CUSTOMER(BUYER)</b></td><td>: {cli}</td></tr></table><table style="width:100%; border-collapse: collapse; text-align:center;" border="1"><thead style="background-color:#eee;"><tr><th>PLT</th><th>ITEM NAME</th><th>Q'TY</th><th>COLOR</th><th>SHAPE</th><th>LOT#</th><th>REMARK</th></tr></thead><tbody>{pl_rows}</tbody><tfoot><tr style="font-weight:bold; background-color:#eee;"><td colspan="2">{tot_plt} PLTS</td><td align='right'>{tot_q:,.0f}</td><td colspan="4"></td></tr></tfoot></table></div>"""
                        btn_html = create_print_button(html_pl, "Packing List", "landscape")
                        st.components.v1.html(btn_html, height=50)
                        st.components.v1.html(html_pl, height=500, scrolling=True)

                    with c2:
                        st.markdown("### 🏷️ 라벨 선택 인쇄")
                        with st.expander("🔷 다이아몬드 라벨 (기존)", expanded=True):
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
                            btn_lbl_d = create_print_button(labels_html_diamond, "Diamond Labels", "landscape")
                            st.components.v1.html(btn_lbl_d, height=50)
                            preview_diamond = labels_html_diamond.replace('width="100%" height="100%"', 'width="100%" height="250px"')
                            st.caption("▼ 미리보기")
                            st.components.v1.html(preview_diamond, height=300, scrolling=True)

                        with st.expander("📄 표준 텍스트 라벨 (신규)", expanded=True):
                            labels_html_text = ""
                            for plt_num, group in dp.groupby('팔레트번호'):
                                p_qty = group['수량'].sum()
                                p_code = group.iloc[0]['코드']
                                label_div = f"""
                                <div class="page-break" style="border: none; width: 100%; height: 95vh; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; font-family: 'Times New Roman', serif; font-weight: bold; padding: 10px; box-sizing: border-box;">
                                    <div style="font-size: 50px; text-transform: uppercase; width:100%; margin-bottom: 40px;">{cli}</div>
                                    <div style="width: 100%; display: flex; justify-content: center; gap: 100px; font-size: 50px; margin-bottom: 40px;"><span>{p_code}</span><span>{p_qty:,.0f}KG</span></div>
                                    <div style="font-size: 45px; width: 100%; line-height: 1.6;"><div>&lt;PLASTIC ABRASIVE MEDIA&gt;</div><div>PLT # : {plt_num}/{tot_plt}</div><div>TOTAL : {p_qty:,.0f} KG</div></div>
                                </div>
                                """
                                labels_html_text += label_div
                            btn_lbl_t = create_print_button(labels_html_text, "Standard Labels", "landscape")
                            st.components.v1.html(btn_lbl_t, height=50)
                            preview_text = labels_html_text.replace('height: 95vh;', 'height: 300px; border: 1px dashed #ccc; margin-bottom: 20px;').replace('font-size: 50px;', 'font-size: 20px;').replace('font-size: 45px;', 'font-size: 18px;')
                            st.caption("▼ 미리보기")
                            st.components.v1.html(preview_text, height=400, scrolling=True)

    with tab_out:
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
                                # [NEW] 출고 확정 시: 거래처(L열)에는 거래처명, 라인(M열)에는 "-"
                                sheet_logs.append_row([date.strftime('%Y-%m-%d'), time_str, factory, "출고", row['코드'], p_nm, p_sp, p_ty, p_co, -safe_float(row['수량']), f"주문출고({tgt_out})", cli, "-"])
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

# [4] 현장 작업 (LOT 입력)
elif menu == "🏭 현장 작업 (LOT 입력)":
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

# [5] 이력/LOT 검색
elif menu == "🔍 이력/LOT 검색":
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
