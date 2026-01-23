import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime
import requests
try:
    from streamlit_gsheets import GSheetsConnection
    gsheets_available = True
except ImportError:
    gsheets_available = False

# --- [0. 화면 설정 및 CSS (글자색 검정 강제 고정)] ---
st.set_page_config(page_title="TQQQ VR 5.0 Official", layout="wide")
st.markdown("""
    <style>
        .block-container {padding-top: 1rem; padding-bottom: 2rem;}
        .metric-box {
            background-color: #ffffff;
            border-left: 8px solid #ffcc00; 
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 15px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.2);
        }
        .header-text { font-size: 1.4rem; font-weight: 900; color: #000000 !important; display: block; }
        .sub-text { font-size: 1.1rem; color: #111111 !important; font-weight: 700; }
        .manual-step { background-color: #e3f2fd; padding: 15px; border-radius: 8px; margin-bottom: 12px; border-left: 5px solid #2196f3; color: #000 !important; font-weight: 500; }
    </style>
""", unsafe_allow_html=True)

# --- [1. 텔레그램 전송 (사용자 원본 코드 적용)] ---
def send_telegram_msg(msg):
    try:
        token = st.secrets["telegram"]["bot_token"]
        chat_id = st.secrets["telegram"]["chat_id"]
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}
        requests.post(url, data=data)
        st.toast("✅ 텔레그램 전송 완료!", icon="✈️")
    except:
        st.error("텔레그램 전송 실패: .streamlit/secrets.toml 설정을 확인하세요.")

# --- [2. 데이터 및 사이드바 설정] ---
@st.cache_data(ttl=300)
def get_price():
    try:
        t = yf.Ticker("TQQQ").history(period="1d")
        return round(t['Close'].iloc[-1], 2) if not t.empty else 50.0
    except: return 50.0

curr_p = get_price()

with st.sidebar:
    st.header("⚙️ VR 5.0 전략 세팅")
    invest_type = st.radio("투자 성향", ["적립식 (Pool 75%)", "거치식 (Pool 50%)", "인출식 (Pool 25%)"])
    p_cap = 0.75 if "적립" in invest_type else (0.5 if "거치" in invest_type else 0.25)
    
    c1, c2 = st.columns(2)
    g_val = c1.number_input("기울기(G)", value=10, min_value=1)
    b_pct = c2.number_input("밴드폭(%)", value=15) / 100.0
    
    st.divider()
    
    # 구글 시트 연결
    conn = None
    if gsheets_available:
        try:
            conn = st.connection("gsheets", type=GSheetsConnection)
            df_gs = conn.read(worksheet="Sheet1", ttl=0)
            row = df_gs.iloc[-1]
            last_v = float(str(row.get("V_old", 0)).replace(',',''))
            last_pool = float(str(row.get("Pool", 0)).replace(',',''))
            last_princ = float(str(row.get("Principal", 0)).replace(',',''))
        except:
            conn = None; last_v = last_pool = last_princ = 0.0

    mode = st.radio("작업 선택", ["사이클 업데이트", "최초 시작"], horizontal=True)
    curr_p = st.number_input("현재가 ($)", value=curr_p, format="%.2f")
    qty = st.number_input("보유 수량 (주)", value=0)
    
    if mode == "최초 시작":
        princ_f = st.number_input("총 원금 ($)", value=5000.0)
        qty_init = int((princ_f * 0.5) / curr_p)
        final_pool = princ_f - (qty_init * curr_p)
        v_final = curr_p * qty_init
        qty = qty_init
    else:
        base_p = st.number_input("현재 현금 ($)", value=last_pool)
        add_usd = st.number_input("신규 입금 ($)", value=0.0)
        final_pool = base_p + add_usd
        princ_f = last_princ + add_usd
        v_final = last_v + (final_pool / g_val) + add_usd if final_pool > 0 else last_v + add_usd

# --- [3. 매매 가이드 계산] ---
min_val, max_val = v_final * (1 - b_pct), v_final * (1 + b_pct)
start_s_p = max_val / qty if qty > 0 else 0
base_s_p = max(curr_p, start_s_p)

# 매수 가이드 (균등 배분)
buy_guide, b_step, t_q, t_p = [], (final_pool * p_cap) / 10, qty, final_pool
for i in range(10):
    p = curr_p * (1 - (0.015 * (i+1)))
    q = int(b_step / p) if p > 0 else 0
    if q >= 1 and t_p >= p * q:
        t_q += q; t_p -= (p * q)
        buy_guide.append({"잔여개수": f"{t_q}개", "매수가격": f"${p:.2f}", "Pool": f"${t_p:,.2f}"})

# 매도 가이드 (피라미드)
sell_guide, weights, t_qs, t_ps = [], [1, 1, 2, 2, 3, 3, 4, 4, 5, 5], qty, final_pool
unit = qty / sum(weights) if qty > 0 else 0
for i in range(10):
    q = max(1, int(unit * weights[i]))
    if t_qs >= q:
        p = base_s_p * (1 + (0.015 * i))
        t_qs -= q; t_ps += (p * q)
        sell_guide.append({"잔여개수": f"{t_qs}개", "매도가격": f"${p:.2f}", "수량": f"🔻{q}주", "Pool": f"${t_ps:,.2f}"})

# --- [4. 데이터 저장 및 텔레그램 전송] ---
if st.sidebar.button("💾 데이터 저장 및 알림 전송"):
    # 메세지 구성
    msg = f"🚀 [TQQQ VR 5.0 가이드]\n💰 Pool: ${final_pool:,.2f}\n📉 하단: ${min_val:,.2f}\n📈 상단가: ${start_s_p:,.2f}\n\n"
    msg += "🔵 [매수 가이드]\n" + "\n".join([f"{d['매수가격']} / {d['잔여개수']}" for d in buy_guide[:5]]) + "\n\n"
    msg += "🔴 [매도 가이드]\n" + "\n".join([f"{d['매도가격']} / {d['수량']}" for d in sell_guide[:5]])
    
    # 전송
    send_telegram_msg(msg)
    
    # 구글 시트 저장
    if conn:
        new_row = pd.DataFrame([{"Date": datetime.now().strftime('%Y-%m-%d'), "Qty": qty, "Pool": final_pool, "V_old": v_final, "Principal": princ_f, "Price": curr_p, "Band": int(b_pct*100)}])
        conn.update(worksheet="Sheet1", data=pd.concat([df_gs, new_row], ignore_index=True).fillna(0))
        st.success("💾 구글 시트 저장 완료!")
        st.rerun()

# --- [5. 메인 화면 출력 (TAB)] ---
st.title("🚀 TQQQ VR 5.0 Dashboard")
t1, t2, t3 = st.tabs(["📋 매매 가이드", "📈 성장 차트", "📖 필승 매뉴얼"])

with t1:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f'<div class="metric-box"><span class="header-text">📉 최소값(밴드하단): ${min_val:,.2f}</span><span class="sub-text">현재 잔여개수: {qty}개 │ 현재 Pool: ${final_pool:,.2f}</span></div>', unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(buy_guide), use_container_width=True, hide_index=True)
    with c2:
        st.markdown(f'<div class="metric-box"><span class="header-text">📈 최대값(밴드상단): ${max_val:,.2f}</span><span class="sub-text">상단 도달 가격: ${start_s_p:,.2f}</span></div>', unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(sell_guide), use_container_width=True, hide_index=True)

with t2:
    if conn:
        df_plot = conn.read(worksheet="Sheet1", ttl=0)
        if not df_plot.empty:
            df_plot['Date'] = pd.to_datetime(df_plot['Date'])
            df_plot["상단"] = df_plot["V_old"] * (1 + b_pct); df_plot["하단"] = df_plot["V_old"] * (1 - b_pct); df_plot["자산"] = df_plot["Qty"] * df_plot["Price"]
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_plot['Date'], y=df_plot['상단'], line=dict(color='#00FF00', width=1), name='매도밴드'))
            fig.add_trace(go.Scatter(x=df_plot['Date'], y=df_plot['하단'], line=dict(color='#FF4B4B', width=1), fill='tonexty', name='매수밴드'))
            fig.add_trace(go.Scatter(x=df_plot['Date'], y=df_plot['V_old'], line=dict(color='#00BFFF', dash='dot'), name='목표V'))
            fig.add_trace(go.Scatter(x=df_plot['Date'], y=df_plot['자산'], line=dict(color='#FFFF00', width=3), name='내자산'))
            st.plotly_chart(fig, use_container_width=True)

with t3:
    st.markdown("### 📘 VR 5.0 초심자 상세 매뉴얼")
    with st.expander("1️⃣ 최초 시작 (처음 세팅할 때)", expanded=True):
        st.markdown('<div class="manual-step">사이드바 <b>[최초 시작]</b> 선택 → 총 원금 입력 → 즉시 매수 후 <b>[데이터 저장]</b> 클릭</div>', unsafe_allow_html=True)
    with st.expander("2️⃣ 2주마다 반복 (사이클 업데이트)", expanded=True):
        st.markdown('<div class="manual-step">사이드바 <b>[사이클 업데이트]</b> 선택 → 현재 주식수/현금 입력 → <b>[데이터 저장 및 알림 전송]</b> 클릭 → 텔레그램 확인</div>', unsafe_allow_html=True)
    with st.expander("3️⃣ 증권사 예약 주문 (그물 치기)", expanded=True):
        st.markdown('<div class="manual-step">증권사 앱에서 <b>2주 기간/지정가/잔량유지</b> 조건으로 표에 나온 가격/수량대로 예약 주문</div>', unsafe_allow_html=True)
