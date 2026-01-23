import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime
import requests
from streamlit_gsheets import GSheetsConnection

# --- [0. 화면 설정 (여백 최소화)] ---
st.set_page_config(page_title="TQQQ VR 5.0", layout="wide")

# CSS로 상단 여백 강제 줄이기
st.markdown("""
    <style>
        .block-container {padding-top: 1rem; padding-bottom: 1rem;}
        div[data-testid="stMetricValue"] {font-size: 1.2rem;}
    </style>
""", unsafe_allow_html=True)

# 텔레그램 메시지 전송
def send_telegram_msg(msg):
    try:
        if "telegram" in st.secrets:
            token = st.secrets["telegram"]["bot_token"]
            chat_id = st.secrets["telegram"]["chat_id"]
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            data = {"chat_id": chat_id, "text": msg}
            requests.post(url, data=data)
            st.toast("✅ 전송 완료", icon="✈️")
        else:
            st.warning("텔레그램 설정 없음")
    except Exception as e:
        st.error(f"오류: {e}")

# 데이터 로드
@st.cache_data(ttl=300)
def get_market_data():
    data = {"price": 0.0, "fx": 1400.0, "error": None}
    try:
        t_hist = yf.Ticker("TQQQ").history(period="1d")
        if not t_hist.empty: data["price"] = round(t_hist['Close'].iloc[-1], 2)
        fx_hist = yf.Ticker("USDKRW=X").history(period="1d")
        if not fx_hist.empty: data["fx"] = round(fx_hist['Close'].iloc[-1], 2)
        return data
    except Exception as e:
        data["error"] = str(e)
        return data

m = get_market_data()

# --- [사이드바 (입력)] ---
with st.sidebar:
    st.header("⚙️ VR 5.0 설정")
    
    # 성향 & 변수 (한 줄로 모으기)
    invest_type = st.radio("투자 성향", ["적립식 (75%)", "거치식 (50%)"], index=0)
    pool_cap = 0.75 if "적립식" in invest_type else 0.50
    
    c1, c2 = st.columns(2)
    with c1: g_factor = st.number_input("G값", value=10, min_value=1)
    with c2: band_pct = st.number_input("밴드(%)", value=15) / 100.0
    
    st.markdown("---") # 구분선 최소화
    
    # 시장 데이터
    price = st.number_input("TQQQ 현재가($)", value=m["price"] if m["price"]>0 else 0.0, format="%.2f")
    fx = st.number_input("환율(￦/$)", value=m["fx"])
    
    st.markdown("---")
    
    # 데이터 로드 및 저장
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = pd.DataFrame()
    last_v, last_pool, last_qty, last_princ = 0.0, 0.0, 0, 0.0
    
    try:
        df = conn.read(worksheet="Sheet1", ttl=0)
        if not df.empty:
            row = df.iloc[-1]
            last_qty = int(str(row.get("Qty", 0)).replace(',',''))
            last_pool = float(str(row.get("Pool", 0)).replace(',',''))
            last_v = float(str(row.get("V_old", 0)).replace(',',''))
            last_princ = float(str(row.get("Principal", 0)).replace(',',''))
            st.success(f"로드: {row.get('Date','?')}")
    except: pass

    # 입력 폼
    mode = st.radio("모드", ["갱신", "초기화"], horizontal=True)
    qty = st.number_input("보유 수량", value=last_qty)
    pool = st.number_input("보유 현금($)", value=last_pool)
    
    # 계산
    v_new, princ_new, growth = 0.0, last_princ, 0.0
    
    if mode == "초기화":
        princ_new = st.number_input("원금($)", value=last_princ)
        v_new = price * qty if price > 0 else 0
    else:
        st.caption(f"이전 V: ${last_v:,.0f}")
        add_type = st.radio("추가금", ["X", "￦", "$"], horizontal=True)
        add_amt = 0.0
        if add_type == "￦":
            val = st.number_input("원화", value=0)
            add_amt = val / fx if fx > 0 else 0
        elif add_type == "$":
            add_amt = st.number_input("달러", value=0.0)
            
        princ_new += add_amt
        if pool > 0: growth = pool / g_factor
        v_new = last_v + growth + add_amt

    if st.button("💾 저장 (Save)", use_container_width=True):
        new_row = pd.DataFrame([{
            "Date": datetime.now().strftime('%Y-%m-%d'),
            "Qty": qty, "Pool": pool, "V_old": v_new, "Principal": princ_new,
            "Price": price, "Band": band_pct*100
        }])
        final_df = pd.concat([df, new_row], ignore_index=True) if not df.empty else new_row
        conn.update(worksheet="Sheet1", data=final_df.fillna(0))
        st.success("저장됨")
        st.rerun()

# --- [메인 화면 (밀도 높게)] ---
if price <= 0: st.stop()

# 자산 현황
eval_usd = price * qty
total_usd = eval_usd + pool
roi = ((total_usd - princ_new)/princ_new*100) if princ_new>0 else 0

st.title("🌊 VR 5.0 Dashboard")

# 메트릭 한 줄 배치
m1, m2, m3, m4 = st.columns(4)
m1.metric("New V값", f"${v_new:,.0f}", f"+${growth:,.0f}")
m2.metric("총 자산($)", f"${total_usd:,.0f}")
m3.metric("Pool($)", f"${pool:,.0f}")
m4.metric("수익률", f"{roi:.2f}%")

# 탭 구성 (간격 좁게)
tab1, tab2 = st.tabs(["📋 매매 가이드", "📈 누적 차트"])

with tab1:
    col_buy, col_sell = st.columns(2)
    
    # [매수 테이블]
    with col_buy:
        st.subheader("🔵 매수 (LOC)")
        limit_pool = pool * pool_cap
        st.caption(f"가용예산: ${limit_pool:,.0f} ({int(pool_cap*100)}%)")
        
        buy_data = []
        steps = [0.98, 0.96, 0.94, 0.92, 0.90]
        used = 0
        for i, r in enumerate(steps):
            p = price * r
            q = int((limit_pool/5)/p)
            if q < 1: q = 1
            cost = p * q
            if used + cost <= limit_pool:
                buy_data.append({"구분": f"LOC {i+1}", "가격": f"${p:.2f}", "수량": f"{q}주", "금액": f"${cost:.0f}"})
                used += cost
            else: break
            
        st.dataframe(pd.DataFrame(buy_data), hide_index=True, use_container_width=True)

    # [매도 테이블]
    with col_sell:
        st.subheader("🔴 매도 (지정가)")
        v_top = v_new * (1 + band_pct)
        st.caption(f"밴드상단: ${v_top:,.0f} (현재가대비 {((v_top/qty)/price - 1)*100:.1f}%↑)" if qty>0 else "보유량 없음")
        
        sell_data = []
        if qty > 0:
            target_p = v_top / qty
            if price >= target_p:
                excess = eval_usd - v_new
                q_sell = int(excess / price)
                st.error(f"🚨 밴드돌파! {q_sell}주 즉시매도")
            else:
                # 예약 매도
                excess_at_target = v_top - v_new
                q_sell = int(excess_at_target / target_p)
                sell_data.append({"구분": "밴드상단", "목표가": f"${target_p:.2f}", "매도량": f"{q_sell}주"})
                
        if sell_data:
            st.dataframe(pd.DataFrame(sell_data), hide_index=True, use_container_width=True)
        elif qty > 0 and price < target_p:
            st.info("✅ 밴드 안쪽 (관망)")

    if st.button("✈️ 텔레그램 전송", type="primary", use_container_width=True):
        msg = f"🌊 VR5.0\nTQQQ: ${price}\nV: ${v_new:,.0f}\n\n[매수 LOC]\n"
        for b in buy_data: msg += f"{b['가격']} ({b['수량']})\n"
        if qty > 0 and price < target_p: msg += f"\n[매도 예약]\n${target_p:.2f} ({q_sell}주)"
        send_telegram_msg(msg)

with tab2:
    if not df.empty and "Date" in df.columns and "V_old" in df.columns:
        # 데이터 전처리
        c_df = df.copy()
        c_df['Date'] = pd.to_datetime(c_df['Date'])
        if "Price" not in c_df: c_df["Price"] = 0
        if "Band" not in c_df: c_df["Band"] = 15
        
        # 밴드 계산
        c_df["V_High"] = c_df["V_old"] * (1 + c_df["Band"]/100.0)
        c_df["V_Low"] = c_df["V_old"] * (1 - c_df["Band"]/100.0)
        c_df["My_Eval"] = c_df["Qty"] * c_df["Price"]
        
        # 현재가 추가 (Projection)
        now_row = pd.DataFrame([{
            "Date": datetime.now(), "V_old": v_new, "My_Eval": eval_usd,
            "V_High": v_new*(1+band_pct), "V_Low": v_new*(1-band_pct)
        }])
        chart_df = pd.concat([c_df, now_row], ignore_index=True)

        # Plotly 차트 (다크모드 호환)
        fig = go.Figure()

        # 1. 밴드 영역 (투명도 조절로 다크/라이트 모두 호환되게)
        fig.add_trace(go.Scatter(
            x=chart_df['Date'], y=chart_df['V_High'], mode='lines', line=dict(width=0), showlegend=False
        ))
        fig.add_trace(go.Scatter(
            x=chart_df['Date'], y=chart_df['V_Low'], mode='lines', line=dict(width=0), 
            fill='tonexty', fillcolor='rgba(128, 128, 128, 0.2)', # 회색 반투명 (어디서든 무난)
            name='Band'
        ))

        # 2. V값 (중심선)
        fig.add_trace(go.Scatter(
            x=chart_df['Date'], y=chart_df['V_old'], mode='lines+markers',
            line=dict(color='#3366CC', width=3), name='목표(V)'
        ))

        # 3. 내 자산
        fig.add_trace(go.Scatter(
            x=chart_df['Date'], y=chart_df['My_Eval'], mode='lines+markers',
            line=dict(color='#FF9900', width=3), marker=dict(size=8), name='내 자산'
        ))

        # 레이아웃 설정 (배경 투명화)
        fig.update_layout(
            height=400,
            margin=dict(l=20, r=20, t=30, b=20),
            paper_bgcolor='rgba(0,0,0,0)', # 투명 배경
            plot_bgcolor='rgba(0,0,0,0)',  # 투명 배경
            xaxis=dict(showgrid=True, gridcolor='rgba(128,128,128,0.2)'), # 그리드 은은하게
            yaxis=dict(showgrid=True, gridcolor='rgba(128,128,128,0.2)'),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("데이터가 저장되면 차트가 표시됩니다.")
