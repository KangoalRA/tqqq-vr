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
        token = st.secrets["telegram"]["bot_token"]
        chat_id = st.secrets["telegram"]["chat_id"]
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {"chat_id": chat_id, "text": msg}
        requests.post(url, data=data)
        st.toast("✅ 텔레그램 전송 성공!", icon="✈️")
    except:
        st.error("텔레그램 설정 오류 (secrets.toml 확인 필요)")

@st.cache_data(ttl=600)
def get_market_intelligence():
    data = {"price": 0.0, "fx": 1350.0, "dd": 0.0, "fng": 25.0, "bull": True}
    try:
        # TQQQ 가격
        t_hist = yf.Ticker("TQQQ").history(period="5d")
        if not t_hist.empty: 
            data["price"] = round(t_hist['Close'].iloc[-1], 2)
        
        # 나스닥 데이터 (MDD 및 200일선)
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

        # 공포탐욕지수 (CNN) - 크롤링 실패시 기본값 사용
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            r = requests.get("https://production.dataviz.cnn.io/index/fearandgreed/static/history", headers=headers, timeout=3)
            if r.status_code == 200: 
                data["fng"] = float(r.json()['fear_and_greed']['score'])
        except: pass
        
        return data
    except: 
        return data

m = get_market_intelligence()

# --- [1. 로직 함수] ---
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

# --- [UI 구성] ---
st.title("🚀 TQQQ VR 5.0 Pro")

if m and m["price"] > 0:
    with st.sidebar:
        st.header("⚙️ VR 설정")
        
        # G값 슬라이더 (성장 조절)
        st.subheader("1. G값 (성장 속도 조절)")
        st.caption("10(빠름/공격적) ~ 40(느림/보수적)")
        g_factor = st.slider("G값 설정", 10, 40, 10)
        
        st.divider()

        # 밴드폭 슬라이더
        st.subheader("2. 밴드폭 (매매 범위)")
        rec_val, rec_msg = get_recommended_band(m['dd'], m['bull'])
        st.caption(rec_msg)
        band_pct = st.slider("밴드폭 (%)", 5, 30, rec_val) / 100

        st.divider()

        # 시장 데이터
        st.subheader("3. 시장 데이터 확인")
        st.metric("나스닥 MDD", f"{m['dd']}%")
        st.markdown("[👉 FnG 확인 (CNN)](https://edition.cnn.com/markets/fear-and-greed)")
        fng_input = st.number_input("FnG 입력", value=float(m['fng']))
        
        st.divider()
        
        # 구글 시트 데이터 로드
        st.subheader("4. 자산 데이터 로드")
        conn = st.connection("gsheets", type=GSheetsConnection)
        
        # 변수 초기화 (에러 방지용)
        df = pd.DataFrame()
        default_qty = 100
        default_pool = 2000.0
        default_v = m['price'] * 100
        default_principal = 5000.0
        last_date = "기록 없음"
        
        try:
            # 데이터 읽기
            df = conn.read(worksheet="Sheet1", ttl=0)
            
            # 데이터가 있고 컬럼이 충분한지 확인
            if not df.empty and len(df.columns) >= 4:
                # 마지막 행 가져오기
                last_row = df.iloc[-1]
                
                # 안전하게 값 파싱 (문자열이 섞여있어도 죽지 않게 처리)
                try: default_qty = int(float(str(last_row.iloc[0]).replace(',','')))
                except: pass
                
                try: default_pool = float(str(last_row.iloc[1]).replace(',',''))
                except: pass
                
                try: default_v = float(str(last_row.iloc[2]).replace(',',''))
                except: pass
                
                try: default_principal = float(str(last_row.iloc[3]).replace(',',''))
                except: pass
                
                # 날짜 열 확인
                if len(df.columns) > 4:
                    last_date = str(last_row.iloc[4])
                
                st.success(f"✅ 데이터 로드 성공 (기준일: {last_date})")
            else:
                st.info("ℹ️ 신규 시작 또는 데이터 없음")
                
        except Exception as e:
            st.warning("⚠️ 시트 읽기 실패 (신규 생성이면 무시하세요)")

        # 모드 선택
        mode = st.radio("실행 모드", ["사이클 업데이트", "최초 시작"])
        
        # 입력 폼
        qty = st.number_input("보유 수량 (주)", value=default_qty, min_value=0)
        pool = st.number_input("현금 Pool ($)", value=default_pool)
        
        # VR 로직 계산
        v_final = 0.0
        principal_final = default_principal
        
        if mode == "최초 시작":
            principal_final = st.number_input("총 투입 원금 ($)", value=default_principal)
            v_final = m['price'] * qty
        else:
            # G값 반영 공식: 성장금 = (Pool / G) * 보정계수
            # 공식: Pool Ratio = Pool / V
            # Growth Rate = Pool Ratio / G (G가 10이면 1/10, 40이면 1/40)
            
            v_old = default_v
            st.markdown(f"**직전 V값: ${v_old:,.2f}**")
            
            # 리필 계산
            cur = st.radio("추가 적립(리필)", ["없음", "원화", "달러"], horizontal=True)
            add_val = 0.0
            if cur == "원화":
                add_krw = st.number_input("입금액 (원)", value=0)
                add_val = add_krw / m['fx']
                principal_final += add_krw # 원화는 편의상 1:1 합산(간이)
            elif cur == "달러":
                add_usd = st.number_input("입금액 ($)", value=0.0)
                add_val = add_usd
                principal_final += (add_usd * m['fx'])
            
            # 성장 계산
            if v_old > 0 and pool > 0:
                pool_ratio = pool / v_old
                # G값 적용: (Pool/V) 나누기 (G/10) -> G가 10이면 1배, 20이면 0.5배 속도
                # 하지만 요청하신 심플 로직 "Pool/10"을 "Pool/G"로 치환
                # 원본: Pool / 10 --> 수정: Pool / G
                growth_rate = pool_ratio / (g_factor / 10.0) / 10.0 # 기본 10에서 G배수 적용
                # 더 직관적인 해석: 사용자가 원한건 (Pool/V)/G 가 아니라, (Pool/V) / (G/10) 느낌보다는
                # 그냥 분모를 조절하는 것.
                
                # 라오어 공식 Base: (Pool / V) / 10 
                # 여기서 분모 10을 -> G값(10~40)으로 대체
                base_growth = (pool / v_old) / g_factor
                
                # 추가 성장 (평가금이 V보다 크면 +0.5%)
                bonus = 0.005 if (m['price'] * qty) > v_old else 0.0
                
                total_growth = base_growth + bonus
                growth_val = v_old * total_growth
                
                v_final = v_old + growth_val + add_val
                
                st.info(f"📈 성장률: {total_growth*100:.2f}% (G={g_factor}) | +${growth_val:.2f}")
            else:
                v_final = v_old + add_val
                
            if add_val > 0: st.success(f"💰 리필 ${add_val:,.1f} 반영됨")

        # 저장 로직 (가장 중요한 부분)
        if st.button("💾 구글 시트에 저장"):
            # 저장할 데이터 한 줄 생성
            row_data = {
                "Qty": qty, 
                "Pool": pool, 
                "V_old": v_final, 
                "Principal": principal_final,
                "Date": datetime.now().strftime('%Y-%m-%d'),
                "FnG": fng_input
            }
            new_row_df = pd.DataFrame([row_data])
            
            # 기존 데이터와 병합 (에러 방지 핵심 로직)
            final_df = pd.DataFrame()
            if not df.empty:
                # 기존 데이터프레임과 합치되, 컬럼이 안 맞아도 강제로 합침
                final_df = pd.concat([df, new_row_df], ignore_index=True)
            else:
                final_df = new_row_df
            
            # NaN 제거 (구글 시트 에러 방지)
            final_df = final_df.fillna("")
            
            # 업데이트
            conn.update(worksheet="Sheet1", data=final_df)
            st.success(f"✅ 저장 완료! Next V: ${v_final:,.1f}")
            st.rerun() # 화면 갱신

    # --- [계산 및 대시보드] ---
    v_min = v_final * (1 - band_pct)
    v_max = v_final * (1 + band_pct)
    
    is_safe, quota, status_msg, status_type = check_safety(m['dd'], fng_input)
    
    # 수익률
    curr_asset_usd = (m['price'] * qty) + pool
    curr_asset_krw = curr_asset_usd * m['fx']
    roi_val = curr_asset_krw - principal_final
    roi_pct = (roi_val / principal_final * 100) if principal_final > 0 else 0

    # 메인 화면
    st.subheader(f"📊 TQQQ: ${m['price']} (FnG: {int(fng_input)})")
    
    c1, c2, c3 = st.columns(3)
    c1.metric("총 투입 원금", f"{principal_final:,.0f}원")
    c2.metric("현재 자산", f"{curr_asset_krw:,.0f}원", delta=f"{roi_val:,.0f}원")
    c3.metric("수익률", f"{roi_pct:.2f}%", delta_color="normal")
    
    st.divider()
    
    tab1, tab2 = st.tabs(["📢 매매 가이드", "📜 상세 로직"])
    
    report_text = ""
    
    with tab1:
        if status_type == "normal": st.success(status_msg)
        elif status_type == "warning": st.warning(status_msg)
        else: st.error(status_msg)
        
        # 리포트 텍스트 생성
        report_text += f"[VR 5.0 리포트]\n📅 {datetime.now().strftime('%Y-%m-%d')}\n"
        report_text += f"주가: ${m['price']} / FnG: {int(fng_input)}\n"
        report_text += f"설정: G={g_factor} / 밴드={int(band_pct*100)}%\n"
        report_text += f"자산: {curr_asset_krw/10000:.0f}만원 ({roi_pct:.2f}%)\n\n"
        
        cc1, cc2, cc3 = st.columns(3)
        cc1.metric("현재 평가금", f"${m['price']*qty:,.1f}")
        cc2.metric("목표 V값", f"${v_final:,.1f}")
        cc3.metric("매수 밴드", f"${v_min:,.1f}")
        
        st.divider()
        
        col_buy, col_sell = st.columns(2)
        
        # 매수 로직
        with col_buy:
            st.markdown("#### 🔵 매수 (Buy)")
            if (m['price'] * qty) < v_min:
                if is_safe:
                    st.write(f"✅ 현금 사용: {quota*100:.0f}%")
                    report_text += "📉 [매수 추천]\n"
                    
                    # LOC 계산
                    for i in range(1, 10):
                        target_qty = qty + i
                        loc_price = v_min / target_qty
                        # 현재가 대비 +5% 이내일 때만 유효한 LOC로 인정
                        if loc_price < m['price'] * 1.05:
                            line = f"LOC 매수: {loc_price:.2f}$ ({target_qty}주)"
                            st.code(line)
                            report_text += f"{line}\n"
                else:
                    st.error("🛑 FnG 위험: 매수 금지")
                    report_text += "🛑 FnG 위험으로 매수 중단\n"
            else:
                st.info("zzz... 관망 (매수 구간 아님)")
                report_text += "😴 매수 없음 (관망)\n"
        
        # 매도 로직
        with col_sell:
            st.markdown("#### 🔴 매도 (Sell)")
            if (m['price'] * qty) > v_max:
                report_text += "📈 [매도 추천]\n"
                for i in range(1, 10):
                    target_qty = qty - i
                    if target_qty <= 0: break
                    loc_price = v_final / target_qty # V값 근처로 회귀
                    # 현재가보다 낮아야 매도 LOC 의미 있음
                    if loc_price > m['price'] * 0.95:
                        line = f"LOC 매도: {loc_price:.2f}$ ({qty-target_qty}주 매도)"
                        st.code(line)
                        report_text += f"{line}\n"
            else:
                st.info("zzz... 관망 (매도 구간 아님)")
                report_text += "😴 매도 없음 (관망)\n"
                
        st.divider()
        if st.button("✈️ 텔레그램 전송"):
            send_telegram_msg(report_text)
            
        # 그래프 그리기
        fig = go.Figure()
        dates = [datetime.now().date(), datetime.now().date() + timedelta(days=14)]
        fig.add_trace(go.Scatter(x=dates, y=[v_min, v_min], name="매수선", line=dict(color='red', dash='dash')))
        fig.add_trace(go.Scatter(x=dates, y=[v_max, v_max], name="매도선", line=dict(color='green', dash='dash')))
        fig.add_trace(go.Scatter(x=dates, y=[v_final, v_final], name="중심 V", line=dict(color='blue')))
        fig.add_trace(go.Scatter(x=[dates[0]], y=[m['price']*qty], name="내 자산", marker=dict(color='orange', size=12)))
        fig.update_layout(title="VR 밴드 시각화", height=350, template="plotly_white")
        st.plotly_chart(fig, use_container_width=True)

    with tab2:
        st.markdown(f"""
        ### 🛠️ 로직 상세
        **1. V값 성장 공식**
        * `성장률 = (Pool비중) ÷ {g_factor}`
        * G값이 클수록 성장은 보수적(느림)입니다.
        
        **2. 안전 장치 (FnG)**
        * 조정장(-10%~): FnG 15 이하에서만 매수
        * 하락장(-20%~): FnG 10 이하에서만 매수
        """)

else:
    st.spinner("데이터 로딩 중...")
