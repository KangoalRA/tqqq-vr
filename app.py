import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
from streamlit_gsheets import GSheetsConnection

# --- [0. 화면 설정 및 CSS (사용자 선호 스타일)] ---
st.set_page_config(page_title="TQQQ VR 5.0 Official", layout="wide")
st.markdown("""
    <style>
        .block-container {padding-top: 1.5rem; padding-bottom: 1rem;}
        div[data-testid="stMetricValue"] {font-size: 1.5rem !important; font-weight: 700;}
        .manual-section { background-color: rgba(0, 191, 255, 0.05); padding: 18px; border-radius: 10px; border-left: 6px solid #00BFFF; margin-bottom: 20px; color: #000; }
        .tip-box { background-color: rgba(255, 255, 0, 0.05); padding: 18px; border-radius: 10px; border-left: 6px solid #FFFF00; color: #000; }
        .buy-signal { background-color: rgba(0, 255, 0, 0.1); padding: 15px; border-radius: 10px; border: 1px solid #00FF00; color: #00FF00; font-weight: bold; font-size: 1.2rem; text-align: center;}
        .metric-box { background-color: #ffffff; border-left: 8px solid #ffcc00; padding: 15px; border-radius: 10px; margin-bottom: 15px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); color: #000; }
        .header-text { font-size: 1.2rem; font-weight: 800; color: #000 !important; }
    </style>
""", unsafe_allow_html=True)

# --- [1. 텔레그램 전송 함수] ---
def send_telegram_msg(msg):
    try:
        token = st.secrets["telegram"]["bot_token"]
        chat_id = st.secrets["telegram"]["chat_id"]
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}
        requests.post(url, data=data)
        st.toast("✅ 전송 완료!", icon="✈️")
    except:
        st.error("텔레그램 전송 실패: secrets를 확인하세요.")

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
    invest_type = st.radio("투자 성향", ["적립식 (Pool 75% 사용)", "거치식 (Pool 50% 사용)"])
    pool_cap = 0.75 if "적립" in invest_type else 0.50
    
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
        princ_final = st.number_input("나의 총 투입 원금 ($)", value=5000.0)
        qty = int((princ_final * 0.5) / curr_p) if curr_p > 0 else 0
        final_pool = princ_final - (qty * curr_p)
        v_final = curr_p * qty
        st.markdown(f'<div class="buy-signal">💡 즉시 {qty}주 매수하세요!</div>', unsafe_allow_html=True)
    else:
        qty = st.number_input("현재 보유 수량 (주)", value=0)
        base_pool = st.number_input("기존 계좌 잔고 ($)", value=last_pool)
        add_usd = st.number_input("이번 주기 신규 입금액 ($)", value=0.0)
        final_pool = base_pool + add_usd
        princ_final = last_princ + add_usd
        v_final = last_v + (final_pool / g_val) + add_usd if final_pool > 0 else last_v + add_usd

    if st.button("💾 데이터 저장 (Save)", use_container_width=True):
        new_row = pd.DataFrame([{"Date": datetime.now().strftime('%Y-%m-%d'), "Qty": qty, "Pool": final_pool, "V_old": v_final, "Principal": princ_final, "Price": curr_p, "Band": int(b_pct*100)}])
        conn.update(worksheet="Sheet1", data=pd.concat([df, new_row], ignore_index=True).fillna(0))
        st.success("저장 완료!")
        st.rerun()

# --- [4. 매매 가이드 계산] ---
if curr_p <= 0: st.stop()
eval_usd, total_usd = curr_p * qty, (curr_p * qty) + final_pool
min_val, max_val = v_final * (1 - b_pct), v_final * (1 + b_pct)
start_sell_p = max_val / qty if qty > 0 else 0
base_sell_p = max(curr_p, start_sell_p)

# 매수 가이드
buy_guide, b_limit = [], final_pool * pool_cap
for i in range(10):
    p = curr_p * (1 - (0.015 * (i+1)))
    q = int((b_limit/10)/p)
    if q >= 1: buy_guide.append({"가격": f"${p:.2f}", "수량": f"{q}주"})

# 매도 가이드 (피라미드)
sell_guide, weights = [], [1, 1, 2, 2, 3, 3, 4, 4, 5, 5]
unit = qty / sum(weights) if qty > 0 else 0
for i in range(10):
    q = max(1, int(unit * weights[i]))
    if qty >= q:
        p = base_sell_p * (1 + (0.015 * i))
        sell_guide.append({"가격": f"${p:.2f}", "수량": f"🔻{q}주"})

# --- [5. 메인 대시보드 출력] ---
st.title("🚀 TQQQ VR 5.0 Dashboard")
c1, c2, c3, c4 = st.columns(4)
c1.metric("목표 가치 (V)", f"${v_final:,.0f}")
c2.metric("총 자산 (E+P)", f"${total_usd:,.0f}")
c3.metric("최종 현금 (Pool)", f"${final_pool:,.0f}")
c4.metric("수익률", f"{((total_usd - princ_final)/princ_final*100 if princ_final > 0 else 0):.2f}%")

tab1, tab2, tab3 = st.tabs(["📋 매매 가이드", "📈 성장 히스토리", "📖 운용 매뉴얼"])

with tab1:
    col_buy, col_sell = st.columns(2)
    with col_buy:
        if st.button("✈️ 매수 가이드 텔레그램 전송", use_container_width=True):
            send_telegram_msg(f"🔵 [VR 5.0 매수]\n" + "\n".join([f"{d['가격']} / {d['수량']}" for d in buy_guide[:5]]))
        st.markdown(f'<div class="metric-box"><span class="header-text">📉 매수 밴드(하단): ${min_val:,.2f}</span></div>', unsafe_allow_html=True)
        st.table(pd.DataFrame(buy_guide))
    with col_sell:
        if st.button("✈️ 매도 가이드 텔레그램 전송", use_container_width=True):
            send_telegram_msg(f"🔴 [VR 5.0 매도]\n시작가: ${start_sell_p:,.2f}\n" + "\n".join([f"{d['가격']} / {d['수량']}" for d in sell_guide[:5]]))
        st.markdown(f'<div class="metric-box"><span class="header-text">📈 매도 시작가(상단): ${start_sell_p:,.2f}</span></div>', unsafe_allow_html=True)
        st.table(pd.DataFrame(sell_guide))

with tab2:
    if not df.empty:
        df_p = df.copy()
        df_p['Date'] = pd.to_datetime(df_p['Date'])
        df_p["상단"] = df_p["V_old"] * (1 + b_pct); df_p["하단"] = df_p["V_old"] * (1 - b_pct); df_p["자산"] = df_p["Qty"] * df_p["Price"]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_p['Date'], y=df_p['상단'], line=dict(color='green', width=1.5), name='매도 밴드'))
        fig.add_trace(go.Scatter(x=df_p['Date'], y=df_p['하단'], line=dict(color='green', width=1.5), fill='tonexty', fillcolor='rgba(0, 255, 0, 0.05)', name='매수 밴드'))
        fig.add_trace(go.Scatter(x=df_p['Date'], y=df_p['V_old'], line=dict(color='#00BFFF', dash='dot'), name='목표 가치(V)'))
        fig.add_trace(go.Scatter(x=df_p['Date'], y=df_p['자산'], line=dict(color='#FFFF00', width=3), name='내 자산(E)'))
        fig.update_layout(height=500, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig, use_container_width=True)

# --- [6. 운용 매뉴얼 (사용자 요청 원복)] ---
with tab3:
    st.markdown("### 📖 TQQQ VR 5.0 실전 운용 매뉴얼")
    
    with st.container():
        st.markdown('<div class="manual-section">', unsafe_allow_html=True)
        st.markdown("#### 1️⃣ 최초 시작 (Setting Up)")
        st.markdown("""
        * **자산 분배:** 총 원금의 **50%는 주식**을 즉시 매수하고, **50%는 현금**으로 남겨둡니다.
        * **저장:** 매수한 수량과 남은 현금이 확인되면 '데이터 저장'을 누르세요.
        """)
        st.markdown('</div>', unsafe_allow_html=True)

    with st.container():
        st.markdown('<div class="manual-section">', unsafe_allow_html=True)
        st.markdown("#### 2️⃣ 사이클 업데이트 및 예약 주문 (중요)")
        st.markdown("""
        * **주기:** 2주에 한 번 업데이트합니다.
        * **주문 방식:** LOC가 아닌 **[지정가 예약 주문]**을 사용합니다.
        * **설정 방법:** 1. 증권사 앱의 '예약주문' 메뉴에서 **기간을 2주로 설정**합니다.
            2. 주문 유형은 **'지정가'**, 조건은 **'잔량'**으로 선택합니다.
            3. 가이드의 1~5차 가격에 각각의 **[총 수량]**을 예약합니다.
        * **원리:** 2주 동안 주가가 해당 가격에 닿을 때만 총 수량이 채워질 때까지 자동으로 사집니다.
        """)
        st.markdown('</div>', unsafe_allow_html=True)

    with st.container():
        st.markdown('<div class="tip-box">', unsafe_allow_html=True)
        st.markdown("#### 💡 핵심 필승 규칙")
        st.markdown("""
        - **지정가 잔량 주문:** 매일 주문을 넣을 필요가 없습니다. 한 번만 예약하면 2주간 알아서 작동합니다.
        - **본업 집중:** 2주에 한 번만 앱을 켜고 주문을 넣으면 끝입니다. 장중에 차트를 보지 마세요.
        """)
        st.markdown('</div>', unsafe_allow_html=True)
