import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

# --- [0. 화면 및 스타일 설정 (사진과 동일하게)] ---
st.set_page_config(page_title="TQQQ VR 5.0 Final", layout="wide")
st.markdown("""
    <style>
        .block-container {padding-top: 1rem; padding-bottom: 2rem;}
        
        /* 테이블 스타일 정의 */
        .vr-table {
            width: 100%;
            border-collapse: collapse;
            font-family: 'Arial', sans-serif;
            text-align: center;
        }
        .vr-table th, .vr-table td {
            border: 1px solid #ddd;
            padding: 8px;
            font-size: 14px;
        }
        
        /* 헤더 스타일 (매수점/매도점) */
        .header-title {
            font-size: 32px;
            font-weight: bold;
            text-align: center;
            margin-bottom: 10px;
            background-color: #dbeaff; /* 연한 파랑 배경 */
            padding: 10px;
            border: 2px solid #b0c4de;
            border-radius: 5px;
        }

        /* 노란색 강조 헤더 (최소값, 잔여개수, Pool) */
        .yellow-header {
            background-color: #ffff00;
            font-weight: bold;
            color: black;
        }
        
        /* 일반 헤더 */
        .gray-header {
            background-color: #f0f0f0;
            font-weight: bold;
        }

        /* 매수/매도 가격 텍스트 색상 */
        .price-text-buy { color: #ff0000; font-weight: bold; } /* 빨강 */
        .price-text-sell { color: #0000ff; font-weight: bold; } /* 파랑 */

        /* 좌측 라벨 컬럼 */
        .label-col {
            background-color: #f9f9f9;
            font-weight: bold;
            vertical-align: middle;
            width: 20%;
        }
    </style>
""", unsafe_allow_html=True)

# --- [1. 데이터 가져오기] ---
@st.cache_data(ttl=300)
def get_market_data():
    data = {"price": 0.0, "fx": 1450.0}
    try:
        t = yf.Ticker("TQQQ").history(period="1d")
        if not t.empty: data["price"] = round(t['Close'].iloc[-1], 2)
        f = yf.Ticker("USDKRW=X").history(period="1d")
        if not f.empty: data["fx"] = round(f['Close'].iloc[-1], 2)
    except: pass
    return data

m = get_market_data()

# --- [2. 사이드바 설정] ---
with st.sidebar:
    st.header("⚙️ VR 5.0 설정")
    
    # 자금 관리 모드
    invest_type = st.radio(
        "투자 성향", 
        ["적립식 (Pool 75%)", "거치식 (Pool 50%)", "인출식 (Pool 25%)"]
    )
    if "적립식" in invest_type: pool_cap = 0.75
    elif "거치식" in invest_type: pool_cap = 0.50
    else: pool_cap = 0.25

    c1, c2 = st.columns(2)
    with c1: g_val = st.number_input("기울기(G)", value=10, min_value=1)
    with c2: b_pct = st.number_input("밴드폭(%)", value=15) / 100.0
    
    st.divider()
    
    # 구글 시트 연동
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = pd.DataFrame()
    last_v, last_pool, last_princ = 0.0, 0.0, 0.0
    
    try:
        df = conn.read(worksheet="Sheet1", ttl=0)
        if not df.empty:
            row = df.iloc[-1]
            def safe_float(x):
                try: return float(str(x).replace(',',''))
                except: return 0.0
            last_v = safe_float(row.get("V_old", 0))
            last_pool = safe_float(row.get("Pool", 0))
            last_princ = safe_float(row.get("Principal", 0))
    except: pass

    mode = st.radio("작업 선택", ["사이클 업데이트", "최초 시작"], horizontal=True)
    curr_p = st.number_input("TQQQ 현재가 ($)", value=m["price"], format="%.2f")
    curr_fx = st.number_input("현재 환율 (원)", value=m["fx"])
    qty = st.number_input("현재 보유 수량 (주)", value=0)
    
    final_pool, v_final, princ_final, growth, add_usd = 0.0, 0.0, 0.0, 0.0, 0.0

    if mode == "최초 시작":
        princ_final = st.number_input("총 원금 ($)", value=5000.0)
        qty_init = int((princ_final * 0.5) / curr_p) if curr_p > 0 else 0
        final_pool = princ_final - (qty_init * curr_p)
        v_final = curr_p * qty_init
        qty = qty_init 
    else:
        base_pool = st.number_input("기존 계좌 현금 ($)", value=last_pool)
        add_usd = st.number_input("신규 입금액 ($)", value=0.0)
        final_pool = base_pool + add_usd
        princ_final = last_princ + add_usd
        if final_pool > 0: growth = final_pool / g_val
        v_final = last_v + growth + add_usd 

    if st.button("💾 데이터 저장"):
        new_row = pd.DataFrame([{"Date": datetime.now().strftime('%Y-%m-%d'), "Qty": qty, "Pool": final_pool, "V_old": v_final, "Principal": princ_final, "Price": curr_p, "Band": int(b_pct*100)}])
        final_df = pd.concat([df, new_row], ignore_index=True) if not df.empty else new_row
        conn.update(worksheet="Sheet1", data=final_df.fillna(0))
        st.success("저장 완료")
        st.rerun()

# --- [3. 메인 화면 - 매수/매도 테이블 생성 로직] ---
if curr_p <= 0: st.stop()

# 기본 계산
eval_usd = curr_p * qty
total_usd = eval_usd + final_pool
min_val = v_final * (1 - b_pct)  # 밴드 하단 (최소값)
max_val = v_final * (1 + b_pct)  # 밴드 상단 (최대값)

# [매수 테이블 데이터 생성]
buy_limit = final_pool * pool_cap # 사용 가능 예산
# 예산으로 살 수 있는 총 수량을 계산 후, 10단계로 리스팅 (사진처럼 촘촘하게)
total_buy_qty = int(buy_limit / (curr_p * 0.9)) if curr_p > 0 else 0
step_qty = max(1, int(total_buy_qty / 10)) # 사진처럼 '3개씩' 등 일정한 간격

buy_rows = ""
current_buy_pool = final_pool
current_buy_qty = qty
for i in range(10): # 10줄 출력
    target_p = curr_p * (1 - (0.015 * (i+1))) # -1.5%씩 하락하는 가격 가정
    cost = target_p * step_qty
    if current_buy_pool >= cost:
        current_buy_qty += step_qty
        current_buy_pool -= cost
        buy_rows += f"""
        <tr>
            <td>{current_buy_qty}</td>
            <td class="price-text-buy">{target_p:.2f}</td>
            <td>{current_buy_pool:,.2f}</td>
        </tr>
        """

# [매도 테이블 데이터 생성]
sell_rows = ""
current_sell_pool = final_pool
current_sell_qty = qty
sell_step = max(1, int(qty / 10)) # 보유량의 1/10씩 매도
for i in range(10):
    if current_sell_qty >= sell_step:
        target_p = curr_p * (1 + (0.015 * (i+1))) # +1.5%씩 상승하는 가격
        revenue = target_p * sell_step
        current_sell_qty -= sell_step
        current_sell_pool += revenue
        sell_rows += f"""
        <tr>
            <td>{current_sell_qty}</td>
            <td class="price-text-sell">{target_p:.2f}</td>
            <td>{current_sell_pool:,.2f}</td>
        </tr>
        """

# --- [4. HTML 테이블 렌더링] ---
st.title("📊 TQQQ VR 5.0 Dashboard")

c1, c2 = st.columns(2)

# [왼쪽: 매수점 테이블] (사진과 동일 구조)
with c1:
    st.markdown(f"""
    <div class="header-title">매 수 점</div>
    <table class="vr-table">
        <thead>
            <tr>
                <th class="gray-header">최소값</th>
                <th class="gray-header">잔여개수</th>
                <th class="gray-header">매수점</th>
                <th class="gray-header">Pool</th>
            </tr>
            <tr class="yellow-header">
                <td>{min_val:,.2f}</td>
                <td>{qty}</td>
                <td></td>
                <td>{final_pool:,.2f}</td>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td rowspan="10" class="label-col">
                    {step_qty}개씩<br>
                    지정가매수<br>
                    잔량주문
                </td>
                {buy_rows.split('</tr>')[0] + '</tr>'} 
            </tr>
            {''.join(buy_rows.split('</tr>')[1:])}
        </tbody>
    </table>
    """, unsafe_allow_html=True)

# [오른쪽: 매도점 테이블] (사진과 동일 구조)
with c2:
    st.markdown(f"""
    <div class="header-title">매 도 점</div>
    <table class="vr-table">
        <thead>
            <tr>
                <th class="gray-header">최대값</th>
                <th class="gray-header">잔여개수</th>
                <th class="gray-header">매도점</th>
                <th class="gray-header">Pool</th>
            </tr>
            <tr class="yellow-header">
                <td>{max_val:,.2f}</td>
                <td>{qty}</td>
                <td></td>
                <td>{final_pool:,.2f}</td>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td rowspan="10" class="label-col">
                    {sell_step}개씩<br>
                    지정가매도<br>
                    잔량주문
                </td>
                {sell_rows.split('</tr>')[0] + '</tr>'}
            </tr>
            {''.join(sell_rows.split('</tr>')[1:])}
        </tbody>
    </table>
    """, unsafe_allow_html=True)

# --- [하단: 운용 팁] ---
st.markdown("---")
st.info(f"""
💡 **운용 가이드:** 위 표는 사용자님의 자금 상황(Pool 한도 {int(pool_cap*100)}%)에 맞춰 계산되었습니다.
* **매수:** 주가가 떨어질 때마다 **{step_qty}주씩** 더 사지도록 예약하세요.
* **매도:** 주가가 오를 때마다 **{sell_step}주씩** 팔리도록 예약하세요.
""")
