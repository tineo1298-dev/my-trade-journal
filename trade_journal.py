import streamlit as st
import pandas as pd
import io
from datetime import datetime, timedelta
from PIL import Image
import altair as alt
from supabase import create_client
import streamlit.components.v1 as components # ใช้สำหรับกราฟ TradingView

# --- ตั้งค่าหน้าเว็บ ---
st.set_page_config(page_title="Master Trading Journal", layout="wide")

# =========================================================
# 🔐 SECRETS CONFIG (ดึง Key จาก Cloud/Local)
# =========================================================
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except:
    st.error("ไม่พบ Key! กรุณาตั้งค่า Secrets ใน .streamlit/secrets.toml หรือบน Streamlit Cloud")
    st.stop()

# Initialize Supabase
@st.cache_resource
def init_supabase():
    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        return None

supabase = init_supabase()

# ==========================================
# 🔐 AUTHENTICATION & LOGIN SYSTEM
# ==========================================
if 'user' not in st.session_state:
    st.session_state.user = None

def login_page():
    st.title("🔐 เข้าสู่ระบบ (Trading Journal)")
    
    tab1, tab2 = st.tabs(["Login", "Sign Up (สมัครสมาชิก)"])
    
    with tab1:
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_pass")
        if st.button("Log In", type="primary"):
            try:
                response = supabase.auth.sign_in_with_password({"email": email, "password": password})
                st.session_state.user = response.user
                st.success("Login สำเร็จ!")
                st.rerun()
            except Exception as e:
                st.error(f"Login ไม่ผ่าน: {e}")

    with tab2:
        new_email = st.text_input("Email", key="signup_email")
        new_password = st.text_input("Password", type="password", key="signup_pass")
        st.caption("รหัสผ่านต้องยาวอย่างน้อย 6 ตัวอักษร")
        if st.button("สมัครสมาชิก (Sign Up)"):
            try:
                response = supabase.auth.sign_up({"email": new_email, "password": new_password})
                if response.user:
                    st.success("สมัครสมาชิกสำเร็จ! กรุณา Log In ที่แถบแรก")
            except Exception as e:
                st.error(f"สมัครไม่ผ่าน: {e}")

if not st.session_state.user:
    login_page()
    st.stop()

# ==========================================
# ☁️ CLOUD STORAGE FUNCTIONS
# ==========================================
def upload_image_to_supabase(uploaded_file, prefix, coin_name):
    if uploaded_file is None: return "None"
    try:
        image = Image.open(uploaded_file)
        if image.mode in ("RGBA", "P"): image = image.convert("RGB")
        
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='JPEG', quality=70, optimize=True)
        img_byte_arr = img_byte_arr.getvalue()

        user_id = st.session_state.user.id
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = f"{user_id}/{prefix}_{coin_name}_{timestamp_str}.jpg"

        supabase.storage.from_("trade_images").upload(
            file_path, img_byte_arr, {"content-type": "image/jpeg"}
        )
        return supabase.storage.from_("trade_images").get_public_url(file_path)
    except Exception as e:
        st.error(f"Upload Error: {e}")
        return "None"

# ==========================================
# 📈 TRADINGVIEW CHART FUNCTION
# ==========================================
def show_tradingview_chart(coin_name):
    if not coin_name: coin_name = "BTC"
    html_code = f"""
    <div class="tradingview-widget-container">
      <div id="tradingview_chart"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget(
      {{
      "width": "100%", "height": 800,
      "symbol": "BINANCE:{coin_name}USDT",
      "interval": "60", "timezone": "Asia/Bangkok",
      "theme": "dark", "style": "1", "locale": "en",
      "toolbar_bg": "#f1f3f6", "enable_publishing": false,
      "allow_symbol_change": true, "container_id": "tradingview_chart"
      }}
      );
      </script>
    </div>
    """
    components.html(html_code, height=450)

# ==========================================
# 📊 DATA LOADING & CALCULATIONS
# ==========================================
def load_data():
    if not supabase: return pd.DataFrame()
    try:
        user_id = st.session_state.user.id
        response = supabase.table("trade_journal").select("*").eq("user_id", user_id).order("id", desc=True).execute()
        
        data = response.data
        if data:
            df = pd.DataFrame(data)
            if 'date' in df.columns: df['date'] = pd.to_datetime(df['date'])
            if 'created_at' in df.columns: 
                df['created_at'] = pd.to_datetime(df['created_at'])
            
            df['real_pnl'] = df['real_pnl'].fillna(0.0)
            df['margin'] = df['margin'].fillna(0.0)
            df['leverage'] = df['leverage'].fillna(1)
            df['position_size'] = df['margin'] * df['leverage']
            return df
    except Exception as e: st.error(f"Load Error: {e}")
    return pd.DataFrame()

def calculate_streak(df):
    if df.empty: return 0, 0
    dates = df['date'].dt.date.sort_values().unique()
    if len(dates) == 0: return 0, 0
    current_streak, max_streak, temp = 0, 0, 1
    for i in range(1, len(dates)):
        if (dates[i] - dates[i-1]).days == 1: temp += 1
        else: max_streak = max(max_streak, temp); temp = 1
    max_streak = max(max_streak, temp)
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    if dates[-1] in [today, yesterday]:
        current_streak = 1
        for i in range(len(dates)-2, -1, -1):
            if (dates[i+1] - dates[i]).days == 1: current_streak += 1
            else: break
    return current_streak, max_streak

# ==========================================
# 🖥️ MAIN APP UI
# ==========================================
st.sidebar.caption(f"👤 User: {st.session_state.user.email}")
if st.sidebar.button("Logout"):
    supabase.auth.sign_out()
    st.session_state.user = None
    st.rerun()

st.title("☁️ Trading Journal")

# --- 1. SIDEBAR (PLAN) ---
with st.sidebar:
    st.header("📝 สร้างแผน (Plan)")
    c1, c2, c3 = st.columns([1.2, 1, 1])
    with c1: date = st.date_input("วันที่", datetime.now())
    with c2: coin_name = st.text_input("Coin", "BTC").upper()
    with c3: position = st.selectbox("Po", ["L", "S"])
    
    c4, c5 = st.columns(2)
    with c4: leverage = st.number_input("Lev (x)", 1, 125, 20)
    with c5: margin = st.number_input("Margin ($)", 1.0, 100000.0, 100.0)
    total_pos = margin * leverage
    st.caption(f"💰 Size: ${total_pos:,.2f}")
    
    st.markdown("---")
    p1, p2, p3 = st.columns(3)
    with p1: entry_price = st.number_input("Entry", 0.0, format="%.4f")
    with p2: tp_price = st.number_input("TP", 0.0, format="%.4f")
    with p3: sl_price = st.number_input("SL", 0.0, format="%.4f")
    
    if entry_price > 0:
        risk = abs(entry_price - sl_price) if sl_price > 0 else 0
        reward = abs(tp_price - entry_price) if tp_price > 0 else 0
        rr_txt = f"{reward/risk:.2f}" if risk > 0 else "-"
        st.caption(f"Risk:Reward = 1 : {rr_txt}")

    plan_note = st.text_area("Note", height=68)
    uploaded_plan_img = st.file_uploader("รูปแผน", type=['png', 'jpg'], label_visibility="collapsed")
    if uploaded_plan_img: st.image(uploaded_plan_img, caption="Preview", use_container_width=True)
    
    if st.button("บันทึกแผน (Save)", type="primary", use_container_width=True):
        if coin_name == "": st.error("ระบุชื่อเหรียญ")
        else:
            with st.spinner("กำลังอัปโหลดรูป..."):
                path_url = upload_image_to_supabase(uploaded_plan_img, "PLAN", coin_name)
            
            new_data = {
                "user_id": st.session_state.user.id,
                "date": str(date), "coin": coin_name, "position": position,
                "leverage": leverage, "margin": margin, "position_size": total_pos,
                "entry_price": entry_price, "plan_tp": tp_price, "plan_sl": sl_price,
                "plan_note": plan_note, "real_pnl": 0.0, "exit_note": "-",
                "plan_image_path": path_url,
                "result_image_path": "None", "status": "Open"
            }
            try:
                supabase.table("trade_journal").insert(new_data).execute()
                st.success("บันทึกสำเร็จ!")
            except Exception as e: st.error(f"Error: {e}")

# --- SHOW TRADINGVIEW CHART ---
# แสดงกราฟทันทีหลัง Title ตามชื่อเหรียญที่กรอกใน Sidebar
if coin_name:
    st.markdown(f"### 📈 {coin_name}/USDT")
    show_tradingview_chart(coin_name)

# --- 2. DASHBOARD ---
df = load_data()

if not df.empty:
    closed = df[df['status'] == 'Closed'].copy()
    total_pnl = closed['real_pnl'].sum() if not closed.empty else 0
    curr_str, max_str = calculate_streak(df)

    st.markdown("---")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Net Profit", f"${total_pnl:,.2f}", delta_color="normal" if total_pnl>=0 else "inverse")
    c2.metric("Closed Trades", len(closed))
    c3.metric("🔥 Streak", f"{curr_str} Days")
    c4.metric("🏆 Max Streak", f"{max_str} Days")

    st.markdown("---")

    # กราฟสถิติ (Heatmap & Activity)
    c_hm1, c_hm2 = st.columns([2, 1])
    with c_hm1:
        if 'created_at' in df.columns:
            hm = alt.Chart(df).mark_rect().encode(
                x=alt.X('hours(created_at):O', title='Hour'),
                y=alt.Y('day(created_at):O', title='Day', sort=['Mon','Tue','Wed','Thu','Fri','Sat','Sun']),
                color=alt.Color('count():Q', scale=alt.Scale(scheme='blues')),
                tooltip=['day(created_at)', 'hours(created_at)', 'count()']
            ).properties(height=200, title="Time Heatmap")
            st.altair_chart(hm, use_container_width=True)
    with c_hm2:
        dc = df['date'].dt.date.value_counts().reset_index()
        dc.columns=['date','count']; dc['date']=pd.to_datetime(dc['date'])
        gh = alt.Chart(dc).mark_rect().encode(
            x=alt.X('week(date):O', axis=alt.Axis(labels=False, title='Week')), 
            y=alt.Y('day(date):O', title=None),
            color=alt.Color('count:Q', scale=alt.Scale(scheme='greens'), legend=None),
            tooltip=[alt.Tooltip('date', format='%Y-%m-%d'), 'count']
        ).properties(height=200, title="Daily Activity")
        st.altair_chart(gh, use_container_width=True)

    # กราฟ Equity Curve
    if not closed.empty:
        st.markdown("#### 💹 Equity Curve")
        cd = closed.sort_values(by="date")
        cd['CumPNL'] = cd['real_pnl'].cumsum()
        st.line_chart(cd, x='date', y='CumPNL', color="#00FF00")

    st.markdown("---")

    # --- 3. CLOSE ORDER ---
    st.subheader("✍️ 2. ลงผลลัพธ์ (Close Order)")
    open_orders = df[df['status'] == 'Open']

    if not open_orders.empty:
        opts = open_orders.apply(lambda x: f"ID {x['id']}: {x['coin']} ({x['position']})", axis=1)
        sel = st.selectbox("เลือกออเดอร์:", opts)
        
        if sel:
            sid = int(sel.split(":")[0].replace("ID ", ""))
            current_row = df[df['id']==sid].iloc[0]
            st.info(f"📌 Note: {current_row['plan_note']}")
            
            with st.form("res_form"):
                c1, c2 = st.columns(2)
                rp = c1.number_input("PNL ($)", step=0.1)
                en = c2.text_input("บทเรียน")
                img = st.file_uploader("รูปผลลัพธ์", type=['png', 'jpg'])
                
                if st.form_submit_button("ปิดงาน"):
                    with st.spinner("กำลังอัปโหลดรูป..."):
                        r_path_url = upload_image_to_supabase(img, "RES", current_row['coin'])
                    
                    update_data = {
                        "real_pnl": rp, 
                        "exit_note": en, 
                        "result_image_path": r_path_url, 
                        "status": "Closed"
                    }
                    try:
                        supabase.table("trade_journal").update(update_data).eq("id", sid).eq("user_id", st.session_state.user.id).execute()
                        st.success("อัปเดตเรียบร้อย!")
                        st.rerun()
                    except Exception as e: st.error(f"Error: {e}")
    else:
        st.info("ไม่มีออเดอร์ค้าง")

    st.markdown("---")

    # --- 4. HISTORY ---
    st.subheader("📜 ประวัติ (Trade History)")
    cols_to_show = ["id", "date", "status", "coin", "position", "real_pnl", "plan_note"]
    st.dataframe(df[cols_to_show], use_container_width=True, hide_index=True)

    st.markdown("### 🔍 ดูรายละเอียด & ลบ")
    view_opts = df.apply(lambda x: f"ID {x['id']} : {x['coin']} ({x['position']})", axis=1)
    sel_view = st.selectbox("เลือกรายการดูรูป:", view_opts.iloc[::-1])

    if sel_view:
        vid = int(sel_view.split(" :")[0].replace("ID ", ""))
        row = df[df['id'] == vid].iloc[0]
        
        c_det1, c_det2 = st.columns(2)
        with c_det1:
            st.markdown(f"**📌 Plan Note:** {row['plan_note']}")
            if row['plan_image_path'] and str(row['plan_image_path']).startswith("http"):
                st.image(row['plan_image_path'], caption="แผน", use_container_width=True)
            else: st.caption("ไม่มีรูป")

        with c_det2:
            st.markdown(f"**📝 Exit Note:** {row['exit_note']}")
            if row['result_image_path'] and str(row['result_image_path']).startswith("http"):
                st.image(row['result_image_path'], caption="ผลลัพธ์", use_container_width=True)
            else: st.caption("ไม่มีรูป")
            
        # ปุ่มลบข้อมูล
        st.markdown("---")
        with st.expander(f"🗑️ ลบรายการ ID {vid}"):
            st.warning("คำเตือน: ลบแล้วกู้คืนไม่ได้")
            if st.button("ยืนยันการลบ (Delete)", type="primary", key=f"del_{vid}"):
                try:
                    supabase.table("trade_journal").delete().eq("id", vid).eq("user_id", st.session_state.user.id).execute()
                    st.success(f"ลบรายการ ID {vid} เรียบร้อย!")
                    st.rerun()
                except Exception as e:
                    st.error(f"เกิดข้อผิดพลาด: {e}")

else:

    st.info("👋 ยินดีต้อนรับ! เริ่มบันทึกเทรดแรกของคุณได้เลย")
