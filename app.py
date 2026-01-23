import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
from streamlit_gsheets import GSheetsConnection

# --- [0. 화면 설정 및 CSS] ---
st.set_page_config(page_title="TQQQ VR 5.0 Official", layout="wide")
st.markdown("""
    <style>
        .block-container {padding-top: 1.5rem; padding-bottom: 1rem;}
        div[data-testid="stMetricValue"] {font-size: 1.5rem !important; font-weight: 700;}
        .manual-section { background-color: #f8f9fa; padding: 20px; border-radius: 10px; border: 1px solid #dee2e6; margin-bottom: 20px; color: #000; }
        .tip-box { background-color: #fff9db; padding: 15px; border-radius: 10px; border-left: 6px solid #fab005; color: #000; font-weight: 500; }
    </style>
""", unsafe_allow_html=True)

# --- [1. 텔레그램 전송 함수 (사용자 원본 방식)] ---
def send_telegram_msg(msg):
    try:
        token = st.secrets["telegram"]["bot_token"]
        chat_id = st.secrets["telegram"]["chat_id"]
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}
        requests.post(url, data=data)
        st.toast("✅ 텔레그램 전송 완료!", icon="✈️")
    except:
        st.error("텔레그램 전송 실패: secrets 설정을 확인하세요.")

# --- [2. 데이터 가져오기] ---
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

# --- [3. 사이드바: 데이터 입력 및 저장] ---
with st.sidebar:
    st.header("📊 VR 5.0 전략 설정")
    invest_type = st.radio("투자 성향", ["적립식 (Pool 75% 사용)", "거치식 (Pool 50% 사용)", "인출식 (Pool 25% 사용)"])
    pool_cap = 0.75 if "적립" in invest_type else (0.50 if "거치" in invest_type else 0.25)
    
    c1, c2 = st.columns(2)
    g_val = c1.number_input("기울기(G)", value=10, min_value=1)
    b_pct = c2.number_input("밴드폭(%)", value=15) / 100.0
    
    st.divider()
    
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = pd.DataFrame()
    last_v, last_pool, last_princ = 0.0, 0.0, 0.0
    
    try:
        df = conn.read(worksheet="Sheet1", ttl=0)
        if not df.empty:
            row = df.iloc[-1]
            last_v = float(str(row.get("V_old", 0)).replace(',',''))
            last_pool = float(str(row.get("Pool", 0)).replace(',',''))
            last_princ = float(str(row.get("Principal", 0)).replace(',',''))
    except: pass

    mode = st.radio("작업 선택", ["사이클 업데이트", "최초 시작"], horizontal=True)
    curr_p = st.number_input("TQQQ 현재가 ($)", value=m["price"], format="%.2f")
    
    if mode == "최초 시작":
        princ_final = st.number_input("총 원금 ($)", value=5000.0)
        qty = int((princ_final * 0.5) / curr_p) if curr_p > 0 else 0
        final_pool = princ_final - (qty * curr_p)
        v_final = curr_p * qty
    else:
        qty = st.number_input("현재 보유 수량 (주)", value=0)
        base_pool = st.number_input("기존 계좌 잔고 ($)", value=last_pool)
        add_usd = st.number_input("신규 입금액 ($)", value=0.0)
        final_pool = base_pool + add_usd
        princ_final = last_princ + add_usd
        v_final = last_v + (final_pool / g_val) + add_usd if final_pool > 0 else last_v + add_usd

    if st.button("💾 이 사이클 데이터 저장", use_container_width=True):
        new_row = pd.DataFrame([{"Date": datetime.now().strftime('%Y-%m-%d'), "Qty": qty, "Pool": final_pool, "V_old": v_final, "Principal": princ_final, "Price": curr_p, "Band": int(b_pct*100)}])
        conn.update(worksheet="Sheet1", data=pd.concat([df, new_row], ignore_index=True).fillna(0))
        st.success("구글 시트 저장 완료!")
        st.rerun()

# --- [4. 매매 가이드 계산] ---
if curr_p <= 0: st.stop()
eval_usd = curr_p * qty
total_usd = eval_usd + final_pool
min_val, max_val = v_final * (1 - b_pct), v_final * (1 + b_pct)
start_sell_p = max_val / qty if qty > 0 else 0
base_sell_p = max(curr_p, start_sell_p)

# 매수 가이드 (균등)
buy_guide, b_limit = [], final_pool * pool_cap
for i in range(10):
    p = curr_p * (1 - (0.015 * (i+1)))
    q = int((b_limit/10)/p)
    if q >= 1: buy_guide.append({"매수가격": f"${p:.2f}", "수량": f"{q}주"})

# 매도 가이드 (피라미드)
sell_guide, weights = [], [1, 1, 2, 2, 3, 3, 4, 4, 5, 5]
unit = qty / sum(weights) if qty > 0 else 0
for i in range(10):
    q = max(1, int(unit * weights[i]))
    if qty >= q:
        p = base_sell_p * (1 + (0.015 * i))
        sell_guide.append({"매도가격": f"${p:.2f}", "수량": f"🔻{q}주"})

# --- [5. 메인 대시보드 출력] ---
st.title("🚀 TQQQ VR 5.0 Dashboard")
c1, c2, c3, c4 = st.columns(4)
c1.metric("목표 가치 (V)", f"${v_final:,.0f}")
c2.metric("총 자산 (E+P)", f"${total_usd:,.0f}")
c3.metric("가용 현금 (Pool)", f"${final_pool:,.0f}")
c4.metric("수익률", f"{( (total_usd - princ_final)/princ_final*100 if princ_final > 0 else 0):.2f}%")

tab1, tab2, tab3 = st.tabs(["📋 매매 가이드", "📈 성장 히스토리", "📖 운용 매뉴얼"])

with tab1:
    col_buy, col_sell = st.columns(2)
    with col_buy:
        if st.button("✈️ 매수 가이드 전송"):
            send_telegram_msg(f"🔵 [VR 5.0 매수]\n" + "\n".join([f"{d['매수가격']} / {d['수량']}" for d in buy_guide[:5]]))
        st.markdown(f'<div class="metric-box"><span class="header-text">📉 매수 밴드(하단): ${min_val:,.2f}</span></div>', unsafe_allow_html=True)
        st.table(pd.DataFrame(buy_guide))
    with col_sell:
        if st.button("✈️ 매도 가이드 전송"):
            send_telegram_msg(f"🔴 [VR 5.0 매도]\n상단가: ${start_sell_p:,.2f}\n" + "\n".join([f"{d['매도가격']} / {d['수량']}" for d in sell_guide[:5]]))
        st.markdown(f'<div class="metric-box"><span class="header-text">📈 매도 시작가(상단): ${start_sell_p:,.2f}</span></div>', unsafe_allow_html=True)
        st.table(pd.DataFrame(sell_guide))

with tab2:
    if not df.empty:
        df_p = df.copy()
        df_p['Date'] = pd.to_datetime(df_p['Date'])
        df_p["상단"] = df_p["V_old"] * (1 + b_pct); df_p["하단"] = df_p["V_old"] * (1 - b_pct); df_p["자산"] = df_p["Qty"] * df_p["Price"]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_p['Date'], y=df_p['상단'], line=dict(color='green', width=1), name='매도 한계'))
        fig.add_trace(go.Scatter(x=df_p['Date'], y=df_p['하단'], line=dict(color='green', width=1), fill='tonexty', fillcolor='rgba(0, 255, 0, 0.05)', name='안전 밴드(V)'))
        fig.add_trace(go.Scatter(x=df_p['Date'], y=df_p['V_old'], line=dict(color='#00BFFF', dash='dot'), name='목표 가치'))
        fig.add_trace(go.Scatter(x=df_p['Date'], y=df_p['자산'], line=dict(color='#FFFF00', width=3), name='내 자산(E)'))
        st.plotly_chart(fig, use_container_width=True)

# --- [6. 운용 매뉴얼 (4단계 원칙 준수)] ---
with tab3:
    st.header("1. 전제 조건 및 배경 설명")
    st.markdown("""
    <div class="manual-section">
    <b>과목 성격:</b> 변동성을 이용해 자산 가치($V$)를 우상향시키는 기계적 리밸런싱 시스템<br>
    <b>전제 조건:</b> 2주 단위 사이클 준수 및 지정가 잔량 주문 활용 능력<br>
    <b>학습 목표:</b> 장중 차트 확인 없이 '그물 매수'와 '피라미드 매도'로 수익 확정
    </div>
    """, unsafe_allow_html=True)

    st.header("2. 핵심 이론 분석 (Vs)")
    st.markdown("##### ▣ 사이클 운영 비교")
    st.markdown("""
    | 구분 | 최초 시작 | 사이클 업데이트 |
    | :--- | :--- | :--- |
    | **자산 비중** | 주식 50 : 현금 50 고정 | $V$ 성장 공식 + 신규 입금 반영 |
    | **동작** | 즉시 수량 매수 후 저장 | 2주 기간 예약 주문 세팅 |
    """)
    st.markdown("##### ▣ 매매 전략 비교")
    st.markdown("""
    | 비교 항목 | 매수 그물 (Buy Grid) | 매도 피라미드 (Sell Pyramid) |
    | :--- | :--- | :--- |
    | **기준 가격** | 현재가 대비 하락 시 | 밴드 상단 도달 시 |
    | **수량 배정** | 10단계 균등 자금 투입 | 위로 갈수록 대량 매도 (가중치) |
    | **핵심 목표** | 평단가 방어 및 주식 수 확보 | 수익 극대화 및 Pool 확보 |
    """)

    st.header("3. '결정적' 구별 포인트 (Tip)")
    st.markdown("""
    <div class="tip-box">
    <b>💡 실전 운용 핵심:</b><br>
    - <b>저장 후 전송:</b> 사이드바에서 [저장]을 완료한 뒤에 메인 화면의 [전송] 버튼을 누르세요.<br>
    - <b>지정가 잔량 주문:</b> 2주 동안 주가가 해당 가격에 닿을 때만 체결되도록 '잔량유지' 옵션을 반드시 켭니다.<br>
    - <b>무대응 구간:</b> 자산(노란색 선)이 초록색 안전 밴드 안에 있다면 아무것도 하지 않아도 됩니다.
    </div>
    """, unsafe_allow_html=True)
