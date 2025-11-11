import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import os
import requests
from openai import OpenAI
import json
import openpyxl

# --- 0. 配置与初始化 ---
st.set_page_config(
    page_title="李白生平GIS与RAG整合",
    page_icon="🐉",
    layout="wide"
)

# 初始化OpenAI客户端
# ⚠️ 注意：请确保 DEEPSEEK_API_KEY 环境变量已设置，或在此处替换为您的密钥
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY", "sk-72997944466a4af2bcd52a068895f8cf"), 
    base_url="https://api.deepseek.com"
)

# ----------------------------------------------------
# 全局变量定义
# ----------------------------------------------------
XLSX_FILENAME = "李白人生重要节点与代表作地理位置.xlsx"
location_col = '地点（古称/今称）'
summary_col = '诗作/事件摘要'


# --- 1. RAG 补充函数：抓取CBDB李白人物资料 ---
@st.cache_data(ttl=3600)
def get_cbdb_data(name="李白"):
    """从 CBDB API 获取人物 JSON"""
    url = f"https://cbdb.fas.harvard.edu/cbdbapi/person.php?name={name}&o=json"
    headers = {"User-Agent": "Mozilla/5.0 (Streamlit App)"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            return None
    except Exception:
        return None

# --- 2. 关键地点经纬度数据 (用于匹配) ---
# 这里的坐标和匹配键用于将地名映射到 GIS 坐标
LOCATION_COORDS = {
    "碎叶城": {"lat": 42.8447, "lon": 75.1648, "match_keys": ["碎叶城"]},
    "峨眉山": {"lat": 29.5807, "lon": 103.3592, "match_keys": ["峨眉山"]},
    "蜀中": {"lat": 31.7828, "lon": 104.7570, "match_keys": ["蜀中", "江油"]},
    "荆门/南津关": {"lat": 30.5667, "lon": 111.4500, "match_keys": ["荆门", "南津关"]},
    "岳阳楼": {"lat": 29.3879, "lon": 113.1092, "match_keys": ["岳阳楼", "岳阳"]},
    "安陆": {"lat": 31.3653, "lon": 113.7077, "match_keys": ["安陆"]},
    "黄鹤楼": {"lat": 30.5484, "lon": 114.3168, "match_keys": ["黄鹤楼", "武汉"]},
    "金陵（凤凰台）": {"lat": 32.0415, "lon": 118.7781, "match_keys": ["金陵", "凤凰台", "南京"]},
    "庐山": {"lat": 29.5910, "lon": 115.9922, "match_keys": ["庐山", "九江"]},
    "天姥山": {"lat": 29.5000, "lon": 120.8900, "match_keys": ["天姥山"]},
    "金陵/长干里": {"lat": 32.0298, "lon": 118.7900, "match_keys": ["长干里"]},
    "长安": {"lat": 34.2652, "lon": 108.9500, "match_keys": ["长安", "西安"]},
    "长安/宫廷": {"lat": 34.2652, "lon": 108.9500, "match_keys": ["宫廷"]},
    "长安/洛阳": {"lat": 34.6859, "lon": 112.4600, "match_keys": ["洛阳"]},
    "桃花潭": {"lat": 30.4079, "lon": 118.4230, "match_keys": ["桃花潭", "泾县"]},
    "敬亭山": {"lat": 30.9822, "lon": 118.7844, "match_keys": ["敬亭山", "宣城"]},
    "天门山": {"lat": 31.4285, "lon": 118.3970, "match_keys": ["天门山", "芜湖"]},
    "扬州/旅店": {"lat": 32.3934, "lon": 119.4290, "match_keys": ["扬州"]},
    "夜郎": {"lat": 27.6888, "lon": 106.3773, "match_keys": ["夜郎", "桐梓"]},
    "白帝城": {"lat": 31.0450, "lon": 109.5780, "match_keys": ["白帝城", "奉节"]},
    "秋浦": {"lat": 30.6500, "lon": 117.4800, "match_keys": ["秋浦", "池州"]},
    "当涂": {"lat": 31.5453, "lon": 118.4870, "match_keys": ["当涂", "马鞍山"]},
    # 泛指或主题类地点使用主要游历地坐标
    "蜀道": {"lat": 31.0000, "lon": 107.0000, "match_keys": ["蜀道"]},
    "月下独酌": {"lat": 34.2652, "lon": 108.9500, "match_keys": ["独酌", "月下"]},
    "静夜思": {"lat": 32.3934, "lon": 119.4290, "match_keys": ["静夜思"]},
    "长江沿线": {"lat": 30.5928, "lon": 114.3055, "match_keys": ["长江"]},
    "战城南": {"lat": 35.0000, "lon": 100.0000, "match_keys": ["边塞", "战争"]},
    "送友人": {"lat": 30.5928, "lon": 114.3055, "match_keys": ["送友人"]},
    "将进酒": {"lat": 34.2652, "lon": 108.9500, "match_keys": ["将进酒", "豪饮"]},
    "行路难": {"lat": 34.2652, "lon": 108.9500, "match_keys": ["行路难"]},
}

# --- 3. 数据加载与预处理 (核心修复区) ---
@st.cache_data
def load_and_prepare_data(xlsx_file_name):
    """加载 XLSX 文件，并合并经纬度数据。修复：增加 Hugging Face 路径兼容。"""
    
    # Hugging Face 兼容路径检查 (文件通常在 src/ 目录下)
    file_path = xlsx_file_name
    if not os.path.exists(file_path):
        # 尝试检查 src/ 目录
        src_path = os.path.join("src", xlsx_file_name)
        if os.path.exists(src_path):
            file_path = src_path
        else:
            st.error(f"❌ 错误：未能找到文件 '{xlsx_file_name}'。已检查根目录和 src/ 目录。请确保文件名和路径正确。")
            return pd.DataFrame()

    df = pd.DataFrame()
    
    # 使用 read_excel() 读取 XLSX 文件
    try:
        # 假设数据在第一个工作表（sheet_name=0）
        df = pd.read_excel(file_path, sheet_name=0) 
        st.success(f"✅ 文件 '{file_path}' 已成功加载。")
    except Exception as e:
        st.error(f"❌ 读取 XLSX 文件失败，请检查文件是否损坏或工作表名称是否正确。错误: {e}")
        return pd.DataFrame()
    
    # 清理列名（去除可能存在的首尾空格）
    df.columns = df.columns.str.strip()
    
    # 检查关键列是否存在
    if location_col not in df.columns or summary_col not in df.columns:
        st.error(f"❌ 错误：XLSX 文件中未找到关键列 '{location_col}' 或 '{summary_col}'。当前列名为: {list(df.columns)}")
        return pd.DataFrame()
        
    # --- 经纬度匹配逻辑 ---
    
    coords_list = []
    df['coords_key'] = '' 
    
    for index, row in df.iterrows():
        # 这里需要处理 NaN 或 None 值，否则 .strip() 会报错
        location_str = str(row[location_col]).strip()
        
        match = None
        match_key_found = '未知'
        
        # 遍历 LOCATION_COORDS 查找最合适的匹配
        for key, data in LOCATION_COORDS.items():
            if location_str == key:
                match = data
                match_key_found = key
                break
            # 宽松匹配：检查匹配键是否在地点字符串中
            if any(k in location_str for k in data.get('match_keys', [])):
                match = data
                match_key_found = key
                break
        
        if match:
            coords_list.append((match['lat'], match['lon']))
            df.loc[index, 'coords_key'] = match_key_found
        else:
            # 找不到坐标，使用默认中心点
            coords_list.append((34.0478, 108.4357))
            
    df['Latitude'] = [c[0] for c in coords_list]
    df['Longitude'] = [c[1] for c in coords_list]
    
    return df

# 加载数据
data_df = load_and_prepare_data(XLSX_FILENAME)

# 初始化会话状态
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "highlight_location_key" not in st.session_state:
    st.session_state.highlight_location_key = None  # 存储需要高亮的地点 key

# --- 4. Chatbot 逻辑 (RAG) ---

def run_chatbot(cbdb_data, prompt):
    """运行 RAG 增强的 Chatbot"""
    
    # 构建包含 CBDB 数据的 Prompt
    cbdb_text = json.dumps(cbdb_data, ensure_ascii=False)[:5000] if cbdb_data else "无CBDB资料。"
    
    system_prompt_rag = (
        "你是一个李白生平研究的聊天机器人，能介绍李白的生平、作品和相关地点。"
        "当用户询问地点相关问题时（如某首诗的创作地），请在回答中**给出详细答案，回答完后给出提及**地名（古称/今称），"
        "并确保使用的地名与提供的 GIS 地图节点相匹配，例如：'安陆'，'桃花潭'，'黄鹤楼'，'长安'，'当涂'。"
        "如果回答内容来自你引用的CBDB资料，请在结尾标注'（资料源自CBDB）'，"
        "否则说'（资料来自网络）'。"
        f"\n\n以下是CBDB人物资料（仅供参考和增强）：\n{cbdb_text}"
    )
    
    try:
        # 构建消息列表：新的系统 Prompt 包含 RAG 数据
        messages = [{"role": "system", "content": system_prompt_rag}]
        messages.extend(st.session_state.chat_history[-5:])
        
        # 调用DeepSeek API
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            stream=False
        )
        answer = response.choices[0].message.content.strip()
        
        # 尝试从 Chatbot 回答中提取地名，用于地图高亮
        highlight_key = None
        
        # 遍历所有可能的地点键，检查它们是否在 Chatbot 的回答中出现
        for key in data_df['coords_key'].unique():
            if key != '未知' and key in answer:
                highlight_key = key
                break
        
        st.session_state.highlight_location_key = highlight_key
        return answer
            
    except Exception as e:
        st.session_state.highlight_location_key = None
        return f"Chatbot 发生错误: {str(e)}"

# --- 5. GIS 地图生成函数 ---

def create_li_bai_map(df, highlight_key):
    """根据 DataFrame 生成 Folium 地图，并高亮特定节点"""
    
    if df.empty:
        # 如果数据为空，返回一个默认地图
        return folium.Map(location=[34.0, 108.0], zoom_start=4)

    center_lat = df['Latitude'].mean()
    center_lon = df['Longitude'].mean()
    
    m = folium.Map(
        location=[center_lat, center_lon], 
        zoom_start=4.5, 
        tiles="cartodbdarkmatter"
    )

    # 绘制轨迹线
    points = df[['Latitude', 'Longitude']].values.tolist()
    if len(points) > 1:
        folium.PolyLine(
            points, 
            color="#00AEEF", 
            weight=3, 
            opacity=0.5,
        ).add_to(m)

    # 绘制节点和 Popup
    for index, row in df.iterrows():
        is_highlighted = (row['coords_key'] == highlight_key)
        
        # 弹出窗口内容
        popup_html = f"""
        **序号:** {row['序号']}<br>
        **阶段:** {row['阶段（大致年份）']}<br>
        **地点:** {row['地点（古称/今称）']}<br>
        **事件/诗作:** {row['诗作/事件摘要']}<br>
        **核心情感:** {row['核心情感/主题']}<br>
        **节点类型:** <b>{row['节点类型']}</b>
        """
        
        # 确定标记点样式
        if is_highlighted:
            color = 'orange'
            icon = 'fire'
            tooltip = f"🔥 RAG高亮: {row['地点（古称/今称）']}"
        elif '人生事件' in row['节点类型']:
            color = 'blue'
            icon = 'user'
            tooltip = f"人生事件: {row['地点（古称/今称）']}"
        else:
            color = 'green'
            icon = 'flag'
            tooltip = f"作品创作: {row['地点（古称/今称）']}"
            
        folium.Marker(
            location=[row['Latitude'], row['Longitude']],
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=tooltip,
            icon=folium.Icon(color=color, icon=icon, prefix='fa', icon_color='white')
        ).add_to(m)
        
    return m

# --- 6. 主应用布局 ---

cbdb_data = get_cbdb_data("李白")

st.header("🐉 李白生平 GIS 地图与 Chatbot 交互系统")

if data_df.empty:
    st.error("❌ 无法加载或处理李白生平节点数据，请检查文件路径和列名是否正确。")
    # 如果加载失败，显示原始数据加载错误信息
    st.dataframe(data_df)
else:
    # 使用分栏布局
    col1, col2 = st.columns([1, 1.5])

    # --- 左侧：RAG Chatbot 区域 ---
    with col1:
        st.subheader("💬 CBDB-RAG 李白 Chatbot")
        
        # 提示 RAG 状态
        if cbdb_data:
            st.info("CBDB 资料已加载，增强问答功能。")
        else:
            st.warning("CBDB 资料加载失败，问答功能受限。")
            
        # 显示聊天历史
        for message in st.session_state.chat_history:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
        
        # 处理用户输入
        if prompt := st.chat_input("请输入你的问题 (例如：安陆对李白有什么意义？)..."):
            
            # 显示用户消息
            with st.chat_message("user"):
                st.markdown(prompt)
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            
            # 调用 Chatbot
            with st.chat_message("assistant"):
                with st.spinner('AI 正在思考...'):
                    answer = run_chatbot(cbdb_data, prompt)
                    st.markdown(answer)
                    st.session_state.chat_history.append({"role": "assistant", "content": answer})
                
                # 在 Chatbot 区域底部显示地图高亮提示
                if st.session_state.highlight_location_key:
                    st.success(f"地图已高亮显示：{st.session_state.highlight_location_key}")
                
            # 必须调用 rerun 以刷新地图
            st.rerun()

    # --- 右侧：GIS 地图区域 ---
    with col2:
        st.subheader("🗺️ 李白一生足迹 GIS 可视化")
        st.info("地图轨迹按时间顺序绘制，高亮标记点由左侧 Chatbot 触发。")
        
        # 生成地图
        current_map = create_li_bai_map(data_df, st.session_state.highlight_location_key)
        
        # 显示地图
        st_folium(current_map, width=800, height=700)
