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
    
    # 確保 base_url 結尾有 /v1
    if not base_url.endswith("/v1") and not base_url.endswith("/v1/"):
        base_url = base_url.rstrip("/") + "/v1"
        
    # 初始化 OpenAI 客戶端來連接第三方 API
    client = OpenAI(api_key=api_key, base_url=base_url)
else:
    st.error("⚠️ 請先在 Streamlit Secrets 中設定 GEMINI_API_KEY 與 GEMINI_BASE_URL")
    st.stop()

# ==========================================
# 2. 輔助函式 (優化 Token 節能版)
# ==========================================
def extract_images_from_pdf(pdf_bytes):
    """將 PDF 轉換為圖片，適度降低放大倍率以節省 Token 消耗"""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    images = []
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        # 從 Matrix(2, 2) 微調至 (1.3, 1.3)，既能看清字跡，又能大幅降低 AI 的切片(Tiles)計費
        pix = page.get_pixmap(matrix=fitz.Matrix(1.3, 1.3))
        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data))
        images.append(img)
    return images

def encode_image(image):
    """將圖片等比例縮小並壓縮，控制在低 Token 計費區間"""
    if image.mode != 'RGB':
        image = image.convert('RGB')
    
    # 限制圖片最大邊長不超過 1024 像素
    max_size = 1024
    if max(image.size) > max_size:
        image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        
    buffered = io.BytesIO()
    # 稍微調降 JPEG 品質至 70 減少傳輸大小，但不影響字跡辨識
    image.save(buffered, format="JPEG", quality=70)
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

def grade_single_image(image_b64, model_name, rubric):
    """封裝好的單張圖片批改函式 (強制 JSON 模式與大 Token 版)"""
    system_prompt = "你是一位嚴謹的高中數學老師。你必須且只能以 JSON 格式回傳批改結果，嚴禁包含任何額外的問候語或 Markdown 標記。"
    user_prompt = f"""請根據下方的【評分標準】，詳細批改圖片中的學生數學作業算式。
【評分標準】：
{rubric}

【回傳 JSON 格式要求】：
{{
    "recognized_steps": "你辨識到的完整算式與推導步驟",
    "error_analysis": "詳細分析哪裡寫對、哪裡寫錯（若全對則寫「邏輯與計算皆正確」）",
    "score": "最終給分 (只需填寫純數字，例如 4)",
    "feedback": "給這位學生的簡短評語與建議"
}}"""
    
    # 呼叫 API
    response = client.chat.completions.create(
        model=model_name,
        response_format={"type": "json_object"},  # ⭐【新增】強制 API 開啟嚴格 JSON 物件模式
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
        max_tokens=4000,  # ⭐【修正】將 Token 上限大幅調高至 4000，確保長公式不會被切斷
        temperature=0.1
    )
    
    # 取得原始回傳文字
    raw_text = response.choices[0].message.content.strip()
    
    # 清理字串
    cleaned_text = raw_text.replace("```json", "").replace("```", "").strip()
    
    if not cleaned_text.startswith("{"):
        raise ValueError(f"第三方 API 未成功輸出 JSON 結構。原始內容：\n{raw_text}")

    try:
        return json.loads(cleaned_text)
    except json.JSONDecodeError:
        raise ValueError(f"JSON 語法解析失敗。原始內容：\n{raw_text}")

# ==========================================
# 3. 網頁介面 (UI) 設計
# ==========================================
st.title("📝 高中數學作業自動批改系統 (PDF 批量版)")
st.markdown("支援上傳單張圖片或 **多頁 PDF 考卷** 進行自動批量批改。")
st.markdown("---")

col1, col2 = st.columns([1, 1.5])

with col1:
    st.subheader("⚙️ 1. 批改設定")
    
    model_options = {
        "🧠 gemini-3-flash-preview": "gemini-3-flash-preview",
        "⚡ gemini-3-flash-preview": "gemini-3-flash-preview",
        "🔮 gemini-3-flash-preview": "gemini-3-flash-preview"
    }
    selected_friendly_name = st.selectbox("選擇 AI 模型", options=list(model_options.keys()))
    actual_model_name = model_options[selected_friendly_name]
    
    st.markdown("<br>", unsafe_allow_html=True)
    default_rubric = """1. 寫出正確公式：給 2 分\n2. 運算過程正確：給 2 分\n3. 最終答案正確：給 1 分\n(總分 5 分)"""
    rubric = st.text_area("設定評分標準 (Rubric)", value=default_rubric, height=150)
    
    st.markdown("<br>", unsafe_allow_html=True)
    uploaded_file = st.file_uploader("上傳全班作業 (PDF) 或單張圖片 (JPG/PNG)", type=["pdf", "jpg", "png", "jpeg"])

with col2:
    st.subheader("👁️ 2. 作業處理與批改結果")
    
    if uploaded_file is not None:
        file_extension = uploaded_file.name.split('.')[-1].lower()
        images_to_process = []
        
        if file_extension == 'pdf':
            with st.spinner("📄 正在從 PDF 中擷取每一頁的考卷..."):
                images_to_process = extract_images_from_pdf(uploaded_file.read())
            st.info(f"✅ 成功從 PDF 讀取了 **{len(images_to_process)}** 頁作業。")
        else:
            images_to_process = [Image.open(uploaded_file)]
            st.image(images_to_process[0], caption="學生上傳的作業畫面", use_container_width=True)
            
        st.markdown("---")
        
        if st.button("🚀 開始批量智能批改", type="primary", use_container_width=True):
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            results_list = []
            total_pages = len(images_to_process)
            
            for i, img in enumerate(images_to_process):
                page_num = i + 1
                status_text.text(f"🧠 正在批改第 {page_num} / {total_pages} 頁，請稍候...")
                
                try:
                    b64_img = encode_image(img)
                    result_json = grade_single_image(b64_img, actual_model_name, rubric)
                    
                    results_list.append({
                        "page": page_num,
                        "image": img,
                        "data": result_json,
                        "status": "success"
                    })
                except Exception as e:
                    results_list.append({
                        "page": page_num,
                        "image": img,
                        "error": str(e),
                        "status": "error"
                    })
                
                progress_bar.progress((i + 1) / total_pages)
            
            status_text.success(f"🎉 批量批改完成！共處理 {total_pages} 份作業。")
            st.balloons()
            
            st.subheader("📊 批改結果總覽")
            for res in results_list:
                with st.expander(f"📄 第 {res['page']} 頁作業批改結果", expanded=(total_pages==1)):
                    subcol1, subcol2 = st.columns([1, 2])
                    
                    with subcol1:
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
