import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
from streamlit_gsheets import GSheetsConnection

# --- [0. 페이지 설정] ---
st.set_page_config(page_title="TQQQ VR 5.0 투자 가이드", layout="wide")

# 텔레그램 메시지 전송
def send_telegram_msg(msg):
    try:
        token = st.secrets["telegram"]["bot_token"]
        chat_id = st.secrets["telegram"]["chat_id"]
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {"chat_id": chat_id, "text": msg}
        requests.post(url, data=data)
        st.toast("✅ 텔레그램 전송 완료!", icon="✈️")
    except:
        st.error("텔레그램 설정 확인 필요")

@st.cache_data(ttl=600)
def get_market_intelligence():
    data = {"price": 0.0, "fx": 1350.0, "dd": 0.0, "fng": 25.0, "bull": True}
    try:
        t_hist = yf.Ticker("TQQQ").history(period="5d")
        if not t_hist.empty: data["price"] = round(t_hist['Close'].iloc[-1], 2)
        
        n_hist = yf.Ticker("^NDX").history(period="2y")
        if not n_hist.empty:
            ndx_high = n_hist['Close'].max()
            curr_ndx = n_hist['Close'].iloc[-1]
            data["dd"] = round((curr_ndx / ndx_high - 1) * 100, 2)
            data["bull"] = curr_ndx > n_hist['Close'].rolling(window=200).mean().iloc[-1]
        
        fx_hist = yf.Ticker("USDKRW=X").history(period="1d")
        if not fx_hist.empty: data["fx"] = round(fx_hist['Close'].iloc[-1], 2)

        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            r = requests.get("https://production.dataviz.cnn.io/index/fearandgreed/static/history", headers=headers, timeout=3)
            if r.status_code == 200: data["fng"] = float(r.json()['fear_and_greed']['score'])
        except: pass
        return data
    except: return data

m = get_market_intelligence()

def check_safety(dd, fng):
    if dd > -10: return True, 1.0, "🟩 정상장: 쿼터 100%", "normal"
    elif -20 < dd <= -10:
        if fng <= 15: return True, 0.5, "🟧 조정장: 쿼터 50% (FnG 15↓)", "warning"
        else: return False, 0.0, f"🚫 매수 보류 (FnG {fng} > 15)", "error"
    else:
        if fng <= 10: return True, 0.3, "🟥 하락장: 쿼터 30% (FnG 10↓)", "critical"
        else: return False, 0.0, f"🚫 하락장 방어 (FnG {fng} > 10)", "error"

def get_recommended_band(dd, is_bull):
    if not is_bull or dd < -20: return 10, "🟥 하락/공포장 (추천: 10%)"
    elif -20 <= dd < -10: return 15, "🟧 조정장 (추천: 15%)"
    elif dd >= -10 and is_bull: return 20, "🟩 상승장 (추천: 20%)"
    return 15, "⬜ 일반 (추천: 15%)"

# --- [UI 시작] ---
st.title("🚀 TQQQ VR 5.0 가이드")

if m and m["price"] > 0:
    with st.sidebar:
        st.header("⚙️ VR 설정")
        
        st.subheader("1. 밴드폭(Band) 설정")
        rec_val, rec_msg = get_recommended_band(m['dd'], m['bull'])
        st.caption(rec_msg)
        band_pct = st.slider("밴드폭 설정 (%)", 10, 40, rec_val) / 100

        st.divider()

        st.subheader("2. 시장 데이터")
        st.metric("나스닥 낙폭", f"{m['dd']}%")
        st.markdown("[👉 FnG 확인 (CNN)](https://edition.cnn.com/markets/fear-and-greed)")
        fng_input = st.number_input("FnG Index 입력", value=float(m['fng']))
        
        st.divider()
        
        st.subheader("3. 자산 데이터")
        conn = st.connection("gsheets", type=GSheetsConnection)
        
        default_qty, default_pool, default_v, default_principal = 100, 2000.0, m['price']*100, 5000.0
        last_date, saved_fng = "-", "-"
        
        # [핵심 수정 1] 데이터프레임 로드 시 에러 방지 처리
        df = pd.DataFrame()
        try:
            df = conn.read(worksheet="Sheet1", ttl=0)
            # 데이터가 있고, 필수 컬럼(최소 1개 이상)이 있을 때만 처리
            if not df.empty and len(df.columns) >= 4:
                # 마지막 행 가져오기
                last_row = df.iloc[-1]
                
                # 값 파싱 (에러나면 기본값 유지)
                try: default_qty = int(last_row.iloc[0])
                except: pass
                try: default_pool = float(last_row.iloc[1])
                except: pass
                try: default_v = float(last_row.iloc[2])
                except: pass
                try: default_principal = float(last_row.iloc[3])
                except: pass
                
                # E열(날짜), F열(FnG) 확인
                if len(df.columns) > 4:
                    last_date = str(last_row.iloc[4])
                if len(df.columns) > 5:
                    saved_fng = str(last_row.iloc[5])
                
                st.success(f"✅ 로드됨 (Date: {last_date})")
            else:
                st.info("ℹ️ 기존 데이터 없음 (신규 시작)")
        except Exception as e:
            st.warning(f"⚠️ 데이터 로드 실패 (초기화 상태): {e}")

        mode = st.radio("모드 선택", ["사이클 업데이트", "최초 시작"])
        
        qty = st.number_input("현재 보유 수량 (주)", value=default_qty, min_value=1)
        pool = st.number_input("현재 현금 Pool ($)", value=default_pool)
        
        if mode == "최초 시작":
            principal = st.number_input("총 투입 원금 ($)", value=default_principal)
            v1 = m['price'] * qty
            v_to_save = v1 
        else:
            st.markdown(f"**직전 V값: ${default_v:,.2f}** (자동 적용)")
            v_old = default_v 
            principal = default_principal
            cur = st.radio("추가 적립금(리필)", ["없음", "원화", "달러"], horizontal=True)
            
            add_val = 0.0
            if cur == "원화":
                add_krw = st.number_input("입금액 (원)", value=0)
                add_val = add_krw / m['fx']
                principal += add_krw
            elif cur == "달러":
                add_usd = st.number_input("입금액 ($)", value=0.0)
                add_val = add_usd
                principal += (add_usd * m['fx'])

            v1 = v_old + add_val 
            v_to_save = v1
            
            if add_val > 0:
                st.info(f"💡 리필액 ${add_val:,.2f} 반영됨")

        # [핵심 수정 2] 저장 시 NaN(빈값) 제거 및 기존 컬럼 맞춤
        if st.button("💾 구글 시트에 저장"):
            # 새 데이터
            new_row = pd.DataFrame([{
                "Qty": qty, 
                "Pool": pool, 
                "V_old": v_to_save, 
                "Principal": principal,
                "Date": datetime.now().strftime('%Y-%m-%d'),
                "FnG": fng_input
            }])
            
            # 기존 데이터와 합치기
            if not df.empty:
                # 컬럼 이름 통일 (혹시 모를 헤더 불일치 방지)
                # 만약 기존 df에 'Date' 컬럼이 없으면 concat 과정에서 생김 -> NaN 발생
                updated_df = pd.concat([df, new_row], ignore_index=True)
                
                # *** 가장 중요 ***: NaN을 빈 문자열이나 0으로 채워야 에러 안 남
                updated_df = updated_df.fillna("") 
            else:
                updated_df = new_row
            
            conn.update(worksheet="Sheet1", data=updated_df)
            st.success("✅ 저장 완료! (누적 기록됨)")

    # 계산 로직
    v_l, v_u = v1 * (1-band_pct), v1 * (1+band_pct)
    ok, qta, msg, m_type = check_safety(m['dd'], fng_input)
    
    current_asset_usd = (m['price'] * qty) + pool
    current_asset_krw = current_asset_usd * m['fx']
    roi_val_krw = current_asset_krw - principal
    roi_pct = (roi_val_krw / principal) * 100 if principal > 0 else 0

    # --- [메인 대시보드] ---
    st.subheader(f"📈 TQQQ: ${m['price']} (FnG: {int(fng_input)})")
    
    c1, c2, c3 = st.columns(3)
    c1.metric("총 투입 원금 (KRW)", f"{principal:,.0f}원")
    c2.metric("현재 자산 평가 (KRW)", f"{current_asset_krw:,.0f}원", delta=f"{roi_val_krw:,.0f}원")
    c3.metric("수익률 (ROI)", f"{roi_pct:.2f}%", delta_color="normal")
    
    st.divider()

    tab1, tab2 = st.tabs(["📊 매매 가이드", "📘 로직 설명"])
    telegram_msg = "" 

    with tab1:
        if m_type == "normal": st.success(msg)
        elif m_type == "warning": st.warning(msg)
        else: st.error(msg)
        
        telegram_msg += f"[VR 5.0 리포트]\n📅 {datetime.now().strftime('%Y-%m-%d')}\n"
        telegram_msg += f"TQQQ: ${m['price']} (FnG: {int(fng_input)})\n"
        telegram_msg += f"상태: {msg}\n"
        telegram_msg += f"밴드폭: {int(band_pct*100)}%\n"
        telegram_msg += f"수익률: {roi_pct:.2f}% ({roi_val_krw/10000:.0f}만원)\n\n"

        col_v1, col_v2, col_v3 = st.columns(3)
        col_v1.metric("현재 평가금", f"${m['price']*qty:,.1f}")
        col_v2.metric("목표 V값", f"${v1:,.1f}")
        col_v3.metric("하단 매수선", f"${v_l:,.1f}")

        st.divider()
        l, r = st.columns(2)
        
        with l:
            st.markdown("#### 📉 매수 (Buy)")
            if m['price']*qty < v_l:
                if ok:
                    st.write(f"✅ 가용 현금 쿼터: {qta*100:.0f}%")
                    telegram_msg += "📉 [매수 추천]\n"
                    for i in range(1, 10):
                        t_q = qty + i
                        p = v_l / t_q
                        if p < m['price'] * 1.05:
                            guide_text = f"LOC 매수: {p:.2f}$ ({t_q}주)"
                            st.code(guide_text)
                            telegram_msg += f"{guide_text}\n"
                else: 
                    st.error("🚫 FnG 위험: 매수 금지")
                    telegram_msg += "🚫 FnG 경고: 매수 금지\n"
            else: 
                st.info("😴 관망")
                telegram_msg += "😴 매수 없음 (관망)\n"

        with r:
            st.markdown("#### 📈 매도 (Sell)")
            if m['price']*qty > v_u:
                telegram_msg += "📈 [매도 추천]\n"
                for i in range(1, 5):
                    t_q = qty - i
                    if t_q > 0:
                        p = v1 / t_q
                        if p > m['price']: 
                            guide_text = f"LOC 매도: {p:.2f}$ ({qty-t_q}주 판매)"
                            st.code(guide_text)
                            telegram_msg += f"{guide_text}\n"
            else: 
                st.info("😴 관망")
                telegram_msg += "😴 매도 없음 (관망)\n"

        st.divider()
        if st.button("✈️ 텔레그램 전송"):
            send_telegram_msg(telegram_msg)

        fig = go.Figure()
        dr_range = [datetime.now().date(), datetime.now().date() + timedelta(days=14)]
        fig.add_trace(go.Scatter(x=dr_range, y=[v_l, v_l], name='매수선', line=dict(color='red', dash='dash')))
        fig.add_trace(go.Scatter(x=dr_range, y=[v_u, v_u], name='매도선', line=dict(color='green', dash='dash')))
        fig.add_trace(go.Scatter(x=dr_range, y=[v1, v1], name='목표 V', line=dict(color='blue')))
        fig.add_trace(go.Scatter(x=[datetime.now().date()], y=[m['price']*qty], marker=dict(color='orange', size=15), name='현재자산'))
        fig.update_layout(height=350, margin=dict(l=10, r=10, t=30, b=10), template="plotly_white")
        st.plotly_chart(fig, use_container_width=True)

    with tab2:
        st.markdown("""
        ### 🛡️ VR 5.0 로직
        **1. 밴드폭 (Bandwidth)**
        * 평시: 15%, 상승장: 20%, 하락장: 10%
        **2. FnG 안전장치**
        * 조정장: FnG 15 이하 매수 / 하락장: FnG 10 이하 매수
        """)
else:
    st.error("데이터 로드 중... 잠시만 기다려주세요.")
