import streamlit as st
import google.generativeai as genai
from PIL import Image
import json

# ==========================================
# 1. 頁面初始化與 API 設定
# ==========================================
st.set_page_config(page_title="高中數學作業自動批改系統", layout="wide")

if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    st.error("⚠️ 請先在 Streamlit 後台 Secrets 中設定 GEMINI_API_KEY")
    st.stop()

# ==========================================
# 2. 動態抓取模型與友善命名
# ==========================================
@st.cache_data(ttl=3600)
def get_friendly_models():
    friendly_options = {}
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods and 'gemini' in m.name:
                raw_name = m.name.replace("models/", "")
                if "flash" in raw_name:
                    friendly_name = f"⚡ 極速批改版 ({raw_name}) - 適合簡單題型"
                elif "pro" in raw_name:
                    friendly_name = f"🧠 深度邏輯版 ({raw_name}) - 適合複雜計算"
                else:
                    friendly_name = f"🔮 其他可用模型 ({raw_name})"
                friendly_options[friendly_name] = raw_name
    except Exception as e:
        st.error(f"無法取得模型列表：{e}")
    return friendly_options

model_dict = get_friendly_models()

# ==========================================
# 3. 網頁介面 (UI) 設計
# ==========================================
st.title("📝 高中數學作業自動批改系統 (測試版)")
st.markdown("---")

col1, col2 = st.columns([1, 1.2])

with col1:
    st.subheader("⚙️ 1. 批改設定")
    
    # 模型選擇
    if model_dict:
        default_idx = next((i for i, name in enumerate(model_dict.keys()) if "深度邏輯版" in name), 0)
        selected_friendly_name = st.selectbox(
            "選擇 AI 模型", options=list(model_dict.keys()), index=default_idx
        )
        actual_model_name = model_dict[selected_friendly_name]
        st.caption(f"目前實際調用模型：`{actual_model_name}`")
    
    # 評分標準
    st.markdown("<br>", unsafe_allow_html=True)
    default_rubric = """1. 寫出正確公式：給 2 分
2. 運算過程正確：給 2 分
3. 最終答案正確：給 1 分
(總分 5 分)"""
    rubric = st.text_area("設定評分標準 (Rubric)", value=default_rubric, height=150)
    
    # 檔案上傳 (第一階段先測試 JPG/PNG 圖片)
    st.markdown("<br>", unsafe_allow_html=True)
    uploaded_file = st.file_uploader("上傳學生單張作業圖片 (JPG/PNG)", type=["jpg", "png", "jpeg"])

with col2:
    st.subheader("👁️ 2. 作業預覽與批改結果")
    
    if uploaded_file is not None:
        # 讀取並顯示圖片
        image = Image.open(uploaded_file)
        st.image(image, caption="學生上傳的作業畫面", use_container_width=True)
        
        st.markdown("---")
        # 按下批改按鈕
        if st.button("🚀 確認無誤，開始智能批改", type="primary", use_container_width=True):
            with st.spinner("🧠 Gemini 正在仔細閱讀算式並評分中..."):
                try:
                    # 初始化選擇的模型
                    model = genai.GenerativeModel(actual_model_name)
                    
                    # 提示詞工程 (Prompt)
                    prompt = f"""
                    你是一位嚴謹的高中數學老師。請根據下方的【評分標準】，批改圖片中的學生數學作業。
                    
                    【評分標準】：
                    {rubric}
                    
                    【作業要求】：
                    1. 仔細辨識圖片中的手寫算式。
                    2. 判斷學生的邏輯是否有錯、計算是否粗心。
                    3. 請你嚴格以 JSON 格式回傳結果，不需要任何多餘的問候語，直接輸出 JSON 內容即可。
                    
                    【回傳 JSON 格式】：
                    {{
                        "recognized_steps": "你辨識到的學生完整算式與推導步驟",
                        "error_analysis": "詳細分析學生哪裡寫對、哪裡寫錯（若全對則寫「邏輯與計算皆正確」）",
                        "score": "最終給分（只需填寫數字）",
                        "feedback": "給這位學生的簡短評語與建議"
                    }}
                    """
                    
                    # 送出給 Gemini
                    response = model.generate_content([prompt, image])
                    raw_text = response.text.strip()
                    
                    # 確保乾淨的 JSON 格式 (安全替換法，避免語法錯誤)
                    raw_text = raw_text.replace("```json", "")
                    raw_text = raw_text.replace("```", "")
                    raw_text = raw_text.strip()
                    
                    # 解析結果
                    result = json.loads(raw_text)
                    
                    # 顯示批改成果
                    st.success("🎉 批改完成！")
                    st.metric(label="🌟 AI 建議分數", value=f"{result.get('score', '未知')} 分")
                    st.info(f"**💬 給學生的評語**：\n{result.get('feedback', '無')}")
                    
                    with st.expander("🔍 查看 AI 詳細分析過程"):
                        st.write("**辨識到的算式：**")
                        st.code(result.get('recognized_steps', '無法辨識'))
                        st.write("**錯誤分析邏輯：**")
                        st.write(result.get('error_analysis', '無詳細分析'))
                        
                except json.JSONDecodeError:
                     st.error(f"💥 批改失敗。AI 未按標準 JSON 格式回傳。原始回傳內容：\n{raw_text}")
                except Exception as e:
                    st.error(f"💥 批改過程發生錯誤。錯誤訊息：{e}")
    else:
        st.info("👈 請先在左側設定評分標準，並上傳一張學生的作業圖片。")
