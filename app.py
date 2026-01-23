import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
from streamlit_gsheets import GSheetsConnection

# --- [0. 화면 설정] ---
st.set_page_config(page_title="TQQQ VR 5.0", layout="wide")
st.markdown("""
    <style>
        .block-container {padding-top: 1.5rem; padding-bottom: 1rem;}
        div[data-testid="stMetricValue"] {font-size: 1.5rem !important; font-weight: 700;}
    </style>
""", unsafe_allow_html=True)

# 텔레그램
def send_telegram_msg(msg):
    try:
        if "telegram" in st.secrets:
            token = st.secrets["telegram"]["bot_token"]
            chat_id = st.secrets["telegram"]["chat_id"]
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(url, data={"chat_id": chat_id, "text": msg})
            st.toast("✅ 전송 완료")
    except: pass

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

# --- [사이드바] ---
with st.sidebar:
    st.header("📊 VR 5.0 설정")
    invest_type = st.radio("투자 성향", ["적립식 (75%)", "거치식 (50%)"])
    pool_cap = 0.75 if "적립식" in invest_type else 0.50
    
    c1, c2 = st.columns(2)
    with c1: g_val = st.number_input("기울기(G)", value=10, min_value=1)
    with c2: b_pct = st.number_input("밴드폭(%)", value=15) / 100.0
    
    st.divider()
    
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = pd.DataFrame()
    last_v, last_princ = 0.0, 0.0
    
    try:
        df = conn.read(worksheet="Sheet1", ttl=0)
        if not df.empty:
            row = df.iloc[-1]
            last_v = float(str(row.get("V_old", 0)).replace(',',''))
            last_princ = float(str(row.get("Principal", 0)).replace(',',''))
    except: pass

    mode = st.radio("작업 선택", ["사이클 업데이트", "최초 시작"], horizontal=True)
    curr_p = st.number_input("TQQQ 현재가($)", value=m["price"], format="%.2f")
    curr_fx = st.number_input("현재 환율", value=m["fx"])
    qty = st.number_input("보유 수량(주)", value=0)
    pool = st.number_input("현금 Pool($)", value=0.0)
    
    v_final, princ_final, growth = 0.0, last_princ, 0.0
    if mode == "최초 시작":
        princ_final = st.number_input("초기 원금($)", value=0.0)
        v_final = curr_p * qty
    else:
        add_usd = st.number_input("신규 적립($)", value=0.0)
        princ_final += add_usd
        if pool > 0: growth = pool / g_val
        v_final = last_v + growth + add_usd 

    if st.button("💾 데이터 저장", use_container_width=True):
        new_row = pd.DataFrame([{
            "Date": datetime.now().strftime('%Y-%m-%d'),
            "Qty": qty, "Pool": pool, "V_old": v_final, "Principal": princ_final,
            "Price": curr_p, "Band": int(b_pct*100)
        }])
        final_df = pd.concat([df, new_row], ignore_index=True) if not df.empty else new_row
        conn.update(worksheet="Sheet1", data=final_df.fillna(0))
        st.success("저장 완료!")
        st.rerun()

# --- [메인 대시보드] ---
if curr_p <= 0: st.stop()

eval_usd = curr_p * qty
total_usd = eval_usd + pool
roi = ((total_usd - princ_final)/princ_final*100) if princ_final > 0 else 0

st.title("🚀 TQQQ VR 5.0 Dashboard")

c1, c2, c3, c4 = st.columns(4)
c1.metric("목표값 (V)", f"${v_final:,.0f}", f"+${growth:,.0f}")
c2.metric("총 자산", f"${total_usd:,.0f}")
c3.metric("가용 Pool", f"${pool:,.0f}")
c4.metric("수익률", f"{roi:.2f}%")

tab1, tab2 = st.tabs(["📋 매매 가이드", "📈 자산 성장 차트"])

with tab1:
    col_buy, col_sell = st.columns(2)
    with col_buy:
        st.subheader("🔵 매수 (LOC)")
        limit = pool * pool_cap
        buy_table = []
        for i, r in enumerate([0.98, 0.96, 0.94, 0.92, 0.90]):
            p = curr_p * r
            q = int((limit/5)/p)
            if q >= 1: buy_table.append({"단계": f"{i+1}차", "가격": f"${p:.2f}", "수량": f"{q}주"})
        st.table(pd.DataFrame(buy_table))

    with col_sell:
        st.subheader("🔴 매도 (지정가)")
        v_max = v_final * (1 + b_pct)
        if qty > 0:
            target_p = v_max / qty
            if curr_p >= target_p:
                st.error(f"🚨 돌파! {int((eval_usd-v_final)/curr_p)}주 매도")
            else:
                st.success(f"목표가: ${target_p:.2f}")
        else: st.info("보유량 없음")

with tab2:
    # 1. 데이터 준비
    c_df = df.copy() if not df.empty else pd.DataFrame()
    if not c_df.empty: c_df['Date'] = pd.to_datetime(c_df['Date'])
    
    now_df = pd.DataFrame([{
        "Date": pd.to_datetime(datetime.now().strftime('%Y-%m-%d')), 
        "V_old": v_final, 
        "Qty": qty, 
        "Price": curr_p, 
        "Band": int(b_pct*100)
    }])
    plot_df = pd.concat([c_df, now_df], ignore_index=True)
    plot_df = plot_df.drop_duplicates(subset=['Date'], keep='last').sort_values('Date')
    
    # 2. 차트 데이터 계산
    plot_df["상단"] = plot_df["V_old"] * (1 + plot_df["Band"]/100.0)
    plot_df["하단"] = plot_df["V_old"] * (1 - plot_df["Band"]/100.0)
    plot_df["자산"] = plot_df["Qty"] * plot_df["Price"]
    
    # 3. Y축 '타이트' 스케일링 계산
    # (0이나 음수는 제외하고 실제 데이터 범위만 추출)
    valid_vals = pd.concat([plot_df["상단"], plot_df["하단"], plot_df["자산"]])
    valid_vals = valid_vals[valid_vals > 0]
    
    if not valid_vals.empty:
        y_min_real = valid_vals.min()
        y_max_real = valid_vals.max()
        
        # 위아래 10% 정도만 여유를 둠 -> 밴드가 꽉 차게 보임
        # 자산이 1000이면 약 900~1100 사이로 잡힘
        y_range = [y_min_real * 0.9, y_max_real * 1.1]
    else:
        y_range = None # 데이터 없을 땐 자동

    # 4. 차트 그리기
    fig = go.Figure()
    
    # 밴드 (초록)
    fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['상단'], line=dict(color='#00FF00', width=1.5), name='Band Top'))
    fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['하단'], line=dict(color='#00FF00', width=1.5), fill='tonexty', fillcolor='rgba(0, 255, 0, 0.05)', name='Band Bottom'))
    
    # 목표 V (하늘색 점선)
    fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['V_old'], line=dict(color='#00BFFF', width=2, dash='dot'), name='Target V'))
    
    # 내 자산 (노랑)
    mode_set = 'markers' if len(plot_df) == 1 else 'lines+markers'
    fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['자산'], 
                             line=dict(color='#FFFF00', width=3), 
                             marker=dict(size=8, color='#FFFF00'), 
                             mode=mode_set, name='My Asset'))
    
    # X축 설정 (데이터 1개일 때 중앙 정렬)
    xaxis_config = dict(showgrid=True, gridcolor='rgba(255,255,255,0.1)', tickformat='%y-%m-%d')
    if len(plot_df) == 1:
        d = plot_df['Date'].iloc[0]
        xaxis_config['range'] = [d - timedelta(days=1), d + timedelta(days=1)]

    fig.update_layout(
        height=500,
        paper_bgcolor='rgba(0,0,0,0)', 
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis=xaxis_config,
        yaxis=dict(
            showgrid=True, gridcolor='rgba(255,255,255,0.1)', 
            range=y_range, # [핵심] 계산된 타이트한 범위 적용
            fixedrange=False
        ),
        legend=dict(orientation="h", y=1.05, x=1, xanchor="right")
    )
    st.plotly_chart(fig, use_container_width=True)
