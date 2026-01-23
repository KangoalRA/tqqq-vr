import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime
try:
    from streamlit_gsheets import GSheetsConnection
    gsheets_available = True
except ImportError:
    gsheets_available = False
import requests

# --- [0. 화면 설정 및 CSS] ---
st.set_page_config(page_title="TQQQ VR 5.0 Final", layout="wide")
st.markdown("""
    <style>
        .block-container {padding-top: 1rem; padding-bottom: 2rem;}
        .metric-box {
            background-color: #ffffff;
            border-left: 6px solid #ffcc00; 
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 15px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.2);
        }
        .header-text { font-size: 1.3rem; font-weight: 900; color: #000 !important; display: block; }
        .sub-text { font-size: 1.0rem; color: #222 !important; font-weight: 600; }
    </style>
""", unsafe_allow_html=True)

# --- [1. 텔레그램 전송 함수] ---
def send_telegram_msg(token, chat_id, message):
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        params = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
        requests.get(url, params=params)
    except:
        st.error("텔레그램 전송 실패! 토큰과 ID를 확인하세요.")

# --- [2. 데이터 가져오기] ---
@st.cache_data(ttl=300)
def get_market_data():
    data = {"price": 50.0, "fx": 1450.0}
    try:
        t = yf.Ticker("TQQQ").history(period="1d")
        if not t.empty: data["price"] = round(t['Close'].iloc[-1], 2)
        f = yf.Ticker("USDKRW=X").history(period="1d")
        if not f.empty: data["fx"] = round(f['Close'].iloc[-1], 2)
    except: pass
    return data

m = get_market_data()

# --- [3. 사이드바 및 설정] ---
with st.sidebar:
    st.header("⚙️ VR 5.0 설정")
    
    # 텔레그램 설정 추가
    st.subheader("🔔 알림 설정")
    bot_token = st.text_input("Telegram Bot Token", type="password")
    chat_id = st.text_input("Telegram Chat ID")
    
    st.divider()
    
    invest_type = st.radio("투자 성향", ["적립식 (Pool 75%)", "거치식 (Pool 50%)", "인출식 (Pool 25%)"])
    pool_cap = 0.75 if "적립식" in invest_type else (0.50 if "거치식" in invest_type else 0.25)

    c1, c2 = st.columns(2)
    with c1: g_val = st.number_input("기울기(G)", value=10, min_value=1)
    with c2: b_pct = st.number_input("밴드폭(%)", value=15) / 100.0
    
    conn = None
    if gsheets_available:
        try: conn = st.connection("gsheets", type=GSheetsConnection)
        except: pass

    df = pd.DataFrame()
    last_v, last_pool, last_princ = 0.0, 0.0, 0.0
    if conn:
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
    qty = st.number_input("현재 보유 수량 (주)", value=0)
    
    # 계산 로직
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
        v_final = last_v + (final_pool / g_val) + add_usd if final_pool > 0 else last_v + add_usd

# --- [4. 메인 화면 및 매매표 생성] ---
min_val = v_final * (1 - b_pct)
max_val = v_final * (1 + b_pct)

# 매수표 생성
buy_limit = final_pool * pool_cap
step_buy_qty = max(1, int(int(buy_limit / (curr_p * 0.9)) / 10))
buy_list = []
tmp_pool = final_pool
tmp_qty = qty
for i in range(10):
    p = curr_p * (1 - (0.015 * (i+1)))
    if tmp_pool >= p * step_buy_qty:
        tmp_qty += step_buy_qty
        tmp_pool -= (p * step_buy_qty)
        buy_list.append(f"{i+1}차: ${p:.2f} / {step_buy_qty}주 (잔여:{tmp_qty}개)")

# 매도표 생성 (피라미드)
start_sell_price = max_val / qty if qty > 0 else 0
base_sell_p = max(curr_p, start_sell_price)
sell_weights = [1, 1, 2, 2, 3, 3, 4, 4, 5, 5]
unit_share = qty / sum(sell_weights) if qty > 0 else 0
sell_list = []
tmp_qty_s = qty
for i in range(10):
    s_q = max(1, int(unit_share * sell_weights[i]))
    if tmp_qty_s >= s_q:
        p = base_sell_p * (1 + (0.015 * i))
        tmp_qty_s -= s_q
        sell_list.append(f"{i+1}차: ${p:.2f} / {s_q}주 (잔여:{tmp_qty_s}개)")

# --- [5. 저장 및 메세지 전송] ---
if st.sidebar.button("💾 데이터 저장 및 알림 전송"):
    # 텔레그램 메세지 구성
    msg = f"🚀 TQQQ VR 5.0 가이드\n\n🔹현재가: ${curr_p}\n🔹보유: {qty}주\n🔹Pool: ${final_pool:,.2f}\n\n"
    msg += "🔵 [매수 그물]\n" + "\n".join(buy_list[:5]) + "\n\n"
    msg += "🔴 [매도 그물]\n" + "\n".join(sell_list[:5])
    
    if bot_token and chat_id:
        send_telegram_msg(bot_token, chat_id, msg)
        st.success("✅ 텔레그램으로 가이드를 보냈습니다!")
    
    if conn:
        new_row = pd.DataFrame([{"Date": datetime.now().strftime('%Y-%m-%d'), "Qty": qty, "Pool": final_pool, "V_old": v_final, "Principal": princ_final, "Price": curr_p, "Band": int(b_pct*100)}])
        conn.update(worksheet="Sheet1", data=pd.concat([df, new_row], ignore_index=True).fillna(0))
        st.success("💾 구글 시트 저장 완료!")
        st.rerun()

# (이하 화면 출력 부분은 기존과 동일)
st.title("📊 TQQQ VR 5.0 Dashboard")
t1, t2, t3 = st.tabs(["📋 매매 가이드", "📈 성장 차트", "📖 매뉴얼"])
with t1:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f'<div class="metric-box"><span class="header-text">📉 하단: ${min_val:,.2f}</span><span class="sub-text">잔여:{qty}개 / Pool:${final_pool:,.2f}</span></div>', unsafe_allow_html=True)
        st.dataframe(pd.DataFrame([line.split(' / ') for line in buy_list], columns=["가격","수량"]), use_container_width=True)
    with c2:
        st.markdown(f'<div class="metric-box"><span class="header-text">📈 상단 가격: ${start_sell_price:,.2f}</span><span class="sub-text">전체 상단 가치: ${max_val:,.2f}</span></div>', unsafe_allow_html=True)
        st.dataframe(pd.DataFrame([line.split(' / ') for line in sell_list], columns=["가격","수량"]), use_container_width=True)
