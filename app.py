import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime
import requests
from streamlit_gsheets import GSheetsConnection

# --- [0. 화면 설정] ---
st.set_page_config(page_title="TQQQ VR 5.0 공식 시스템", layout="wide")

st.markdown("""
    <style>
        .block-container {padding-top: 1rem; padding-bottom: 1rem;}
        div[data-testid="stMetricValue"] {font-size: 1.5rem !important; font-weight: 700;}
    </style>
""", unsafe_allow_html=True)

# 텔레그램 알림
def send_telegram_msg(msg):
    try:
        if "telegram" in st.secrets:
            token = st.secrets["telegram"]["bot_token"]
            chat_id = st.secrets["telegram"]["chat_id"]
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(url, data={"chat_id": chat_id, "text": msg})
            st.toast("✅ 가이드 전송 완료")
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
    st.header("📊 VR 5.0 시스템 설정")
    
    invest_type = st.radio("투자 성향", ["적립식 (75% 한도)", "거치식 (50% 한도)"])
    pool_cap = 0.75 if "적립식" in invest_type else 0.50
    
    c1, c2 = st.columns(2)
    with c1: g_val = st.number_input("기울기(G)", value=10, min_value=1)
    with c2: b_pct = st.number_input("밴드폭(%)", value=15) / 100.0
    
    st.divider()
    
    # 데이터 로드
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = pd.DataFrame()
    last_v, last_princ = 0.0, 0.0
    
    try:
        df = conn.read(worksheet="Sheet1", ttl=0)
        if not df.empty:
            row = df.iloc[-1]
            last_v = float(str(row.get("V_old", 0)).replace(',',''))
            last_princ = float(str(row.get("Principal", 0)).replace(',',''))
            st.success(f"이전 데이터 로드 완료")
    except: pass

    mode = st.radio("작업 선택", ["사이클 업데이트", "최초 시작"], horizontal=True)
    
    curr_p = st.number_input("TQQQ 현재가($)", value=m["price"], format="%.2f")
    curr_fx = st.number_input("현재 환율(원)", value=m["fx"])
    
    qty = st.number_input("보유 수량(주)", value=0)
    pool = st.number_input("현금 Pool($)", value=0.0)
    
    # 공식 적용
    v_final, princ_final, growth = 0.0, last_princ, 0.0
    
    if mode == "최초 시작":
        princ_final = st.number_input("초기 원금($)", value=0.0)
        v_final = curr_p * qty
    else:
        add_usd = st.number_input("신규 적립($)", value=0.0)
        princ_final += add_usd
        if pool > 0: growth = pool / g_val
        v_final = last_v + growth + add_usd 

    if st.button("💾 시트에 기록 저장", use_container_width=True):
        new_row = pd.DataFrame([{
            "Date": datetime.now().strftime('%Y-%m-%d'),
            "Qty": qty, "Pool": pool, "V_old": v_final, "Principal": princ_final,
            "Price": curr_p, "Band": int(b_pct*100)
        }])
        final_df = pd.concat([df, new_row], ignore_index=True) if not df.empty else new_row
        conn.update(worksheet="Sheet1", data=final_df.fillna(0))
        st.success("데이터가 저장되었습니다.")
        st.rerun()

# --- [메인 대시보드] ---
if curr_p <= 0: st.stop()

eval_usd = curr_p * qty
total_usd = eval_usd + pool
roi = ((total_usd - princ_final)/princ_final*100) if princ_final>0 else 0

st.title("🚀 TQQQ VR 5.0 자산관리")

c1, c2, c3, c4 = st.columns(4)
c1.metric("새 목표값 (V)", f"${v_final:,.0f}", f"+${growth:,.0f} 성장")
c2.metric("총 자산 (E+P)", f"${total_usd:,.0f}")
c3.metric("가용 현금 (Pool)", f"${pool:,.0f}")
c4.metric("현재 수익률", f"{roi:.2f}%")

tab1, tab2 = st.tabs(["📋 실전 매매 가이드", "📈 자산 성장 차트"])

with tab1:
    col_buy, col_sell = st.columns(2)
    with col_buy:
        st.subheader("🔵 매수 예약 (LOC)")
        limit_amt = pool * pool_cap
        buy_table = []
        steps = [0.98, 0.96, 0.94, 0.92, 0.90]
        used = 0
        for i, r in enumerate(steps):
            p_loc = curr_p * r
            q_loc = int((limit_amt / 5) / p_loc)
            if q_loc >= 1:
                cost = p_loc * q_loc
                if used + cost <= limit_amt:
                    buy_table.append({"순서": f"{i+1}차", "지정가(LOC)": f"${p_loc:.2f}", "수량": f"{q_loc}주", "필요금액": f"${cost:.0f}"})
                    used += cost
        st.table(pd.DataFrame(buy_table))

    with col_sell:
        st.subheader("🔴 수익 실현 (지정가)")
        v_max = v_final * (1 + b_pct)
        if qty > 0:
            target_p = v_max / qty
            if curr_p >= target_p:
                excess = eval_usd - v_final
                st.error(f"🚨 **밴드 돌파!** {int(excess/curr_p)}주 매도하여 수익을 확정하세요.")
            else:
                st.success(f"매도 목표가: **${target_p:.2f}**")
                st.write(f"도달 시 약 {int((v_max - v_final)/target_p)}주 리밸런싱 매도")
        else: st.info("보유 주식이 없습니다.")

with tab2:
    if not df.empty:
        c_df = df.copy()
        c_df['Date'] = pd.to_datetime(c_df['Date'])
        # 실시간 프로젝션 데이터 합치기
        now_df = pd.DataFrame([{"Date": datetime.now(), "V_old": v_final, "Qty": qty, "Price": curr_p, "Band": int(b_pct*100)}])
        c_df = pd.concat([c_df, now_df], ignore_index=True)
        
        # 차트 수치 계산
        c_df["상단밴드"] = c_df["V_old"] * (1 + c_df["Band"]/100.0)
        c_df["하단밴드"] = c_df["V_old"] * (1 - c_df["Band"]/100.0)
        c_df["주식가치"] = c_df["Qty"] * c_df["Price"]
        
        fig = go.Figure()
        # 밴드 라인 (노랑)
        fig.add_trace(go.Scatter(x=c_df['Date'], y=c_df['상단밴드'], line=dict(color='yellow', width=1), name='매도 밴드'))
        fig.add_trace(go.Scatter(x=c_df['Date'], y=c_df['하단밴드'], line=dict(color='yellow', width=1), fill='tonexty', fillcolor='rgba(255, 255, 0, 0.05)', name='매수 밴드'))
        # 목표선 (빨강)
        fig.add_trace(go.Scatter(x=c_df['Date'], y=c_df['V_old'], line=dict(color='red', width=2), name='목표 가치(V)'))
        # 내 자산 (하늘색)
        fig.add_trace(go.Scatter(x=c_df['Date'], y=c_df['주식가치'], line=dict(color='#00E5FF', width=3), name='내 주식 가치(E)'))
        
        fig.update_layout(
            title="VR 5.0 자산 성장 히스토리",
            height=450, 
            paper_bgcolor='rgba(0,0,0,0)', 
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color="white"), # 글자색 화이트 고정 (다크모드 대응)
            xaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.1)', title="날짜"),
            yaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.1)', title="금액 ($)"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig, use_container_width=True)
    else: st.info("저장된 데이터가 없습니다. 먼저 데이터를 저장해주세요.")
