import streamlit as st
import google.generativeai as genai

# ==========================================
# 1. 頁面初始化與 API 設定
# ==========================================
st.set_page_config(page_title="高中數學作業自動批改系統", layout="wide")

# 讀取金鑰 (請確保專案資料夾內有 .streamlit/secrets.toml)
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    st.error("⚠️ 請先在 .streamlit/secrets.toml 中設定 GEMINI_API_KEY")
    st.stop()

# ==========================================
# 2. 核心邏輯：動態抓取模型與友善命名
# ==========================================
@st.cache_data(ttl=3600)  # 快取 1 小時，避免頻繁發送請求
def get_friendly_models():
    friendly_options = {}
    try:
        for m in genai.list_models():
            # 只篩選支援生成內容且名稱包含 gemini 的模型
            if 'generateContent' in m.supported_generation_methods and 'gemini' in m.name:
                raw_name = m.name.replace("models/", "")
                
                # 建立字典對照表 (翻譯邏輯)
                if "flash" in raw_name:
                    friendly_name = f"⚡ 極速批改版 ({raw_name}) - 適合簡單題型"
                elif "pro" in raw_name:
                    friendly_name = f"🧠 深度邏輯版 ({raw_name}) - 適合複雜計算"
                else:
                    friendly_name = f"🔮 其他可用模型 ({raw_name})"
                    
                friendly_options[friendly_name] = raw_name
    except Exception as e:
        st.error(f"無法取得模型列表，請檢查網路或 API 狀態。錯誤：{e}")
        
    return friendly_options

# 取得字典資料
model_dict = get_friendly_models()

# ==========================================
# 3. 網頁介面 (UI) 設計
# ==========================================
st.title("📝 高中數學作業自動批改系統")
st.markdown("---")

# 使用左右兩欄佈局
col1, col2 = st.columns([1, 1.2])

with col1:
    st.subheader("⚙️ 1. 批改設定")
    
    # 下拉選單：讓老師看友善名稱，但程式背後記錄真實名稱
    if model_dict:
        # 預設尋找包含「深度邏輯版」的選項，若無則選第一個
        default_idx = next((i for i, name in enumerate(model_dict.keys()) if "深度邏輯版" in name), 0)
        
        selected_friendly_name = st.selectbox(
            "選擇 AI 模型 (已自動同步官方最新版本)",
            options=list(model_dict.keys()),
            index=default_idx
        )
        actual_model_name = model_dict[selected_friendly_name]
        st.caption(f"目前實際調用模型：`{actual_model_name}`")
    else:
        st.warning("系統目前無法載入模型清單。")

    # 評分標準輸入區
    st.markdown("<br>", unsafe_allow_html=True)
    default_rubric = "1. 寫出正確公式：給 2 分\n2. 運算過程正確：給 2 分\n3. 最終答案正確：給 1 分\n(總分 5 分)"
    rubric = st.text_area("設定評分標準 (Rubric)", value=default_rubric, height=160)
    
    # 檔案上傳區
    st.markdown("<br>", unsafe_allow_html=True)
    uploaded_file = st.file_uploader("上傳全班作業 (支援 PDF, JPG, PNG)", type=["pdf", "jpg", "png", "jpeg"])

with col2:
    st.subheader("👁️ 2. 作業預覽與狀態")
    
    # 建立一個漂亮的卡片視覺區塊
    with st.container(border=True):
        if uploaded_file is not None:
            st.success(f"✅ 成功載入檔案：{uploaded_file.name}")
            
            # 這裡暫時放文字佔位，後續會換成圖片與分割確認介面
            st.info("⏳ 這裡之後會顯示影像前處理（裁切、辨識名字）的縮圖，讓您進行人工確認。")
            
            st.markdown("---")
            if st.button("🚀 確認無誤，開始智能批改", type="primary", use_container_width=True):
                st.write("🧠 串接 Gemini 進行批改的邏輯即將在此執行...")
        else:
            st.info("👈 請先從左側設定評分標準，並上傳作業檔案。")