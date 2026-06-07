import streamlit as st
from openai import OpenAI
import base64
from PIL import Image
import io
import json
import fitz  # 這是 PyMuPDF 套件，用來處理 PDF

# ==========================================
# 1. 頁面初始化與 API 設定
# ==========================================
st.set_page_config(page_title="高中數學作業自動批改系統 (批量版)", layout="wide")

# 讀取金鑰與第三方代理網址
if "GEMINI_API_KEY" in st.secrets and "GEMINI_BASE_URL" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
    base_url = st.secrets["GEMINI_BASE_URL"]
    
    # 確保 base_url 結尾有 /v1 (多數第三方 API 的標準格式)
    if not base_url.endswith("/v1") and not base_url.endswith("/v1/"):
        base_url = base_url.rstrip("/") + "/v1"
        
    # 初始化 OpenAI 客戶端來連接第三方 API
    client = OpenAI(api_key=api_key, base_url=base_url)
else:
    st.error("⚠️ 請先在 Streamlit Secrets 中設定 GEMINI_API_KEY 與 GEMINI_BASE_URL")
    st.stop()

# ==========================================
# 2. 輔助函式
# ==========================================
def encode_image(image):
    """將 PIL 圖片轉換為 Base64 編碼，供 API 讀取"""
    if image.mode != 'RGB':
        image = image.convert('RGB')
    buffered = io.BytesIO()
    # 稍微壓縮圖片以加快傳輸速度
    image.save(buffered, format="JPEG", quality=85)
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

def extract_images_from_pdf(pdf_bytes):
    """將上傳的 PDF 檔案轉換為一頁一頁的圖片列表"""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    images = []
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        # 放大 2 倍確保算式清晰度 (matrix=2,2)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data))
        images.append(img)
    return images

def grade_single_image(image_b64, model_name, rubric):
    """封裝好的單張圖片批改函式"""
    system_prompt = "你是一位嚴謹的高中數學老師。請嚴格以 JSON 格式回傳，不要有任何多餘的文字或 markdown 標記。"
    user_prompt = f"""請根據下方的【評分標準】，批改圖片中的學生數學作業。
【評分標準】：
{rubric}

【回傳 JSON 格式要求】：
{{
    "recognized_steps": "你辨識到的完整算式與推導步驟",
    "error_analysis": "詳細分析哪裡寫對、哪裡寫錯",
    "score": "最終給分 (只需填寫數字)",
    "feedback": "給學生的評語"
}}"""
    
    # 呼叫 API
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
                ]
            }
        ],
        max_tokens=1500,
        temperature=0.2
    )
    
    # 處理回傳的文字，確保是純 JSON
    raw_text = response.choices[0].message.content.strip()
    raw_text = raw_text.replace("```json", "").replace("```", "").strip()
    return json.loads(raw_text)

# ==========================================
# 3. 網頁介面 (UI) 設計
# ==========================================
st.title("📝 高中數學作業自動批改系統 (PDF 批量版)")
st.markdown("支援上傳單張圖片或 **多頁 PDF 考卷** 進行自動批量批改。")
st.markdown("---")

col1, col2 = st.columns([1, 1.5])

with col1:
    st.subheader("⚙️ 1. 批改設定")
    
    # 模型選擇選單
    model_options = {
        "🧠 深度邏輯版 (gemini-1.5-pro)": "gemini-3-flash-preview",
        "⚡ 極速批改版 (gemini-1.5-flash)": "gemini-3-flash-preview",
        "🔮 備用高階模型 (gpt-4o)": "gemini-3-flash-preview"
    }
    selected_friendly_name = st.selectbox("選擇 AI 模型", options=list(model_options.keys()))
    actual_model_name = model_options[selected_friendly_name]
    
    # 評分標準輸入區
    st.markdown("<br>", unsafe_allow_html=True)
    default_rubric = """1. 寫出正確公式：給 2 分\n2. 運算過程正確：給 2 分\n3. 最終答案正確：給 1 分\n(總分 5 分)"""
    rubric = st.text_area("設定評分標準 (Rubric)", value=default_rubric, height=150)
    
    # 檔案上傳區 (新增 pdf 支援)
    st.markdown("<br>", unsafe_allow_html=True)
    uploaded_file = st.file_uploader("上傳全班作業 (PDF) 或單張圖片 (JPG/PNG)", type=["pdf", "jpg", "png", "jpeg"])

with col2:
    st.subheader("👁️ 2. 作業處理與批改結果")
    
    if uploaded_file is not None:
        file_extension = uploaded_file.name.split('.')[-1].lower()
        images_to_process = []
        
        # 判斷是 PDF 還是單張圖片
        if file_extension == 'pdf':
            with st.spinner("📄 正在從 PDF 中擷取每一頁的考卷..."):
                images_to_process = extract_images_from_pdf(uploaded_file.read())
            st.info(f"✅ 成功從 PDF 讀取了 **{len(images_to_process)}** 頁作業。")
        else:
            images_to_process = [Image.open(uploaded_file)]
            st.image(images_to_process[0], caption="學生上傳的作業畫面", use_container_width=True)
            
        st.markdown("---")
        
        # 執行批改按鈕
        if st.button("🚀 開始批量智能批改", type="primary", use_container_width=True):
            
            # 建立進度條與狀態文字
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            results_list = []
            total_pages = len(images_to_process)
            
            # 開始迴圈批改每一頁
            for i, img in enumerate(images_to_process):
                page_num = i + 1
                status_text.text(f"🧠 正在批改第 {page_num} / {total_pages} 頁，請稍候...")
                
                try:
                    # 編碼並呼叫 API
                    b64_img = encode_image(img)
                    result_json = grade_single_image(b64_img, actual_model_name, rubric)
                    
                    # 儲存成功結果
                    results_list.append({
                        "page": page_num,
                        "image": img,
                        "data": result_json,
                        "status": "success"
                    })
                except Exception as e:
                    # 處理單頁失敗的狀況 (不中斷整個流程)
                    results_list.append({
                        "page": page_num,
                        "image": img,
                        "error": str(e),
                        "status": "error"
                    })
                
                # 更新進度條
                progress_bar.progress((i + 1) / total_pages)
            
            # 完成提示
            status_text.success(f"🎉 批量批改完成！共處理 {total_pages} 份作業。")
            st.balloons()
            
            # ==========================================
            # 顯示批量結果 (使用 Expander 折疊排版)
            # ==========================================
            st.subheader("📊 批改結果總覽")
            
            for res in results_list:
                # 如果只有一頁就預設展開，多頁就預設折疊
                with st.expander(f"📄 第 {res['page']} 頁作業批改結果", expanded=(total_pages==1)):
                    subcol1, subcol2 = st.columns([1, 2])
                    
                    with subcol1:
                        # 顯示縮圖
                        st.image(res['image'], use_container_width=True)
                        
                    with subcol2:
                        if res['status'] == "success":
                            data = res['data']
                            st.metric(label="🌟 建議分數", value=f"{data.get('score', '未知')} 分")
                            st.info(f"**💬 評語**：\n{data.get('feedback', '無')}")
                            st.write("**辨識算式：**")
                            st.code(data.get('recognized_steps', '無法辨識'))
                            st.write("**錯誤分析：**")
                            st.write(data.get('error_analysis', '無'))
                        else:
                            st.error(f"💥 此頁批改失敗：{res['error']}")
    else:
        st.info("👈 請先上傳一份 PDF 考卷或單張圖片。")
