import streamlit as st
from openai import OpenAI
import base64
from PIL import Image
import io
import json

# ==========================================
# 1. 頁面初始化與 API 設定
# ==========================================
st.set_page_config(page_title="高中數學作業自動批改系統", layout="wide")

# 讀取金鑰與第三方代理網址
if "GEMINI_API_KEY" in st.secrets and "GEMINI_BASE_URL" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
    base_url = st.secrets["GEMINI_BASE_URL"]
    
    # 確保 base_url 結尾有 /v1 (多數第三方 API 的標準格式)
    if not base_url.endswith("/v1") and not base_url.endswith("/v1/"):
        base_url = base_url.rstrip("/") + "/v1"
        
    # 初始化客戶端 (這裡使用 openai 套件來精準連接第三方網站)
    client = OpenAI(
        api_key=api_key,
        base_url=base_url
    )
else:
    st.error("⚠️ 請先在 Streamlit Secrets 中設定 GEMINI_API_KEY 與 GEMINI_BASE_URL")
    st.stop()

# ==========================================
# 2. 輔助函式：圖片轉 Base64
# ==========================================
def encode_image(uploaded_file):
    image = Image.open(uploaded_file)
    # 將圖片轉換為 RGB 模式並壓縮，避免超過 API 大小限制
    if image.mode != 'RGB':
        image = image.convert('RGB')
    buffered = io.BytesIO()
    image.save(buffered, format="JPEG", quality=85)
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

# ==========================================
# 3. 網頁介面 (UI) 設計
# ==========================================
st.title("📝 高中數學作業自動批改系統 (第三方穩健版)")
st.markdown("---")

col1, col2 = st.columns([1, 1.2])

with col1:
    st.subheader("⚙️ 1. 批改設定")
    
    # 手動建立模型清單 (第三方網站通常支援這些標準命名)
    model_options = {
        "🧠 gemini-3-flash-preview": "gemini-3-flash-preview"
       
    }
    
    selected_friendly_name = st.selectbox("選擇 AI 模型", options=list(model_options.keys()))
    actual_model_name = model_options[selected_friendly_name]
    st.caption(f"目前實際調用模型：`{actual_model_name}`")
    
    # 評分標準設定區
    st.markdown("<br>", unsafe_allow_html=True)
    default_rubric = """1. 寫出正確公式：給 2 分
2. 運算過程正確：給 2 分
3. 最終答案正確：給 1 分
(總分 5 分)"""
    rubric = st.text_area("設定評分標準 (Rubric)", value=default_rubric, height=150)
    
    # 圖片上傳區
    st.markdown("<br>", unsafe_allow_html=True)
    uploaded_file = st.file_uploader("上傳學生單張作業圖片 (JPG/PNG)", type=["jpg", "png", "jpeg"])

with col2:
    st.subheader("👁️ 2. 作業預覽與批改結果")
    
    if uploaded_file is not None:
        st.image(Image.open(uploaded_file), caption="學生上傳的作業畫面", use_container_width=True)
        st.markdown("---")
        
        if st.button("🚀 確認無誤，開始智能批改", type="primary", use_container_width=True):
            with st.spinner(f"🧠 {actual_model_name} 正在透過第三方 API 深度閱讀中..."):
                try:
                    # 1. 將圖片轉為 Base64 字串
                    base64_image = encode_image(uploaded_file)
                    
                    # 2. 設計 Prompt 系統指令
                    system_prompt = f"你是一位嚴謹的高中數學老師。請嚴格以 JSON 格式回傳，不要有任何多餘的文字或 markdown 標記 (不要有 ```json)。"
                    
                    user_prompt = f"""請根據下方的【評分標準】，批改圖片中的學生數學作業。
【評分標準】：
{rubric}

【回傳 JSON 格式要求】：
{{
    "recognized_steps": "你辨識到的完整算式與推導步驟",
    "error_analysis": "詳細分析哪裡寫對、哪裡寫錯",
    "score": "最終給分 (填寫數字)",
    "feedback": "給學生的評語"
}}
"""
                    # 3. 呼叫第三方 API
                    response = client.chat.completions.create(
                        model=actual_model_name,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": user_prompt},
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:image/jpeg;base64,{base64_image}"
                                        }
                                    }
                                ]
                            }
                        ],
                        max_tokens=1500,
                        temperature=0.2
                    )
                    
                    # 4. 取得回傳文字並清理
                    raw_text = response.choices[0].message.content.strip()
                    raw_text = raw_text.replace("```json", "").replace("```", "").strip()
                    
                    # 5. 解析 JSON 
                    result = json.loads(raw_text)
                    
                    # 6. 渲染結果
                    st.success("🎉 批改完成！")
                    st.metric(label="🌟 AI 建議分數", value=f"{result.get('score', '未知')} 分")
                    st.info(f"**💬 給學生的評語**：\n{result.get('feedback', '無')}")
                    
                    with st.expander("🔍 查看 AI 詳細分析過程", expanded=True):
                        st.write("**辨識到的算式：**")
                        st.code(result.get('recognized_steps', '無法辨識'))
                        st.write("**錯誤分析邏輯：**")
                        st.write(result.get('error_analysis', '無詳細分析'))
                        
                except Exception as e:
                    st.error(f"💥 批改發生錯誤。請確認您的第三方網址與金鑰是否正確。錯誤細節：{e}")
    else:
        st.info("👈 請先上傳圖片。")
