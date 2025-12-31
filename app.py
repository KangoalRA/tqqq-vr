import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests

# --- [0. 기본 설정] ---
st.set_page_config(page_title="TQQQ 적립식 VR 5.0", layout="wide")

@st.cache_data(ttl=600)
def get_market_data():
    data = {"price": 0.0, "fx": 1400.0, "dd": 0.0, "fng": 50.0, "bull": True}
    try:
        t = yf.Ticker("TQQQ").history(period="5d")
        n = yf.Ticker("^NDX").history(period="2y")
        if not t.empty: data["price"] = round(t['Close'].iloc[-1], 2)
        if not n.empty:
            cur = n['Close'].iloc[-1]
            high = n['Close'].max()
            data["dd"] = round((cur/high - 1)*100, 2)
            data["bull"] = cur > n['Close'].rolling(200).mean().iloc[-1]
        
        fx = yf.Ticker("USDKRW=X").history(period="1d")
        if not fx.empty: data["fx"] = round(fx['Close'].iloc[-1], 2)
        
        try:
            r = requests.get("https://production.dataviz.cnn.io/index/fearandgreed/graphdata", headers={'User-Agent': 'Mozilla/5.0'}, timeout=2)
            if r.status_code == 200: data["fng"] = float(r.json()['fear_and_greed']['score'])
        except: pass
        
        return data
    except: return data

m = get_market_data()

# --- [1. 사이드바: 중복 제거 및 통합] ---
# 제목 한 번만 출력
st.sidebar.title("⚙️ VR 운용 설정")

# [A] 시장 지표 (한 번만 표시)
with st.sidebar.expander("📊 시장 지표 확인/수정", expanded=True):
    st.metric("나스닥 낙폭 (MDD)", f"{m['dd']}%")
    fng_input = st.number_input("Fear & Greed Index", value=float(m['fng']), min_value=0.0, max_value=100.0)
    st.caption(f"기준 환율: {m['fx']}원/$")

st.sidebar.divider()

# [B] 밴드 설정 (한 번만 표시)
rec_msg = "🛡️ 10% (하락장)" if m['dd'] < -20 else ("🚀 20% (상승장)" if m['bull'] and m['dd'] >= -10 else "⚖️ 15% (평소)")
st.sidebar.info(f"추천: {rec_msg}")
band = st.sidebar.slider("밴드폭 설정 (%)", 5, 30, 15) / 100

st.sidebar.divider()

# [C] 내 자산 입력 (핵심: 중복 없이 '현재상태' + '추가입금'만 입력)
st.sidebar.subheader("📝 자산 입력")

# 1. 현재 계좌 잔고
qty = st.sidebar.number_input("1. 현재 보유 수량 (주)", value=100, min_value=0)
cur_cash = st.sidebar.number_input("2. 현재 보유 예수금 ($)", value=1000.0)

# 2. 오늘 추가할 돈 (리필)
add_krw = st.sidebar.number_input("3. 오늘 추가 입금액 (원)", value=0, step=10000, help="월급날 리필할 때만 입력")
add_usd = add_krw / m['fx'] 

# [D] 자동 계산 (V값)
cur_stock_val = m['price'] * qty
final_pool = cur_cash + add_usd
total_equity = cur_stock_val + final_pool

st.sidebar.markdown(f"👉 **추가 입금 반영: ${add_usd:.2f}**")
st.sidebar.divider()

# V값 목표 설정 (보통 총 자산 따라감)
v_target = st.sidebar.number_input("4. 목표 V값 (자동계산됨)", value=float(int(total_equity)))


# --- [2. 메인 로직 및 대시보드] ---
v_low = v_target * (1 - band)
v_high = v_target * (1 + band)

# 안전장치 함수
def get_status(dd, fng):
    if dd > -10: return 1.0, "green", "정상장 (100%)"
    elif -20 < dd <= -10: return (0.5, "orange", "조정장 (50%)") if fng <= 20 else (0.0, "red", "매수보류")
    else: return (0.3, "red", "폭락장 (30%)") if fng <= 10 else (0.0, "red", "매수보류")

qta, color, status_msg = get_status(m['dd'], fng_input)

# 메인 화면 출력
st.title("🚀 TQQQ 적립식 VR 5.0")
st.markdown(f"**현재가:** ${m['price']} | **FnG:** {fng_input} | **상태:** {status_msg}")

# 정보 카드
c1, c2, c3, c4 = st.columns(4)
c1.metric("총 자산", f"${total_equity:,.0f}")
c2.metric("보유 현금 (리필후)", f"${final_pool:,.0f}")
c3.metric("목표 V", f"${v_target:,.0f}")
c4.metric("밴드 범위", f"±{band*100}%", f"${v_low:,.0f} ~ ${v_high:,.0f}")

st.divider()

# 매매 가이드 (테이블 형태)
col_buy, col_sell = st.columns(2)

with col_buy:
    st.subheader("🔵 매수 (Buy)")
    if cur_stock_val < v_low:
        if qta > 0:
            st.success(f"✅ 매수 진행 ({qta*100}% 가동)")
            data = []
            for n in range(1, 11):
                t_q = qty + n
                loc = v_low / t_q
                if loc < m['price'] * 1.15:
                    cost = loc * n
                    note = "가능" if cost <= final_pool * qta else "현금부족"
                    data.append({"매수":f"+{n}주", "LOC단가":f"${loc:.2f}", "비용":f"${cost:.0f}", "상태":note})
            st.table(pd.DataFrame(data))
        else:
            st.error("⛔ FnG 지표가 높아 매수를 쉽니다.")
    else:
        st.info("😴 관망 (매수 구간 아님)")

with col_sell:
    st.subheader("🔴 매도 (Sell)")
    if cur_stock_val > v_high:
        st.warning("🔥 수익 실현")
        data = []
        for n in range(1, 11):
            if qty - n >= 0:
                t_q = qty - n
                loc = v_high / t_q
                if loc > m['price'] * 0.85:
                    data.append({"매도":f"-{n}주", "LOC단가":f"${loc:.2f}", "현금확보":f"${loc*n:.0f}"})
        st.table(pd.DataFrame(data))
    else:
        st.info("😴 관망 (매도 구간 아님)")

# 그래프
st.divider()
fig = go.Figure()
days = [datetime.now().date(), datetime.now().date() + timedelta(days=14)]
fig.add_trace(go.Scatter(x=days, y=[v_target, v_target], name="목표 V", line=dict(dash='dot', color='gray')))
fig.add_trace(go.Scatter(x=days, y=[v_high, v_high], name="매도선", line=dict(color='red')))
fig.add_trace(go.Scatter(x=days, y=[v_low, v_low], name="매수선", line=dict(color='blue')))
fig.add_trace(go.Scatter(x=[days[0]], y=[cur_stock_val], mode='markers+text', name="현재주식가치", 
                         text=["Here"], textposition="top center", marker=dict(size=15, color='green')))
fig.update_layout(height=400, template="plotly_white", title="VR 밴드 시각화")
st.plotly_chart(fig, use_container_width=True)
