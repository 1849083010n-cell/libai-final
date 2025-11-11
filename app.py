import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import os
import requests
from openai import OpenAI
import json
import openpyxl

# --- 0. 版本兼容性检查与页面配置 ---
try:
    import streamlit.version as st_version
    st_version = st_version.__version__
    if st_version < "1.28.0":
        st.warning(f"检测到 Streamlit 版本过旧（{st_version}），可能导致功能异常，建议升级：pip install --upgrade streamlit")
except:
    pass

st.set_page_config(
    page_title="李白生平GIS与RAG整合",
    page_icon="🐉",
    layout="wide"
)

# --- 1. 初始化OpenAI客户端 ---
api_key = os.getenv("DEEPSEEK_API_KEY")
if not api_key:
    st.warning("未检测到 DEEPSEEK_API_KEY 环境变量，将使用测试密钥（功能可能受限）")
    api_key = "sk-72997944466a4af2bcd52a068895f8cf"  # 仅测试用

client = OpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com"
)

# --- 2. 全局变量与经纬度数据 ---
XLSX_FILENAME = "李白人生重要节点与代表作地理位置.xlsx"
location_col = '地点（古称/今称）'
summary_col = '诗作/事件摘要'

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

# --- 3. 数据加载与预处理 ---
@st.cache_data(ttl=3600, show_spinner="正在加载李白生平数据...")
def load_and_prepare_data(xlsx_file_name, time_period=None):
    """加载并处理数据，支持按时段筛选"""
    # 检查文件路径
    file_path = xlsx_file_name
    if not os.path.exists(file_path):
        st.error(f"❌ 未找到数据文件 '{xlsx_file_name}'，请确保文件在仓库根目录")
        return pd.DataFrame(columns=[
            '序号', '阶段（大致年份）', location_col, summary_col,
            '核心情感/主题', '节点类型', 'coords_key', 'Latitude', 'Longitude'
        ])

    # 读取Excel文件
    try:
        df = pd.read_excel(file_path, sheet_name=0)
        df.columns = df.columns.str.strip()
    except Exception as e:
        st.error(f"❌ 读取文件失败：{str(e)}")
        return pd.DataFrame(columns=[
            '序号', '阶段（大致年份）', location_col, summary_col,
            '核心情感/主题', '节点类型', 'coords_key', 'Latitude', 'Longitude'
        ])

    # 检查必要列
    required_cols = [location_col, summary_col, '阶段（大致年份）', '节点类型', '核心情感/主题', '序号']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        st.error(f"❌ 数据文件缺少关键列：{missing_cols}，当前列：{list(df.columns)}")
        return pd.DataFrame(columns=required_cols + ['coords_key', 'Latitude', 'Longitude'])

    # 筛选时段数据
    df = df.copy()
    if time_period:
        if time_period == "youth":
            df = df[df['阶段（大致年份）'].str.contains("青年", na=False)]
        elif time_period == "middle":
            df = df[df['阶段（大致年份）'].str.contains("中年", na=False)]
        elif time_period == "old":
            df = df[df['阶段（大致年份）'].str.contains("晚年", na=False)]

    # 匹配经纬度
    df['coords_key'] = '未知'
    df['Latitude'] = 34.0478  # 默认纬度（长安附近）
    df['Longitude'] = 108.4357  # 默认经度

    for idx, row in df.iterrows():
        location_str = str(row[location_col]).strip()
        for key, data in LOCATION_COORDS.items():
            if location_str == key or any(k in location_str for k in data.get('match_keys', [])):
                df.at[idx, 'coords_key'] = key
                df.at[idx, 'Latitude'] = data['lat']
                df.at[idx, 'Longitude'] = data['lon']
                break

    return df

# --- 4. RAG相关函数 ---
@st.cache_data(ttl=3600, show_spinner="正在加载CBDB史料...")
def get_cbdb_data(name="李白"):
    """从CBDB获取人物数据"""
    try:
        url = f"https://cbdb.fas.harvard.edu/cbdbapi/person.php?name={name}&o=json"
        response = requests.get(url, headers={"User-Agent": "Streamlit App"}, timeout=10)
        return response.json() if response.status_code == 200 else None
    except Exception as e:
        st.warning(f"CBDB数据加载失败：{str(e)}")
        return None

def run_chatbot(cbdb_data, prompt):
    """运行RAG增强的Chatbot"""
    if not prompt:
        return "请输入有效的问题"

    # 构建系统提示
    cbdb_text = json.dumps(cbdb_data, ensure_ascii=False)[:3000] if cbdb_data else "无CBDB资料"
    system_prompt = (
        "你是李白研究专家，需结合提供的史料回答问题。\n"
        "回答需包含与地图匹配的地点名称（如安陆、长安等）。\n"
        f"史料参考：{cbdb_text}\n"
        "资料源自CBDB请标注'（资料源自CBDB）'，否则标注'（资料来自网络）'。"
    )

    try:
        # 构建消息列表
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend([msg for msg in st.session_state.chat_history[-5:] 
                        if msg.get("role") in ["user", "assistant"]])
        messages.append({"role": "user", "content": prompt})

        # 调用API
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0.7
        )
        answer = response.choices[0].message.content.strip()

        # 提取高亮地点
        highlight_key = None
        if not st.session_state.data_df.empty:
            for key in st.session_state.data_df['coords_key'].unique():
                if key != '未知' and key in answer:
                    highlight_key = key
                    break
        st.session_state.highlight_location_key = highlight_key
        return answer

    except Exception as e:
        st.session_state.highlight_location_key = None
        return f"Chatbot错误：{str(e)}（请检查API密钥是否有效）"

# --- 5. 地图生成函数 ---
def create_li_bai_map(df, highlight_key):
    """生成李白足迹地图"""
    if df.empty:
        return folium.Map(location=[34.0, 108.0], zoom_start=4, tiles="cartodbdarkmatter")

    # 计算中心点
    try:
        center_lat = df['Latitude'].mean()
        center_lon = df['Longitude'].mean()
    except:
        center_lat, center_lon = 34.0, 108.0

    m = folium.Map(location=[center_lat, center_lon], zoom_start=4.5, tiles="cartodbdarkmatter")

    # 绘制轨迹线
    points = df[['Latitude', 'Longitude']].dropna().values.tolist()
    if len(points) > 1:
        folium.PolyLine(points, color="#00AEEF", weight=3, opacity=0.5).add_to(m)

    # 绘制标记点
    for idx, row in df.iterrows():
        try:
            if pd.isna(row['Latitude']) or pd.isna(row['Longitude']):
                continue

            # 标记样式
            is_highlighted = (row['coords_key'] == highlight_key)
            color = 'orange' if is_highlighted else 'blue' if '人生事件' in str(row['节点类型']) else 'green'
            icon = 'fire' if is_highlighted else 'user' if '人生事件' in str(row['节点类型']) else 'flag'
            tooltip = f"🔥 高亮: {row[location_col]}" if is_highlighted else f"{row['节点类型']}: {row[location_col]}"

            # 弹窗内容
            popup_html = f"""
            **序号:** {row['序号']}<br>
            **阶段:** {row['阶段（大致年份）']}<br>
            **地点:** {row[location_col]}<br>
            **事件/诗作:** {row[summary_col]}<br>
            **核心情感:** {row['核心情感/主题']}<br>
            **节点类型:** <b>{row['节点类型']}</b>
            """

            folium.Marker(
                location=[row['Latitude'], row['Longitude']],
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=tooltip,
                icon=folium.Icon(color=color, icon=icon, prefix='fa', icon_color='white')
            ).add_to(m)
        except:
            continue

    return m

# --- 6. 会话状态初始化 ---
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "highlight_location_key" not in st.session_state:
    st.session_state.highlight_location_key = None
if "data_df" not in st.session_state:
    try:
        st.session_state.data_df = load_and_prepare_data(XLSX_FILENAME)
        if not isinstance(st.session_state.data_df, pd.DataFrame):
            st.session_state.data_df = pd.DataFrame(columns=[
                '序号', '阶段（大致年份）', location_col, summary_col,
                '核心情感/主题', '节点类型', 'coords_key', 'Latitude', 'Longitude'
            ])
    except:
        st.session_state.data_df = pd.DataFrame(columns=[
            '序号', '阶段（大致年份）', location_col, summary_col,
            '核心情感/主题', '节点类型', 'coords_key', 'Latitude', 'Longitude'
        ])

# --- 7. 主页面逻辑 ---
def main():
    st.header("🐉 李白生平 GIS 地图与 Chatbot 交互系统")
    cbdb_data = get_cbdb_data("李白")

    # 数据为空时的处理
    if st.session_state.data_df.empty:
        st.error("❌ 未加载到有效数据，请检查Excel文件格式和内容")
        return

    # 页面布局
    with st.container():
        col1, col2 = st.columns([1, 1.5], gap="large")

        # 左侧：Chatbot区域
        with col1:
            st.subheader("💬 CBDB-RAG 李白 Chatbot")
            if cbdb_data:
                st.info("已加载CBDB史料，可解答李白生平、作品及地点相关问题")
            else:
                st.warning("CBDB史料加载失败，问答基于公开知识")

            # 显示聊天历史
            for message in st.session_state.chat_history:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])

            # 处理用户输入
            if prompt := st.chat_input("请输入问题（例如：李白在安陆有哪些经历？）"):
                # 添加用户消息
                st.session_state.chat_history.append({"role": "user", "content": prompt})
                with st.chat_message("user"):
                    st.markdown(prompt)

                # 生成回答
                with st.chat_message("assistant"):
                    with st.spinner("AI正在思考..."):
                        answer = run_chatbot(cbdb_data, prompt)
                        st.markdown(answer)
                        st.session_state.chat_history.append({"role": "assistant", "content": answer})
                    # 高亮提示
                    if st.session_state.highlight_location_key:
                        st.success(f"地图已高亮：{st.session_state.highlight_location_key}")

                # 刷新页面（兼容新旧版本）
                try:
                    st.rerun()
                except AttributeError:
                    st.experimental_rerun()

        # 右侧：地图区域
        with col2:
            st.subheader("🗺️ 李白一生完整足迹可视化")
            st.info("左侧提问可触发地图节点高亮，侧边栏可切换青年/中年/晚年分页")
            current_map = create_li_bai_map(st.session_state.data_df, st.session_state.highlight_location_key)
            st_folium(current_map, width=800, height=700)

if __name__ == "__main__":
    main()
