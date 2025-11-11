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
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY", "sk-72997944466a4af2bcd52a068895f8cf"), 
    base_url="https://api.deepseek.com"
)

# --- 全局变量定义 ---
XLSX_FILENAME = "李白人生重要节点与代表作地理位置.xlsx"
location_col = '地点（古称/今称）'
summary_col = '诗作/事件摘要'

# 地点经纬度数据（不变）
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
    "蜀道": {"lat": 31.0000, "lon": 107.0000, "match_keys": ["蜀道"]},
    "月下独酌": {"lat": 34.2652, "lon": 108.9500, "match_keys": ["独酌", "月下"]},
    "静夜思": {"lat": 32.3934, "lon": 119.4290, "match_keys": ["静夜思"]},
    "长江沿线": {"lat": 30.5928, "lon": 114.3055, "match_keys": ["长江"]},
    "战城南": {"lat": 35.0000, "lon": 100.0000, "match_keys": ["边塞", "战争"]},
    "送友人": {"lat": 30.5928, "lon": 114.3055, "match_keys": ["送友人"]},
    "将进酒": {"lat": 34.2652, "lon": 108.9500, "match_keys": ["将进酒", "豪饮"]},
    "行路难": {"lat": 34.2652, "lon": 108.9500, "match_keys": ["行路难"]},
}

# --- 数据加载与预处理（简化路径，适配多页面共享）---
@st.cache_data
def load_and_prepare_data(xlsx_file_name, time_period=None):
    """加载数据，支持按时段筛选（time_period: youth/middle/old）"""
    file_path = xlsx_file_name
    if not os.path.exists(file_path):
        st.error(f"❌ 未找到数据文件 '{xlsx_file_name}'，请确保文件在仓库根目录。")
        return pd.DataFrame()

    try:
        df = pd.read_excel(file_path, sheet_name=0)
        df.columns = df.columns.str.strip()
    except Exception as e:
        st.error(f"❌ 读取文件失败：{e}")
        return pd.DataFrame()

    # 检查关键列
    required_cols = [location_col, summary_col, '阶段（大致年份）', '节点类型', '核心情感/主题', '序号']
    if not all(col in df.columns for col in required_cols):
        st.error(f"❌ 数据文件缺少关键列，当前列名：{list(df.columns)}")
        return pd.DataFrame()

    # 按时段筛选数据（核心新增逻辑）
    if time_period:
        # 假设 Excel 中“阶段（大致年份）”列格式如：“701-725（青年）”“726-742（中年）”“743-762（晚年）”
        # 可根据实际 Excel 格式调整筛选条件（比如按年份范围）
        if time_period == "youth":
            df = df[df['阶段（大致年份）'].str.contains("青年", na=False)]
        elif time_period == "middle":
            df = df[df['阶段（大致年份）'].str.contains("中年", na=False)]
        elif time_period == "old":
            df = df[df['阶段（大致年份）'].str.contains("晚年", na=False)]

    # 匹配经纬度（不变）
    coords_list = []
    df['coords_key'] = '未知'
    for index, row in df.iterrows():
        location_str = str(row[location_col]).strip()
        match = None
        match_key = '未知'
        for key, data in LOCATION_COORDS.items():
            if location_str == key or any(k in location_str for k in data.get('match_keys', [])):
                match = data
                match_key = key
                break
        if match:
            coords_list.append((match['lat'], match['lon']))
            df.loc[index, 'coords_key'] = match_key
        else:
            coords_list.append((34.0478, 108.4357))  # 默认坐标

    df['Latitude'] = [c[0] for c in coords_list]
    df['Longitude'] = [c[1] for c in coords_list]
    return df

# --- RAG Chatbot 逻辑（不变）---
@st.cache_data(ttl=3600)
def get_cbdb_data(name="李白"):
    url = f"https://cbdb.fas.harvard.edu/cbdbapi/person.php?name={name}&o=json"
    headers = {"User-Agent": "Mozilla/5.0 (Streamlit App)"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        return response.json() if response.status_code == 200 else None
    except Exception:
        return None

def run_chatbot(cbdb_data, prompt):
    cbdb_text = json.dumps(cbdb_data, ensure_ascii=False)[:5000] if cbdb_data else "无CBDB资料。"
    system_prompt_rag = (
        "你是李白生平研究专家，能介绍李白的生平、作品和相关地点。"
        "当用户询问地点或时段相关问题时，需给出详细答案，并明确提及对应的古称/今称，"
        "确保与GIS地图节点匹配（如安陆、桃花潭、长安等）。"
        "资料源自CBDB请标注'（资料源自CBDB）'，否则标注'（资料来自网络）'。"
        f"\n\nCBDB人物资料：\n{cbdb_text}"
    )
    try:
        messages = [{"role": "system", "content": system_prompt_rag}]
        messages.extend(st.session_state.chat_history[-5:])
        response = client.chat.completions.create(
            model="deepseek-chat", messages=messages, stream=False
        )
        answer = response.choices[0].message.content.strip()
        # 提取高亮地点
        highlight_key = None
        for key in st.session_state.data_df['coords_key'].unique():
            if key != '未知' and key in answer:
                highlight_key = key
                break
        st.session_state.highlight_location_key = highlight_key
        return answer
    except Exception as e:
        st.session_state.highlight_location_key = None
        return f"Chatbot 错误：{str(e)}"

# --- 地图生成函数（不变）---
def create_li_bai_map(df, highlight_key):
    if df.empty:
        return folium.Map(location=[34.0, 108.0], zoom_start=4)
    center_lat = df['Latitude'].mean()
    center_lon = df['Longitude'].mean()
    m = folium.Map(location=[center_lat, center_lon], zoom_start=4.5, tiles="cartodbdarkmatter")
    # 绘制轨迹
    points = df[['Latitude', 'Longitude']].values.tolist()
    if len(points) > 1:
        folium.PolyLine(points, color="#00AEEF", weight=3, opacity=0.5).add_to(m)
    # 绘制节点
    for index, row in df.iterrows():
        is_highlighted = (row['coords_key'] == highlight_key)
        popup_html = f"""
        **序号:** {row['序号']}<br>
        **阶段:** {row['阶段（大致年份）']}<br>
        **地点:** {row['地点（古称/今称）']}<br>
        **事件/诗作:** {row['诗作/事件摘要']}<br>
        **核心情感:** {row['核心情感/主题']}<br>
        **节点类型:** <b>{row['节点类型']}</b>
        """
        color = 'orange' if is_highlighted else 'blue' if '人生事件' in row['节点类型'] else 'green'
        icon = 'fire' if is_highlighted else 'user' if '人生事件' in row['节点类型'] else 'flag'
        tooltip = f"🔥 高亮: {row['地点（古称/今称）']}" if is_highlighted else f"{row['节点类型']}: {row['地点（古称/今称）']}"
        folium.Marker(
            location=[row['Latitude'], row['Longitude']],
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=tooltip,
            icon=folium.Icon(color=color, icon=icon, prefix='fa', icon_color='white')
        ).add_to(m)
    return m

# --- 初始化会话状态 ---
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "highlight_location_key" not in st.session_state:
    st.session_state.highlight_location_key = None
if "data_df" not in st.session_state:
    st.session_state.data_df = load_and_prepare_data(XLSX_FILENAME)  # 全量数据

# --- 主页面布局 ---
st.header("🐉 李白生平 GIS 地图与 Chatbot 交互系统")
cbdb_data = get_cbdb_data("李白")

if st.session_state.data_df.empty:
    st.error("❌ 无法加载李白生平数据，请检查文件路径和格式。")
else:
    col1, col2 = st.columns([1, 1.5])
    # 左侧 Chatbot
    with col1:
        st.subheader("💬 CBDB-RAG 李白 Chatbot")
        st.info("可询问李白生平、作品、地点意义，支持地图高亮") if cbdb_data else st.warning("CBDB 资料加载失败，问答功能受限")
        # 聊天历史
        for message in st.session_state.chat_history:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
        # 用户输入
        if prompt := st.chat_input("例如：李白青年时期去过哪些地方？安陆对李白有什么意义？"):
            with st.chat_message("user"):
                st.markdown(prompt)
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            with st.chat_message("assistant"):
                with st.spinner('AI 思考中...'):
                    answer = run_chatbot(cbdb_data, prompt)
                    st.markdown(answer)
                    st.session_state.chat_history.append({"role": "assistant", "content": answer})
                if st.session_state.highlight_location_key:
                    st.success(f"地图已高亮：{st.session_state.highlight_location_key}")
            st.rerun()
    # 右侧全时段地图
    with col2:
        st.subheader("🗺️ 李白一生完整足迹可视化")
        st.info("左侧 Chatbot 提问可触发地图节点高亮，侧边栏可切换时段分页")
        current_map = create_li_bai_map(st.session_state.data_df, st.session_state.highlight_location_key)
        st_folium(current_map, width=800, height=700)
