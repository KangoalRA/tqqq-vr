import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
from streamlit_gsheets import GSheetsConnection

# --- [0. 화면 설정] ---
st.set_page_config(page_title="TQQQ VR 5.0 Official", layout="wide")
st.markdown("""
    <style>
        .block-container {padding-top: 1.5rem; padding-bottom: 1rem;}
        div[data-testid="stMetricValue"] {font-size: 1.5rem !important; font-weight: 700;}
        .manual-box { background-color: rgba(255, 255, 255, 0.05); padding: 20px; border-radius: 10px; border-left: 5px solid #00BFFF; }
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

# --- [사이드바] ---
with st.sidebar:
    st.header("📊 VR 5.0 전략 설정")
    invest_type = st.radio("투자 성향", ["적립식 (75% 사용)", "거치식 (50% 사용)"])
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

st.title("🚀 TQQQ VR 5.0 공식 시스템")

c1, c2, c3, c4 = st.columns(4)
c1.metric("계산된 목표값(V)", f"${v_final:,.0f}", f"+${growth:,.0f}")
c2.metric("총 자산(E+P)", f"${total_usd:,.0f}")
c3.metric("가용 Pool", f"${pool:,.0f}")
c4.metric("현재 수익률", f"{roi:.2f}%")

tab1, tab2, tab3 = st.tabs(["📋 매매 가이드", "📈 성장 히스토리", "📖 운용 매뉴얼"])

# --- [Tab 1: 가이드] ---
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

# --- [Tab 2: 차트] ---
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
    
    fig = go.Figure()
    if not plot_df.empty:
        last_d, last_v, last_t, last_b = plot_df['Date'].max(), plot_df['V_old'].iloc[-1], plot_df['상단'].iloc[-1], plot_df['하단'].iloc[-1]
        future_d = last_d + timedelta(days=60)
        
        fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['상단'], line=dict(color='#00FF00', width=1.5), name='밴드 상단'))
        fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['하단'], line=dict(color='#00FF00', width=1.5), fill='tonexty', fillcolor='rgba(0, 255, 0, 0.05)', name='밴드 하단'))
        fig.add_trace(go.Scatter(x=[last_d, future_d], y=[last_t, last_t], line=dict(color='#00FF00', width=1.5), showlegend=False))
        fig.add_trace(go.Scatter(x=[last_d, future_d], y=[last_b, last_b], line=dict(color='#00FF00', width=1.5), showlegend=False))
        fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['V_old'], line=dict(color='#00BFFF', width=2, dash='dot'), name='목표(V)'))
        fig.add_trace(go.Scatter(x=[last_d, future_d], y=[last_v, last_v], line=dict(color='#00BFFF', width=2, dash='dot'), showlegend=False))
        
        asset_plot = plot_df[plot_df["자산"] > 0]
        fig.add_trace(go.Scatter(x=asset_plot['Date'], y=asset_plot['자산'], line=dict(color='#FFFF00', width=3), mode='lines+markers', name='내 자산(E)'))
        
        fig.update_layout(height=500, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', xaxis=dict(tickformat='%y-%m-%d', range=[plot_df['Date'].min() - timedelta(days=1), future_d]), yaxis=dict(autorange=True, fixedrange=False))
        st.plotly_chart(fig, use_container_width=True)

# --- [Tab 3: 매뉴얼] ---
with tab3:
    st.markdown("### 📖 VR 5.0 (Pool형) 운용 가이드")
    
    st.info("**기본 철학:** 시장을 예측하지 않는다. 오직 가용 현금(Pool)의 한도와 목표 가치(V)를 기준으로 리스크를 통제한다.")

    col_m1, col_m2 = st.columns(2)
    
    with col_m1:
        st.markdown("#### 1️⃣ 최초 시작 (First Start)")
        st.write("VR을 **처음 세팅하거나 완전히 새로 시작**할 때 사용합니다.")
        st.markdown("""
        * **언제?** 생전 처음 이 시스템을 켤 때.
        * **원칙:** 현재 내 자산 상태($Price \\times Qty$)를 그대로 첫 번째 $V$값으로 고정합니다.
        * **주의:** 투입한 원금($Principal$)을 정확히 적어야 정확한 수익률 계산이 가능합니다.
        """)
        
    with col_m2:
        st.markdown("#### 2️⃣ 사이클 업데이트 (Cycle Update)")
        st.write("**2주에 한 번씩** 주기적으로 갱신하며 우상향을 유도합니다.")
        st.markdown("""
        * **언제?** 2주간의 매매가 끝난 후 새 계획을 짤 때.
        * **공식:** $V_{new} = V_{old} + (Pool / G) + \text{신규 적립금}$
        * **핵심:** 현금($Pool$)이 많으면 $V$가 가파르게 성장하고, 현금이 없으면 성장이 더뎌지며 주가가 오르길 기다립니다.
        """)

    st.divider()

    st.markdown("#### 💡 결정적 운용 팁 (Trading Tips)")
    st.table(pd.DataFrame({
        "구분": ["매수 (Buying)", "매도 (Selling)", "관망 (Holding)"],
        "기준": ["평가금 < 밴드 하단", "평가금 > 밴드 상단", "밴드 내부"],
        "행동": ["가용 Pool 내에서 LOC 매수", "초과분($E-V$)만큼 리밸런싱 매도", "아무것도 안 함 (생업에 집중)"]
    }))

    st.warning("⚠️ **가장 중요한 리스크 관리:** 하락장이 길어지면 Pool 한도(50% or 75%)를 다 쓰게 됩니다. 이때는 추가 매수를 멈추고 주가가 반등하여 다시 밴드 안으로 들어올 때까지 기다려야 생존할 수 있습니다.")
