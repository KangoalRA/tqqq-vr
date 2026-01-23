import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime
import requests
from streamlit_gsheets import GSheetsConnection

# --- [0. 화면 설정] ---
st.set_page_config(page_title="TQQQ VR 5.0 Pro", layout="wide")

# CSS: 상단 여백 제거 및 메트릭 강조
st.markdown("""
    <style>
        .block-container {padding-top: 1rem; padding-bottom: 1rem;}
        div[data-testid="stMetricValue"] {font-size: 1.4rem; font-weight: bold;}
    </style>
""", unsafe_allow_html=True)

# 텔레그램 전송
def send_telegram_msg(msg):
    try:
        if "telegram" in st.secrets:
            token = st.secrets["telegram"]["bot_token"]
            chat_id = st.secrets["telegram"]["chat_id"]
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(url, data={"chat_id": chat_id, "text": msg})
            st.toast("✅ 전송 완료", icon="✈️")
        else:
            st.error("텔레그램 설정 없음")
    except Exception as e:
        st.error(f"오류: {e}")

# 데이터 로드
@st.cache_data(ttl=300)
def get_market_data():
    data = {"price": 0.0, "fx": 1450.0} # 기본값 안전장치
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
    st.header("⚙️ VR 5.0 설정")
    
    # 성향 & 변수
    invest_type = st.radio("투자 성향", ["적립식 (Limit 75%)", "거치식 (Limit 50%)"])
    pool_cap = 0.75 if "적립식" in invest_type else 0.50
    
    c1, c2 = st.columns(2)
    with c1: g_factor = st.number_input("G값", value=10, min_value=1)
    with c2: band_pct = st.number_input("밴드(%)", value=15) / 100.0
    
    st.markdown("---")
    
    # 데이터 로드
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = pd.DataFrame()
    last_v, last_pool, last_qty, last_princ = 0.0, 0.0, 0, 0.0
    last_date = ""

    try:
        df = conn.read(worksheet="Sheet1", ttl=0)
        if not df.empty:
            row = df.iloc[-1]
            # 쉼표 제거 및 형변환 안전장치
            def clean_num(x): return float(str(x).replace(',','')) if str(x).replace(',','').replace('.','').isdigit() else 0.0
            
            last_qty = int(clean_num(row.get("Qty", 0)))
            last_pool = clean_num(row.get("Pool", 0))
            last_v = clean_num(row.get("V_old", 0))
            last_princ = clean_num(row.get("Principal", 0))
            last_date = str(row.get("Date", ""))
            st.success(f"로드됨: {last_date}")
    except: pass

    # 입력 폼
    mode = st.radio("모드", ["갱신 (2주 1회)", "초기화 (Reset)"], horizontal=True)
    
    price = st.number_input("TQQQ 현재가($)", value=m["price"] if m["price"]>0 else 0.0, format="%.2f")
    fx = st.number_input("환율(￦/$)", value=m["fx"])
    
    qty = st.number_input("보유 수량", value=last_qty)
    pool = st.number_input("보유 현금($)", value=last_pool)
    
    # --- [V값 계산 로직 수정] ---
    v_new, princ_new, growth = 0.0, last_princ, 0.0
    
    if mode == "초기화 (Reset)":
        princ_new = st.number_input("총 원금($)", value=last_princ)
        if price > 0:
            v_new = price * qty # 초기값은 현재 평가금
        else:
            v_new = 0
            st.error("현재가를 입력해야 V값 계산됨")
    else:
        # 갱신 모드: 무조건 이전 V값 기반
        if last_v <= 0:
            st.warning("이전 V값이 0입니다. 초기화 모드를 먼저 실행하세요.")
            v_new = price * qty
        else:
            add_usd = st.number_input("추가 투입금($)", value=0.0)
            princ_new += add_usd
            
            # 성장 로직
            if pool > 0: growth = pool / g_factor
            v_new = last_v + growth + add_usd

    # 저장 버튼
    if st.button("💾 데이터 저장", use_container_width=True):
        new_row = pd.DataFrame([{
            "Date": datetime.now().strftime('%Y-%m-%d'),
            "Qty": qty, "Pool": pool, "V_old": v_new, "Principal": princ_new,
            "Price": price, "Band": int(band_pct*100)
        }])
        final_df = pd.concat([df, new_row], ignore_index=True) if not df.empty else new_row
        conn.update(worksheet="Sheet1", data=final_df.fillna(0))
        st.success("저장 완료!")
        st.rerun()

# --- [메인 대시보드] ---
if price <= 0: st.stop()

eval_usd = price * qty
total_usd = eval_usd + pool
roi = ((total_usd - princ_new)/princ_new*100) if princ_new>0 else 0

st.title("🌊 TQQQ VR 5.0 Pro")

# 메트릭
c1, c2, c3, c4 = st.columns(4)
c1.metric("New V값 (목표)", f"${v_new:,.0f}", f"+${growth:,.0f}")
c2.metric("총 자산", f"${total_usd:,.0f}")
c3.metric("Pool", f"${pool:,.0f}")
c4.metric("수익률", f"{roi:.2f}%")

tab1, tab2 = st.tabs(["📋 매매 가이드", "📈 누적 차트"])

with tab1:
    col_buy, col_sell = st.columns(2)
    
    # [매수]
    with col_buy:
        st.subheader("🔵 매수 (LOC)")
        limit = pool * pool_cap
        st.caption(f"가용: ${limit:,.0f} ({int(pool_cap*100)}%)")
        
        buy_list = []
        steps = [0.98, 0.96, 0.94, 0.92, 0.90]
        used = 0
        for i, r in enumerate(steps):
            p = price * r
            q = int((limit/5)/p)
            if q < 1: q = 1
            cost = p * q
            if used + cost <= limit:
                buy_list.append({"구분": f"LOC {i+1}", "가격": f"${p:.2f}", "수량": f"{q}주", "금액": f"${cost:.0f}"})
                used += cost
            else: break
        st.dataframe(pd.DataFrame(buy_list), hide_index=True, use_container_width=True)

    # [매도]
    with col_sell:
        st.subheader("🔴 매도 (지정가)")
        v_upper = v_new * (1 + band_pct)
        st.caption(f"밴드상단: ${v_upper:,.0f}")
        
        sell_list = []
        if qty > 0:
            target_p = v_upper / qty
            if price >= target_p:
                excess = eval_usd - v_new
                q_sell = int(excess / price)
                st.error(f"🚨 밴드돌파! {q_sell}주 즉시 매도")
            else:
                excess = v_upper - v_new
                q_sell = int(excess / target_p)
                sell_list.append({"구분": "밴드상단", "목표가": f"${target_p:.2f}", "매도량": f"{q_sell}주"})
        
        if sell_list:
            st.dataframe(pd.DataFrame(sell_list), hide_index=True, use_container_width=True)
        elif qty > 0 and price < target_p:
            st.info("✅ 밴드 안쪽 (관망)")

    if st.button("✈️ 텔레그램 전송", use_container_width=True):
        msg = f"VR 5.0\nTQQQ: ${price}\nV: ${v_new:,.0f}\n자산: ${total_usd:,.0f}"
        send_telegram_msg(msg)

with tab2:
    # --- [차트 로직 전면 수정] ---
    if not df.empty and "V_old" in df.columns:
        # 데이터 정리
        chart_df = df.copy()
        chart_df['Date'] = pd.to_datetime(chart_df['Date'])
        
        # 현재 시점 데이터 추가 (Projection)
        now_row = pd.DataFrame([{
            "Date": datetime.now(),
            "V_old": v_new,
            "Qty": qty, "Price": price, "Band": int(band_pct*100)
        }])
        chart_df = pd.concat([chart_df, now_row], ignore_index=True)
        
        # 밴드 계산
        chart_df["V_Max"] = chart_df["V_old"] * (1 + chart_df["Band"]/100.0)
        chart_df["V_Min"] = chart_df["V_old"] * (1 - chart_df["Band"]/100.0)
        chart_df["My_Asset"] = chart_df["Qty"] * chart_df["Price"]
        
        # 시각화 (노란색 밴드 라인 적용)
        fig = go.Figure()

        # 1. 밴드 상단선 (노랑)
        fig.add_trace(go.Scatter(
            x=chart_df['Date'], y=chart_df['V_Max'],
            mode='lines', line=dict(color='yellow', width=1.5), # 선 두께 줌
            name='Band Max'
        ))

        # 2. 밴드 하단선 (노랑) + 채우기
        fig.add_trace(go.Scatter(
            x=chart_df['Date'], y=chart_df['V_Min'],
            mode='lines', line=dict(color='yellow', width=1.5), # 선 두께 줌
            fill='tonexty', fillcolor='rgba(255, 255, 0, 0.1)', # 노란색 틴트
            name='Band Min'
        ))

        # 3. V값 (빨강)
        fig.add_trace(go.Scatter(
            x=chart_df['Date'], y=chart_df['V_old'],
            mode='lines+markers', line=dict(color='red', width=2),
            name='목표(V)'
        ))

        # 4. 내 자산 (파랑/형광)
        fig.add_trace(go.Scatter(
            x=chart_df['Date'], y=chart_df['My_Asset'],
            mode='lines+markers', line=dict(color='#00CCFF', width=3),
            marker=dict(size=8),
            name='내 자산'
        ))

        fig.update_layout(
            height=500,
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            xaxis=dict(showgrid=True, gridcolor='rgba(128,128,128,0.2)'),
            yaxis=dict(showgrid=True, gridcolor='rgba(128,128,128,0.2)'),
            legend=dict(orientation="h", y=1.1)
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("데이터가 저장되면 차트가 표시됩니다.")
