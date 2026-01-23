import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
from streamlit_gsheets import GSheetsConnection

# --- [0. 화면 설정 및 스타일] ---
st.set_page_config(page_title="TQQQ VR 5.0 Official", layout="wide")
st.markdown("""
    <style>
        .block-container {padding-top: 1.5rem; padding-bottom: 1rem;}
        div[data-testid="stMetricValue"] {font-size: 1.5rem !important; font-weight: 700;}
        .manual-section { background-color: rgba(0, 191, 255, 0.05); padding: 18px; border-radius: 10px; border-left: 6px solid #00BFFF; margin-bottom: 20px; }
        .tip-box { background-color: rgba(255, 255, 0, 0.05); padding: 18px; border-radius: 10px; border-left: 6px solid #FFFF00; }
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

# --- [사이드바: 전략 및 데이터 입력] ---
with st.sidebar:
    st.header("📊 VR 5.0 전략 설정")
    invest_type = st.radio("투자 성향", ["적립식 (Pool 75% 사용)", "거치식 (Pool 50% 사용)"])
    pool_cap = 0.75 if "적립식" in invest_type else 0.50
    
    c1, c2 = st.columns(2)
    with c1: g_val = st.number_input("기울기(G)", value=10, min_value=1)
    with c2: b_pct = st.number_input("밴드폭(%)", value=15) / 100.0
    
    st.divider()
    
    # 구글 시트 데이터 로드
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
            st.success(f"이전 데이터 로드 완료")
    except: pass

    mode = st.radio("모드 선택", ["사이클 업데이트", "최초 시작"], horizontal=True)
    curr_p = st.number_input("TQQQ 현재가($)", value=m["price"], format="%.2f")
    curr_fx = st.number_input("현재 환율(원)", value=m["fx"])
    
    qty = st.number_input("보유 수량(주)", value=0)
    
    # [핵심 수정] 현금 입력 로직
    # 사이클 업데이트 시, 이전 Pool을 기본값으로 보여줌
    base_pool = st.number_input("현재 계좌 현금($)", value=last_pool, help="기존 매매 후 남은 현금을 입력하세요.")
    add_usd = st.number_input("신규 적립금($)", value=0.0, help="이번 주기에 새로 입금할 금액을 적으세요.")
    
    # 최종 현금(Pool) = 현재 계좌 현금 + 신규 적립금
    final_pool = base_pool + add_usd
    
    v_final, princ_final, growth = 0.0, last_princ, 0.0
    if mode == "최초 시작":
        princ_final = st.number_input("총 투입 원금($)", value=0.0)
        v_final = curr_p * qty
    else:
        princ_final = last_princ + add_usd
        if final_pool > 0: 
            growth = final_pool / g_val # 적립금 포함된 총 현금으로 성장 계산
        v_final = last_v + growth + add_usd 

    if st.button("💾 데이터 저장 (Save)", use_container_width=True):
        new_row = pd.DataFrame([{
            "Date": datetime.now().strftime('%Y-%m-%d'),
            "Qty": qty, 
            "Pool": final_pool, # 합산된 현금 저장
            "V_old": v_final, 
            "Principal": princ_final,
            "Price": curr_p, 
            "Band": int(b_pct*100)
        }])
        final_df = pd.concat([df, new_row], ignore_index=True) if not df.empty else new_row
        conn.update(worksheet="Sheet1", data=final_df.fillna(0))
        st.success("성공적으로 저장되었습니다!")
        st.rerun()

# --- [메인 대시보드] ---
if curr_p <= 0: st.stop()

eval_usd = curr_p * qty
total_usd = eval_usd + final_pool
roi = ((total_usd - princ_final)/princ_final*100) if princ_final > 0 else 0

st.title("🚀 TQQQ VR 5.0 Dashboard")

c1, c2, c3, c4 = st.columns(4)
c1.metric("계산된 목표값(V)", f"${v_final:,.0f}", f"+${growth:,.0f} 성장")
c2.metric("총 자산 (현금포함)", f"${total_usd:,.0f}")
c3.metric("최종 Pool (현금)", f"${final_pool:,.0f}", f"+${add_usd:,.0f} 입금")
c4.metric("현재 수익률", f"{roi:.2f}%")

tab1, tab2, tab3 = st.tabs(["📋 매매 가이드", "📈 성장 히스토리", "📖 운용 매뉴얼"])

# --- [Tab 1: 가이드] ---
with tab1:
    col_buy, col_sell = st.columns(2)
    with col_buy:
        st.subheader("🔵 매수 예약 (LOC)")
        limit = final_pool * pool_cap
        buy_table = []
        for i, r in enumerate([0.98, 0.96, 0.94, 0.92, 0.90]):
            p = curr_p * r
            q = int((limit/5)/p)
            if q >= 1: buy_table.append({"단계": f"{i+1}차", "가격": f"${p:.2f}", "수량": f"{q}주", "필요금액": f"${p*q:.0f}"})
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
        else: st.info("보유 수량 없음")

# --- [Tab 2: 차트] ---
with tab2:
    if not df.empty:
        c_df = df.copy()
        c_df['Date'] = pd.to_datetime(c_df['Date']).dt.normalize()
        now_date = pd.to_datetime(datetime.now().date())
        now_df = pd.DataFrame([{"Date": now_date, "V_old": v_final, "Qty": qty, "Price": curr_p, "Band": int(b_pct*100)}])
        plot_df = pd.concat([c_df, now_df], ignore_index=True)
        plot_df = plot_df.drop_duplicates(subset=['Date'], keep='last').sort_values('Date')
        plot_df = plot_df[plot_df["V_old"] > 0]
        
        plot_df["상단"] = plot_df["V_old"] * (1 + plot_df["Band"]/100.0)
        plot_df["하단"] = plot_df["V_old"] * (1 - plot_df["Band"]/100.0)
        plot_df["자산"] = plot_df["Qty"] * plot_df["Price"]
        plot_df = plot_df[plot_df["자산"] > 0]
        
        fig = go.Figure()
        last_d, last_v, last_t, last_b = plot_df['Date'].max(), plot_df['V_old'].iloc[-1], plot_df['상단'].iloc[-1], plot_df['하단'].iloc[-1]
        future_d = last_d + timedelta(days=60)
        
        fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['상단'], line=dict(color='#00FF00', width=1.5), name='매도 밴드'))
        fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['하단'], line=dict(color='#00FF00', width=1.5), fill='tonexty', fillcolor='rgba(0, 255, 0, 0.05)', name='매수 밴드'))
        fig.add_trace(go.Scatter(x=[last_d, future_d], y=[last_t, last_t], line=dict(color='#00FF00', width=1.5), showlegend=False))
        fig.add_trace(go.Scatter(x=[last_d, future_d], y=[last_b, last_b], line=dict(color='#00FF00', width=1.5), showlegend=False))
        fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['V_old'], line=dict(color='#00BFFF', width=2, dash='dot'), name='목표 가치(V)'))
        fig.add_trace(go.Scatter(x=[last_d, future_d], y=[last_v, last_v], line=dict(color='#00BFFF', width=2, dash='dot'), showlegend=False))
        fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['자산'], line=dict(color='#FFFF00', width=3), mode='lines+markers', name='내 주식 가치(E)'))
        
        y_vals = pd.concat([plot_df["상단"], plot_df["하단"], plot_df["자산"]])
        y_range = [y_vals.min()*0.9, y_vals.max()*1.1]
        fig.update_layout(height=500, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', xaxis=dict(tickformat='%y-%m-%d', range=[plot_df['Date'].min() - timedelta(days=1), future_d]), yaxis=dict(range=y_range, fixedrange=False))
        st.plotly_chart(fig, use_container_width=True)

# --- [Tab 3: 매뉴얼] ---
with tab3:
    st.markdown("### 📖 TQQQ VR 5.0 (Pool형) 공식 매뉴얼")
    
    with st.container():
        st.markdown('<div class="manual-section">', unsafe_allow_html=True)
        st.markdown("#### 1️⃣ 최초 시작 (Setting Up)")
        st.markdown("""
        * **언제?** VR 투자를 처음 시작하거나 모든 데이터를 초기화하고 싶을 때 사용합니다.
        * **자산 배분:** 총 자산이 5,000달러라면, **현금 50%($2,500) / 주식 50%($2,500)** 비중으로 매수한 뒤 시작하는 것이 가장 안전합니다.
        * **입력:** '최초 시작' 모드 선택 → 보유한 주식 수량과 남은 현금을 입력 후 저장하세요.
        * **결과:** 이 시점의 내 주식 가치가 시스템의 첫 번째 기준점($V$)이 됩니다.
        """)
        st.markdown('</div>', unsafe_allow_html=True)

    with st.container():
        st.markdown('<div class="manual-section">', unsafe_allow_html=True)
        st.markdown("#### 2️⃣ 사이클 업데이트 (Cycle Update)")
        st.markdown("""
        * **언제?** 2주간의 매매가 끝난 후, 새로운 2주 계획을 짤 때 사용합니다.
        * **현금 관리:** `현재 계좌 현금`에는 지난 매매 후 남은 잔액을 적고, `신규 적립금`에는 이번 주기에 새로 입금할 금액을 적으세요. 시스템이 알아서 합산하여 $V$값을 계산합니다.
        * **공식:** $V_{new} = V_{old} + (Pool / G) + \text{신규 적립금}$
        * **결과:** 적립금이 목표치($V$)에 녹아들며 주가가 떨어졌을 때 더 많이 매수하도록 유도합니다.
        """)
        st.markdown('</div>', unsafe_allow_html=True)

    with st.container():
        st.markdown('<div class="tip-box">', unsafe_allow_html=True)
        st.markdown("#### 💡 실전 운용 규칙")
        st.markdown("""
        - **현금 사용 한도:** 적립식 투자자는 매달 추가 자금이 들어오므로 하락장에서 **현금의 75%**까지 과감히 투입합니다.
        - **기울기(G):** 복리 효과를 위해 기본값 **10**을 권장합니다.
        - **매매 방법:** 2주에 한 번, 월요일 아침에 앱이 계산해준 가격으로 **LOC(매수)**와 **지정가(매도)** 예약 주문을 걸어두고 생업에 집중하세요.
        """)
        st.markdown('</div>', unsafe_allow_html=True)
