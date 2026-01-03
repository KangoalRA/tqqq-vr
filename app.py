import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
from streamlit_gsheets import GSheetsConnection

# --- [0. 기본 설정] ---
st.set_page_config(page_title="TQQQ VR 5.0 Pro", layout="wide")

# 텔레그램 메시지 전송
def send_telegram_msg(msg):
    try:
        if "telegram" in st.secrets:
            token = st.secrets["telegram"]["bot_token"]
            chat_id = st.secrets["telegram"]["chat_id"]
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            data = {"chat_id": chat_id, "text": msg}
            requests.post(url, data=data)
            st.toast("✅ 텔레그램 전송 성공!", icon="✈️")
        else:
            st.warning("텔레그램 설정이 없습니다. (secrets.toml 확인)")
    except Exception as e:
        st.error(f"텔레그램 전송 오류: {e}")

# 데이터 가져오기 (실패 시 기본값 반환)
@st.cache_data(ttl=300)
def get_market_intelligence():
    data = {"price": 0.0, "fx": 1400.0, "dd": 0.0, "fng": 50.0, "bull": True, "error": None}
    try:
        # TQQQ 가격
        t_hist = yf.Ticker("TQQQ").history(period="5d")
        if not t_hist.empty: 
            data["price"] = round(t_hist['Close'].iloc[-1], 2)
        else:
            data["error"] = "TQQQ 데이터 로드 실패"
        
        # 나스닥
        n_hist = yf.Ticker("^NDX").history(period="2y")
        if not n_hist.empty:
            ndx_high = n_hist['Close'].max()
            curr_ndx = n_hist['Close'].iloc[-1]
            data["dd"] = round((curr_ndx / ndx_high - 1) * 100, 2)
            data["bull"] = curr_ndx > n_hist['Close'].rolling(window=200).mean().iloc[-1]
        
        # 환율
        fx_hist = yf.Ticker("USDKRW=X").history(period="1d")
        if not fx_hist.empty: 
            data["fx"] = round(fx_hist['Close'].iloc[-1], 2)

        # 공포지수
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            r = requests.get("https://production.dataviz.cnn.io/index/fearandgreed/static/history", headers=headers, timeout=3)
            if r.status_code == 200: 
                data["fng"] = float(r.json()['fear_and_greed']['score'])
        except: pass
        
        return data
    except Exception as e: 
        data["error"] = str(e)
        return data

m = get_market_intelligence()

# --- [UI 강제 표시 로직] ---
# 데이터를 못 가져왔어도 UI는 무조건 그리도록 구조 변경
st.title("🚀 TQQQ VR 5.0 Pro")

# 에러가 있거나 가격이 0원이면 수동 모드로 전환 경고
if m["price"] == 0 or m["error"]:
    st.warning(f"⚠️ 시장 데이터를 자동으로 가져오지 못했습니다. (원인: {m.get('error', 'API 연결 실패')}) -> 수동 입력값을 사용합니다.")

# --- [사이드바 설정] ---
with st.sidebar:
    st.header("⚙️ 기본 설정")
    
    # G값 & 밴드
    g_factor = st.slider("1. G값 (성장 속도)", 10, 40, 10, help="낮을수록(10) 공격적, 높을수록(40) 보수적")
    band_pct = st.slider("2. 밴드폭 (%)", 5, 30, 15) / 100

    st.divider()

    # 시장 데이터 (자동 실패시 수동 입력 가능하게 변경)
    st.subheader("3. 시장 데이터 (수동 수정 가능)")
    
    # 가격이 0이면 기본값 0.0 대신 사용자가 입력하게 유도
    price_val = m["price"] if m["price"] > 0 else 0.0
    current_price = st.number_input("TQQQ 현재가 ($)", value=price_val, format="%.2f")
    
    mdd_val = st.number_input("나스닥 MDD (%)", value=m["dd"], format="%.2f")
    fng_val = st.number_input("FnG 지수 (0~100)", value=float(m["fng"]))
    fx_val = st.number_input("환율 (원/$)", value=m["fx"])
    
    # 데이터 덮어쓰기 (사용자 입력값 우선)
    m["price"] = current_price
    m["dd"] = mdd_val
    m["fng"] = fng_val
    m["fx"] = fx_val

    st.divider()
    
    # 구글 시트 로드
    st.subheader("4. 자산 데이터")
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    df = pd.DataFrame()
    default_qty, default_pool, default_v, default_principal = 100, 2000.0, m["price"]*100, 5000.0
    last_date = "없음"

    try:
        df = conn.read(worksheet="Sheet1", ttl=0)
        if not df.empty and len(df.columns) >= 4:
            last_row = df.iloc[-1]
            try: default_qty = int(float(str(last_row.iloc[0]).replace(',','')))
            except: pass
            try: default_pool = float(str(last_row.iloc[1]).replace(',',''))
            except: pass
            try: default_v = float(str(last_row.iloc[2]).replace(',',''))
            except: pass
            try: default_principal = float(str(last_row.iloc[3]).replace(',',''))
            except: pass
            if len(df.columns) > 4: last_date = str(last_row.iloc[4])
            st.success(f"✅ 로드됨 ({last_date})")
        else:
            st.info("ℹ️ 데이터 없음 (신규)")
    except:
        st.warning("⚠️ 시트 연결 실패 (설정 확인 필요)")

    mode = st.radio("모드", ["사이클 업데이트", "최초 시작"])
    
    qty = st.number_input("보유 수량 (주)", value=default_qty, min_value=0)
    pool = st.number_input("현금 Pool ($)", value=default_pool)

    # 계산 로직
    v_final = 0.0
    principal_final = default_principal
    
    # 최초 시작 모드
    if mode == "최초 시작":
        principal_final = st.number_input("총 투입 원금 ($)", value=default_principal)
        if current_price > 0:
            v_final = current_price * qty
        else:
            st.error("현재가를 입력해야 V값 계산이 됩니다.")
            v_final = 0
            
    # 업데이트 모드
    else:
        v_old = default_v
        st.markdown(f"**직전 V: ${v_old:,.2f}**")
        
        cur = st.radio("리필(적립)", ["없음", "원화", "달러"], horizontal=True)
        add_val = 0.0
        if cur == "원화":
            add_krw = st.number_input("입금액 (원)", value=0)
            add_val = add_krw / fx_val if fx_val > 0 else 0
            principal_final += add_krw
        elif cur == "달러":
            add_usd = st.number_input("입금액 ($)", value=0.0)
            add_val = add_usd
            principal_final += (add_usd * fx_val)
        
        # 성장 로직 (G값 적용)
        if v_old > 0 and pool > 0:
            # 공식: (Pool/V) / (G/10)
            base_growth = (pool / v_old) / (g_factor / 10.0) / 10.0 
            # 단순화된 요청 공식: (Pool/V) / G 로 변환하여 적용
            # 사용자 요청: 10~40으로 나눈다.
            # Pool비중 = Pool / V
            # 성장률 = Pool비중 / G
            target_growth_rate = (pool / v_old) / g_factor
            
            # 추가 성장 (+0.5% if 평가금 > V)
            bonus = 0.005 if (current_price * qty) > v_old else 0.0
            
            total_rate = target_growth_rate + bonus
            growth_amt = v_old * total_rate
            
            v_final = v_old + growth_amt + add_val
            st.info(f"📈 성장: {total_rate*100:.2f}% (+${growth_amt:.2f})")
        else:
            v_final = v_old + add_val

    # 저장 버튼
    if st.button("💾 시트 저장"):
        new_row = pd.DataFrame([{
            "Qty": qty, "Pool": pool, "V_old": v_final, 
            "Principal": principal_final, 
            "Date": datetime.now().strftime('%Y-%m-%d'), 
            "FnG": fng_val
        }])
        
        final_df = pd.concat([df, new_row], ignore_index=True) if not df.empty else new_row
        final_df = final_df.fillna("")
        conn.update(worksheet="Sheet1", data=final_df)
        st.success("✅ 저장 완료!")
        st.rerun()

# --- [메인 화면 표시] ---
# 가격이 0이면 화면을 그릴 수 없음 -> 경고문 출력
if current_price <= 0:
    st.error("👈 사이드바에서 'TQQQ 현재가'를 입력해주세요.")
    st.stop()

# 밴드 계산
v_min = v_final * (1 - band_pct)
v_max = v_final * (1 + band_pct)

# 안전장치 함수
def check_safety(dd, fng):
    if dd > -10: return True, 1.0, "🟩 정상장 (100%)", "normal"
    elif -20 < dd <= -10:
        return (True, 0.5, "🟧 조정장 (50%)", "warning") if fng <= 15 else (False, 0.0, f"🚫 매수금지 (FnG {fng}>15)", "error")
    else:
        return (True, 0.3, "🟥 하락장 (30%)", "critical") if fng <= 10 else (False, 0.0, f"🚫 하락장 방어 (FnG {fng}>10)", "error")

is_safe, quota, status_msg, status_type = check_safety(mdd_val, fng_val)

# 자산 현황
curr_asset_usd = (current_price * qty) + pool
curr_asset_krw = curr_asset_usd * fx_val
roi_val = curr_asset_krw - principal_final
roi_pct = (roi_val / principal_final * 100) if principal_final > 0 else 0

st.subheader(f"📊 TQQQ: ${current_price} (FnG: {int(fng_val)})")
c1, c2, c3 = st.columns(3)
c1.metric("원금", f"{principal_final:,.0f}원")
c2.metric("평가금", f"{curr_asset_krw:,.0f}원", delta=f"{roi_val:,.0f}원")
c3.metric("수익률", f"{roi_pct:.2f}%")

st.divider()

tab1, tab2 = st.tabs(["📢 가이드", "차트"])

with tab1:
    if status_type == "normal": st.success(status_msg)
    elif status_type == "warning": st.warning(status_msg)
    else: st.error(status_msg)
    
    col_buy, col_sell = st.columns(2)
    
    report_txt = f"VR5.0 / G={g_factor} / Band={int(band_pct*100)}%\n"
    report_txt += f"TQQQ: ${current_price} / V: ${v_final:.1f}\n"
    
    with col_buy:
        st.markdown("#### 매수 (Buy)")
        if (current_price * qty) < v_min:
            if is_safe:
                st.write(f"✅ 쿼터: {quota*100}%")
                for i in range(1, 10):
                    t_q = qty + i
                    p = v_min / t_q
                    if p < current_price * 1.05:
                        line = f"LOC 매수: {p:.2f}$ ({t_q}주)"
                        st.code(line)
                        report_txt += line + "\n"
            else:
                st.error("FnG 위험: 매수 금지")
        else:
            st.info("관망")

    with col_sell:
        st.markdown("#### 매도 (Sell)")
        if (current_price * qty) > v_max:
            for i in range(1, 10):
                t_q = qty - i
                if t_q <= 0: break
                p = v_final / t_q
                if p > current_price * 0.95:
                    line = f"LOC 매도: {p:.2f}$ ({qty-t_q}주 팜)"
                    st.code(line)
                    report_txt += line + "\n"
        else:
            st.info("관망")
            
    if st.button("텔레그램 전송"):
        send_telegram_msg(report_txt)

with tab2:
    fig = go.Figure()
    dates = [datetime.now().date(), datetime.now().date() + timedelta(days=14)]
    fig.add_trace(go.Scatter(x=dates, y=[v_min, v_min], name="Min", line=dict(color='red', dash='dash')))
    fig.add_trace(go.Scatter(x=dates, y=[v_max, v_max], name="Max", line=dict(color='green', dash='dash')))
    fig.add_trace(go.Scatter(x=dates, y=[v_final, v_final], name="V", line=dict(color='blue')))
    fig.add_trace(go.Scatter(x=[dates[0]], y=[current_price*qty], name="내자산", marker=dict(size=12, color='orange')))
    fig.update_layout(height=350, margin=dict(l=10, r=10, t=30, b=10))
    st.plotly_chart(fig, use_container_width=True)
