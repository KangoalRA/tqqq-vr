import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection

# --- [0. 화면 설정] ---
st.set_page_config(page_title="TQQQ VR 5.0 (Final)", layout="wide")
st.markdown("""
    <style>
        .block-container {padding-top: 1.5rem; padding-bottom: 1rem;}
        div[data-testid="stMetricValue"] {font-size: 1.5rem !important; font-weight: 700;}
        .buy-signal { background-color: rgba(0, 255, 0, 0.1); padding: 15px; border-radius: 10px; border: 1px solid #00FF00; color: #00FF00; font-weight: bold; font-size: 1.2rem; text-align: center;}
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
    st.header("📊 VR 5.0 자금 관리 설정")
    
    # [최종 로직] 슬라이더 제거하고 룰대로 고정
    invest_type = st.radio(
        "투자 성향 선택", 
        ["적립식 (Pool 75% 사용)", "거치식 (Pool 50% 사용)", "인출식 (Pool 25% 사용)"]
    )
    
    if "적립식" in invest_type: pool_cap = 0.75
    elif "거치식" in invest_type: pool_cap = 0.50
    else: pool_cap = 0.25 # 인출식
    
    st.info(f"✅ **{invest_type[:3]}** 원칙에 따라 Pool의 **{int(pool_cap*100)}%** 만 사용합니다.")
    
    c1, c2 = st.columns(2)
    with c1: g_val = st.number_input("기울기(G)", value=10, min_value=1)
    with c2: b_pct = st.number_input("밴드폭(%)", value=15, min_value=5) / 100.0
    
    st.divider()
    
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
        st.markdown(f'<div class="buy-signal">💡 즉시 {qty}주 매수 (50:50 시작)</div>', unsafe_allow_html=True)
        
    else: # 사이클 업데이트
        base_pool = st.number_input("기존 계좌 현금 ($)", value=last_pool)
        add_usd = st.number_input("신규 입금액 ($)", value=0.0)
        final_pool = base_pool + add_usd
        princ_final = last_princ + add_usd
        if final_pool > 0: growth = final_pool / g_val
        v_final = last_v + growth + add_usd 

    if st.button("💾 데이터 저장 (Save)", use_container_width=True):
        new_row = pd.DataFrame([{"Date": datetime.now().strftime('%Y-%m-%d'), "Qty": qty, "Pool": final_pool, "V_old": v_final, "Principal": princ_final, "Price": curr_p, "Band": int(b_pct*100)}])
        final_df = pd.concat([df, new_row], ignore_index=True) if not df.empty else new_row
        conn.update(worksheet="Sheet1", data=final_df.fillna(0))
        st.success("저장 완료!")
        st.rerun()

# --- [메인 대시보드] ---
if curr_p <= 0: st.stop()
eval_usd = curr_p * qty
total_usd = eval_usd + final_pool
roi = ((total_usd - princ_final)/princ_final*100) if princ_final > 0 else 0
upper_band = v_final * (1 + b_pct)

st.title("🚀 TQQQ VR 5.0 Dashboard")

c1, c2, c3, c4 = st.columns(4)
c1.metric("목표 가치 (V)", f"${v_final:,.0f}", f"+${growth:,.0f}")
c2.metric("총 자산 (E+P)", f"${total_usd:,.0f}")
c3.metric("가용 현금 (Pool)", f"${final_pool:,.0f}")
c4.metric("수익률", f"{roi:.2f}%")

tab1, tab2, tab3 = st.tabs(["📋 자금 관리형 매수표", "📈 성장 히스토리", "📖 운용 매뉴얼"])

with tab1:
    col_buy, col_sell = st.columns(2)
    
    with col_buy:
        st.subheader("🔵 2주 균등 분할 매수")
        
        # [최종 로직] 선택된 모드에 따라 75% / 50% / 25% 자동 적용
        limit = final_pool * pool_cap 
        budget_per_step = limit / 5   # 5등분 (내 자금 맞춤)
        
        st.write(f"**💰 예산 설계 ({invest_type[:3]} 모드 적용)**")
        st.caption(f"총 예산: ${limit:,.0f} (Pool의 {int(pool_cap*100)}%) │ 단계별: ${budget_per_step:,.0f}")

        buy_table = []
        for i, r in enumerate([0.98, 0.96, 0.94, 0.92, 0.90]):
            p = curr_p * r
            q = int(budget_per_step / p) 
            if q >= 1:
                buy_table.append({
                    "단계": f"{i+1}차 (-{int((1-r)*100)}%)",
                    "가격": f"${p:.2f}",
                    "주문 수량": f"{q}주",
                    "예상 금액": f"${p*q:.0f}"
                })
        
        st.table(pd.DataFrame(buy_table))
        st.info("💡 **실전 지침:** 2주 기간 / 지정가 / 잔량 주문으로 위 수량을 예약하세요.")

    with col_sell:
        st.subheader("🔴 리밸런싱 매도")
        if eval_usd > upper_band:
            excess = eval_usd - v_final
            target_p = upper_band / qty if qty > 0 else 0
            st.error(f"🚨 상단 돌파! 중심(V) 복귀를 위해 약 {int(excess/curr_p)}주 매도하세요.")
        else:
            target_p = upper_band / qty if qty > 0 else 0
            st.info(f"매도 목표가 (밴드 상단): ${target_p:.2f}")

with tab2:
    # 차트 로직 (동일)
    if not df.empty:
        c_df = df.copy()
        c_df['Date'] = pd.to_datetime(c_df['Date']).dt.normalize()
        now_date = pd.to_datetime(datetime.now().date())
        now_df = pd.DataFrame([{"Date": now_date, "V_old": v_final, "Qty": qty, "Price": curr_p, "Band": int(b_pct*100)}])
        plot_df = pd.concat([c_df, now_df], ignore_index=True)
        plot_df = plot_df.drop_duplicates(subset=['Date'], keep='last').sort_values('Date')
        plot_df["상단"] = plot_df["V_old"] * (1 + plot_df["Band"]/100.0)
        plot_df["하단"] = plot_df["V_old"] * (1 - plot_df["Band"]/100.0)
        plot_df["자산"] = plot_df["Qty"] * plot_df["Price"]
        plot_df = plot_df[plot_df["자산"] > 0]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['상단'], line=dict(color='#00FF00', width=1), name='매도 밴드'))
        fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['하단'], line=dict(color='#FF4B4B', width=1), fill='tonexty', fillcolor='rgba(255, 75, 75, 0.05)', name='매수 밴드'))
        fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['V_old'], line=dict(color='#00BFFF', width=2, dash='dot'), name='중심선(V)'))
        fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['자산'], line=dict(color='#FFFF00', width=3), mode='lines+markers', name='내 자산(E)'))
        fig.update_layout(height=500, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig, use_container_width=True)

with tab3:
    st.markdown("### 📖 VR 5.0 자금 관리 원칙")
    st.markdown("""
    <div class="manual-section">
    <h4>🔒 투자 성향별 Pool 제한 (고정)</h4>
    <ul>
        <li><b>적립식 (75%):</b> 매달 돈이 들어오니 가장 공격적으로 매수합니다.</li>
        <li><b>거치식 (50%):</b> 추가 자금이 없으니 절반은 안전하게 남깁니다.</li>
        <li><b>인출식 (25%):</b> 은퇴 후 인출 단계에서는 생존을 위해 최소한만 매수합니다.</li>
    </ul>
    </div>
    """, unsafe_allow_html=True)
