import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
from streamlit_gsheets import GSheetsConnection

# --- [0. 화면 및 스타일 설정] ---
st.set_page_config(page_title="TQQQ VR 5.0 Official", layout="wide")
st.markdown("""
    <style>
        .block-container {padding-top: 1.5rem; padding-bottom: 1rem;}
        div[data-testid="stMetricValue"] {font-size: 1.5rem !important; font-weight: 700;}
        .manual-section { background-color: rgba(0, 191, 255, 0.05); padding: 15px; border-radius: 8px; border-left: 5px solid #00BFFF; margin-bottom: 15px; }
        .tip-box { background-color: rgba(255, 255, 0, 0.05); padding: 15px; border-radius: 8px; border-left: 5px solid #FFFF00; }
    </style>
""", unsafe_allow_html=True)

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

# --- [사이드바: 전략 설정 및 데이터 입력] ---
with st.sidebar:
    st.header("📊 VR 5.0 전략 설정")
    invest_type = st.radio("투자 성향", ["적립식 (75% 한도)", "거치식 (50% 한도)"])
    pool_cap = 0.75 if "적립식" in invest_type else 0.50
    
    c1, c2 = st.columns(2)
    with c1: g_val = st.number_input("기울기(G)", value=10, min_value=1)
    with c2: b_pct = st.number_input("밴드폭(%)", value=15) / 100.0
    
    st.divider()
    
    # 데이터 로드 (Google Sheets)
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = pd.DataFrame()
    last_v, last_princ = 0.0, 0.0
    
    try:
        df = conn.read(worksheet="Sheet1", ttl=0)
        if not df.empty:
            row = df.iloc[-1]
            def safe_float(x):
                try: return float(str(x).replace(',',''))
                except: return 0.0
            last_v = safe_float(row.get("V_old", 0))
            last_princ = safe_float(row.get("Principal", 0))
    except: pass

    mode = st.radio("작업 선택", ["사이클 업데이트", "최초 시작"], horizontal=True)
    curr_p = st.number_input("TQQQ 현재가($)", value=m["price"], format="%.2f")
    curr_fx = st.number_input("현재 환율", value=m["fx"])
    qty = st.number_input("보유 수량(주)", value=0)
    pool = st.number_input("현금 Pool($)", value=0.0)
    
    # 핵심 계산 로직
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

# 상단 핵심 지표 배치
m1, m2, m3, m4 = st.columns(4)
m1.metric("계산된 목표값(V)", f"${v_final:,.0f}", f"+${growth:,.0f} 성장")
m2.metric("총 자산(E+P)", f"${total_usd:,.0f}")
m3.metric("가용 Pool", f"${pool:,.0f}")
m4.metric("현재 수익률", f"{roi:.2f}%")

tab1, tab2, tab3 = st.tabs(["📋 매매 가이드", "📈 자산 성장 차트", "📖 운용 매뉴얼"])

# --- [Tab 1: 매매 가이드] ---
with tab1:
    col_buy, col_sell = st.columns(2)
    with col_buy:
        st.subheader("🔵 매수 예약 (LOC)")
        limit = pool * pool_cap
        st.caption(f"가용 예산: ${limit:,.0f} (Pool의 {int(pool_cap*100)}%)")
        buy_table = []
        for i, r in enumerate([0.98, 0.96, 0.94, 0.92, 0.90]):
            p = curr_p * r
            q = int((limit/5)/p)
            if q >= 1: buy_table.append({"단계": f"{i+1}차", "가격": f"${p:.2f}", "수량": f"{q}주"})
        st.table(pd.DataFrame(buy_table))

    with col_sell:
        st.subheader("🔴 리밸런싱 매도 (지정가)")
        v_max = v_final * (1 + b_pct)
        if qty > 0:
            target_p = v_max / qty
            if curr_p >= target_p:
                excess = eval_usd - v_final
                st.error(f"🚨 **밴드 상단 돌파!** {int(excess/curr_p)}주 매도하여 수익을 확정하세요.")
            else:
                st.success(f"매도 목표가: **${target_p:.2f}**")
                st.write(f"도달 시 약 {int((v_max - v_final)/target_p)}주 매도")
        else: st.info("보유 수량 없음")

# --- [Tab 2: 성장 차트] ---
with tab2:
    c_df = df.copy() if not df.empty else pd.DataFrame()
    if not c_df.empty: c_df['Date'] = pd.to_datetime(c_df['Date']).dt.normalize()
    now_date = pd.to_datetime(datetime.now().date())
    now_df = pd.DataFrame([{"Date": now_date, "V_old": v_final, "Qty": qty, "Price": curr_p, "Band": int(b_pct*100)}])
    plot_df = pd.concat([c_df, now_df], ignore_index=True)
    plot_df = plot_df.drop_duplicates(subset=['Date'], keep='last').sort_values('Date')
    plot_df = plot_df[plot_df["V_old"] > 0]
    
    plot_df["상단"] = plot_df["V_old"] * (1 + plot_df["Band"]/100.0)
    plot_df["하단"] = plot_df["V_old"] * (1 - plot_df["Band"]/100.0)
    plot_df["자산"] = plot_df["Qty"] * plot_df["Price"]
    plot_df = plot_df[plot_df["자산"] > 0] # 0원 데이터 제거
    
    fig = go.Figure()
    if not plot_df.empty:
        last_d, last_v, last_t, last_b = plot_df['Date'].max(), plot_df['V_old'].iloc[-1], plot_df['상단'].iloc[-1], plot_df['하단'].iloc[-1]
        future_d = last_d + timedelta(days=60)
        
        # 밴드 (초록 실선)
        fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['상단'], line=dict(color='#00FF00', width=1.5), name='매도 밴드'))
        fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['하단'], line=dict(color='#00FF00', width=1.5), fill='tonexty', fillcolor='rgba(0, 255, 0, 0.05)', name='매수 밴드'))
        fig.add_trace(go.Scatter(x=[last_d, future_d], y=[last_t, last_t], line=dict(color='#00FF00', width=1.5), showlegend=False))
        fig.add_trace(go.Scatter(x=[last_d, future_d], y=[last_b, last_b], line=dict(color='#00FF00', width=1.5), showlegend=False))
        # 목표V (하늘색 점선)
        fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['V_old'], line=dict(color='#00BFFF', width=2, dash='dot'), name='목표(V)'))
        fig.add_trace(go.Scatter(x=[last_d, future_d], y=[last_v, last_v], line=dict(color='#00BFFF', width=2, dash='dot'), showlegend=False))
        # 내 자산 (노란 실선)
        fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['자산'], line=dict(color='#FFFF00', width=3), mode='lines+markers', name='내 주식 가치(E)'))
        
        y_vals = pd.concat([plot_df["상단"], plot_df["하단"], plot_df["자산"]])
        y_range = [y_vals.min()*0.9, y_vals.max()*1.1]
        fig.update_layout(height=500, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', xaxis=dict(tickformat='%y-%m-%d', range=[plot_df['Date'].min() - timedelta(days=1), future_d]), yaxis=dict(range=y_range, fixedrange=False))
        st.plotly_chart(fig, use_container_width=True)

# --- [Tab 3: 상세 매뉴얼] ---
with tab3:
    st.markdown("### 📖 TQQQ VR 5.0 공식 운용 매뉴얼")
    
    with st.container():
        st.markdown('<div class="manual-section">', unsafe_allow_html=True)
        st.markdown("#### 1️⃣ 최초 시작 (Setting Up)")
        st.write("**적정 자산 배분:** 처음 5,000달러로 시작한다면, **현금 50%($2,500) / 주식 50%($2,500)** 비중으로 먼저 매수하고 시작하는 것을 강력 권장합니다.")
        st.markdown("""
        - **방법:** 사이드바 모드를 `최초 시작`으로 설정.
        - **입력:** 매수한 TQ 수량과 남은 현금을 입력 후 저장.
        - **효과:** 현재 내 자산 가치가 시스템의 첫 번째 기준점($V$)이 됩니다.
        """)
        st.markdown('</div>', unsafe_allow_html=True)

    with st.container():
        st.markdown('<div class="manual-section">', unsafe_allow_html=True)
        st.markdown("#### 2️⃣ 적립식 사이클 업데이트 (Running)")
        st.write("2주마다 한 번씩 월급(적립금)을 추가하며 목표치를 상향합니다.")
        st.markdown("""
        - **방법:** 사이드바 모드를 `사이클 업데이트`로 설정.
        - **적립:** `신규 적립($)` 칸에 이번 주기에 추가한 달러 금액을 입력.
        - **공식:** $V_{new} = V_{old} + (Pool / G) + \text{신규 적립금}$
        - **효과:** 적립금이 목표치에 더해지며, 자연스럽게 더 많은 수량을 매수하도록 유도합니다.
        """)
        st.markdown('</div>', unsafe_allow_html=True)

    with st.container():
        st.markdown('<div class="tip-box">', unsafe_allow_html=True)
        st.markdown("#### 💡 실전 운용 팁")
        st.markdown("""
        - **Pool 한도:** 적립식은 매달 돈이 들어오므로 하락장에서 **현금의 75%**까지 과감히 쓰셔도 됩니다.
        - **기울기(G):** 기본값 **10**을 유지하세요. 현금이 들어올 때마다 $V$를 밀어 올려 복리 효과를 극대화합니다.
        - **본업 집중:** 2주에 한 번, 월요일 아침에 이 앱을 켜고 가이드대로 예약 매수(LOC)만 걸어두면 끝입니다.
        """)
        st.markdown('</div>', unsafe_allow_html=True)
