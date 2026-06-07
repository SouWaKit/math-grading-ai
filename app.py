import streamlit as st
from openai import OpenAI
import base64
from PIL import Image, ImageDraw
import io
import json
import fitz 
import re

# ==========================================
# 1. 頁面初始化與 API 設定
# ==========================================
st.set_page_config(page_title="高中數學作業自動批改系統 (終極版)", layout="wide")

if "GEMINI_API_KEY" in st.secrets and "GEMINI_BASE_URL" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
    base_url = st.secrets["GEMINI_BASE_URL"]
    
    if not base_url.endswith("/v1") and not base_url.endswith("/v1/"):
        base_url = base_url.rstrip("/") + "/v1"
        
    client = OpenAI(api_key=api_key, base_url=base_url)
else:
    st.error("⚠️ 請先在 Streamlit Secrets 中設定 GEMINI_API_KEY 與 GEMINI_BASE_URL")
    st.stop()

# ==========================================
# 2. 輔助函式 
# ==========================================
def extract_images_from_pdf(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    images = []
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        pix = page.get_pixmap(matrix=fitz.Matrix(1.3, 1.3))
        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data))
        images.append(img)
    return images

def encode_image(image):
    if image.mode != 'RGB':
        image = image.convert('RGB')
    max_size = 1024
    if max(image.size) > max_size:
        image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    buffered = io.BytesIO()
    image.save(buffered, format="JPEG", quality=75)
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

# 【新增】專門用來讀取「圖片/PDF 評分標準」的 AI 函式
def extract_rubric_with_ai(images_b64_list, model_name):
    system_prompt = "你是一位專業的文字辨識助手。請不要有任何問候語，直接輸出結果。"
    user_prompt = "請幫我仔細辨識圖片中的「數學評分標準」（可能是手寫或列印）。請將其轉換為條理分明的純文字格式，務必保留所有的配分細節與條件。"
    
    content_list = [{"type": "text", "text": user_prompt}]
    for b64 in images_b64_list:
        content_list.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
        
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content_list}
        ],
        max_tokens=1000,
        temperature=0.1
    )
    return response.choices[0].message.content.strip()

def draw_error_boxes(original_image, boxes):
    annotated_image = original_image.copy()
    draw = ImageDraw.Draw(annotated_image)
    width, height = annotated_image.size
    
    if isinstance(boxes, list):
        for box in boxes:
            try:
                if isinstance(box, list) and len(box) == 4:
                    x1 = (box[0] / 100.0) * width
                    y1 = (box[1] / 100.0) * height
                    x2 = (box[2] / 100.0) * width
                    y2 = (box[3] / 100.0) * height
                    draw.rectangle([x1, y1, x2, y2], outline="red", width=4)
            except Exception:
                pass 
    return annotated_image

def robust_json_extract(text):
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        json_str = match.group(0)
    else:
        json_str = text

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        if json_str.count('"') % 2 != 0:
            json_str += '"'
        json_str += '}'
        try:
            return json.loads(json_str)
        except:
            return {
                "recognized_steps": "JSON 解析失敗。",
                "error_analysis": "AI 輸出：\n" + text[:200] + "...",
                "score": "未知",
                "feedback": "解析失敗，請重新批改。",
                "error_boxes": []
            }

def grade_single_image(image_b64, model_name, rubric):
    system_prompt = "你是一位嚴謹的高中數學老師。你【必須】只回傳純 JSON 格式，不要加 ```json，不要有問候語。"
    user_prompt = f"""請根據下方的【評分標準】，詳細批改圖片中的學生數學作業算式。
【評分標準】：
{rubric}

【特殊要求 - 畫錯區域標註】：
如果學生的算式中有錯誤，請在 `error_boxes` 中給出該錯誤在圖片中的「百分比座標範圍」。
格式為 [x1, y1, x2, y2]，數值為 0~100。
例如 [20, 40, 50, 60] 代表 X軸 20%~50%、Y軸 40%~60%。
若全對無錯，請讓 `error_boxes` 保持空陣列 []。

【強制回傳 JSON 格式】：
{{
    "recognized_steps": "辨識到的完整算式與推導",
    "error_analysis": "分析哪裡寫對、哪裡寫錯",
    "score": "純數字分數",
    "feedback": "給學生的評語",
    "error_boxes": [[x1, y1, x2, y2]]
}}"""
    
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
        max_tokens=4000, 
        temperature=0.1
    )
    
    raw_text = response.choices[0].message.content.strip()
    return robust_json_extract(raw_text)

# ==========================================
# 3. 網頁介面 (UI) 設計
# ==========================================
# 初始化 session_state 來儲存評分標準，避免網頁重整時消失
if "rubric_text" not in st.session_state:
    st.session_state.rubric_text = "1. 寫出正確公式：給 2 分\n2. 運算過程正確：給 2 分\n3. 最終答案正確：給 1 分\n(總分 5 分)"

st.title("📝 高中數學作業自動批改系統 (終極版)")
st.markdown("支援 **紅框糾錯**、**PDF 批量批改** 與 **AI 手寫評分標準辨識**。")
st.markdown("---")

col1, col2 = st.columns([1, 1.5])

with col1:
    st.subheader("⚙️ 1. 批改設定")
    
    model_options = {
        "👑 頂級邏輯預覽版 (gemini-3.1-pro-preview)": "gemini-3.1-pro-preview",
        "🚀 極速預覽版 (gemini-3-flash-preview)": "gemini-3-flash-preview",
        "🧠 穩定深度版 (gemini-1.5-pro)": "gemini-1.5-pro"
    }
    selected_friendly_name = st.selectbox("選擇 AI 模型", options=list(model_options.keys()))
    actual_model_name = model_options[selected_friendly_name]
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # ==========================================
    # 評分標準輸入方式切換
    # ==========================================
    st.markdown("**📋 評分標準設定**")
    rubric_mode = st.radio("選擇輸入方式：", ["手動輸入 / 確認區", "上傳文字檔 (.txt)", "上傳手寫/圖片/PDF"], horizontal=True, label_visibility="collapsed")
    
    if rubric_mode == "上傳文字檔 (.txt)":
        rubric_file = st.file_uploader("上傳包含評分標準的純文字檔", type=["txt", "md"])
        if rubric_file is not None:
            st.session_state.rubric_text = rubric_file.read().decode("utf-8")
            st.success("✅ 成功載入文字檔！請在「手動輸入 / 確認區」查看。")
            
    elif rubric_mode == "上傳手寫/圖片/PDF":
        st.info("💡 將手寫筆記或 PDF 拍照上傳，AI 會幫您轉成文字，省下打字時間！")
        rubric_img_file = st.file_uploader("上傳評分標準圖片或 PDF", type=["pdf", "jpg", "png", "jpeg"])
        
        if rubric_img_file is not None:
            if st.button("🔍 讓 AI 辨識這份評分標準", type="primary"):
                with st.spinner("AI 正在努力閱讀您的筆記..."):
                    try:
                        ext = rubric_img_file.name.split('.')[-1].lower()
                        if ext == 'pdf':
                            r_images = extract_images_from_pdf(rubric_img_file.read())
                        else:
                            r_images = [Image.open(rubric_img_file)]
                        
                        b64_list = [encode_image(img) for img in r_images]
                        extracted_text = extract_rubric_with_ai(b64_list, actual_model_name)
                        
                        # 更新到狀態中
                        st.session_state.rubric_text = extracted_text
                        st.success("🎉 辨識完成！請切換到「手動輸入 / 確認區」檢查是否有錯字。")
                    except Exception as e:
                        st.error(f"💥 辨識失敗：{e}")

    # 最終的文字框：無論哪種方式，都在這裡做最後確認
    st.session_state.rubric_text = st.text_area("確認 / 修改最終評分標準", value=st.session_state.rubric_text, height=150)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # 考卷上傳區
    st.markdown("**📄 學生作業上傳**")
    uploaded_file = st.file_uploader("上傳全班作業 (PDF) 或單張圖片 (JPG/PNG)", type=["pdf", "jpg", "png", "jpeg"], label_visibility="collapsed")

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
            st.image(images_to_process[0], caption="學生上傳的原始畫面", use_container_width=True)
            
        st.markdown("---")
        
        if st.button("🚀 開始批量智能批改", type="primary", use_container_width=True):
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            results_list = []
            total_pages = len(images_to_process)
            
            # 使用狀態裡的最新評分標準來批改
            final_rubric = st.session_state.rubric_text
            
            for i, img in enumerate(images_to_process):
                page_num = i + 1
                status_text.text(f"🧠 {actual_model_name} 正在批改第 {page_num} / {total_pages} 頁，並嘗試定位錯誤...")
                
                try:
                    b64_img = encode_image(img)
                    result_json = grade_single_image(b64_img, actual_model_name, final_rubric)
                    
                    annotated_img = draw_error_boxes(img, result_json.get('error_boxes', []))
                    
                    results_list.append({
                        "page": page_num,
                        "original_image": img,
                        "annotated_image": annotated_img,
                        "data": result_json,
                        "status": "success"
                    })
                except Exception as e:
                    results_list.append({
                        "page": page_num,
                        "original_image": img,
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
                        if res['status'] == "success":
                            data = res['data']
                            boxes = data.get('error_boxes', [])
                            
                            if boxes and len(boxes) > 0 and isinstance(boxes[0], list):
                                show_boxes = st.toggle("👁️ 顯示紅框標註", value=True, key=f"toggle_{res['page']}")
                                if show_boxes:
                                    st.image(res['annotated_image'], caption="AI 批改標註圖", use_container_width=True)
                                else:
                                    st.image(res['original_image'], caption="原始畫面", use_container_width=True)
                            else:
                                st.image(res['original_image'], caption="原始畫面 (無錯誤)", use_container_width=True)
                        else:
                            st.image(res['original_image'], use_container_width=True)
                        
                    with subcol2:
                        if res['status'] == "success":
                            data = res['data']
                            st.metric(label="🌟 建議分數", value=f"{data.get('score', '未知')} 分")
                            st.info(f"**💬 評語**：\n{data.get('feedback', '無')}")
                            
                            boxes = data.get('error_boxes', [])
                            if boxes and len(boxes) > 0 and isinstance(boxes[0], list):
                                st.error("🚨 AI 已抓出疑似計算錯誤的區域 (可使用左側開關查看)。")
                            else:
                                st.success("✅ AI 未在圖片中標示出明顯的錯誤區塊。")
                                
                            st.write("**辨識算式：**")
                            st.code(data.get('recognized_steps', '無法辨識'))
                            st.write("**錯誤分析：**")
                            st.write(data.get('error_analysis', '無'))
                        else:
                            st.error(f"💥 此頁批改失敗：{res['error']}")
    else:
        st.info("👈 請先上傳一份 PDF 考卷或單張圖片。")
