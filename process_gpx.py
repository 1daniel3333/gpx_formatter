import streamlit as st
import re
import os
from io import StringIO

# --- 從 gpx_parser_fix_v2.py 複製過來的核心處理函式 ---

def clean_filename(name):
    """
    從字串中移除不適合做為檔名的字元。
    """
    if not name:
        return "unnamed_track"
    # 移除 XML CDATA 標記
    name = name.replace('<![CDATA[', '').replace(']]>', '').strip()
    # 移除或替換檔名中的無效字元
    return re.sub(r'[\\/*?:"<>|]', '_', name)

def process_gpx_content(file_content, original_filename):
    """
    以最穩健的方式處理 GPX 檔案內容字串：
    1. 嘗試標準解析，若失敗則啟用深度救援模式。
    2. 建立一個全新的、乾淨的 GPX 1.1 檔案內容。
    3. 返回處理後的檔名和 GPX 內容字串。
    """
    try:
        # --- 1. 提取檔名 ---
        name = ""
        # 優先從 <metadata> 或 <trk> 中尋找名稱
        name_match = re.search(r'<(?:metadata|trk)>.*?<name>(.*?)</name>', file_content, re.DOTALL | re.IGNORECASE)
        if name_match:
            name = name_match.group(1).strip()
        
        output_filename = clean_filename(name)
        if not output_filename or output_filename == "unnamed_track":
            base = os.path.basename(original_filename)
            output_filename = os.path.splitext(base)[0]

        # --- 2. 標準解析模式 ---
        waypoints = re.findall(r'<(?:[a-zA-Z0-9]+:)?wpt.*?</(?:[a-zA-Z0-9]+:)?wpt>', file_content, re.DOTALL | re.IGNORECASE)
        tracks = re.findall(r'<(?:[a-zA-Z0-9]+:)?trk>.*?</(?:[a-zA-Z0-9]+:)?trk>', file_content, re.DOTALL | re.IGNORECASE)
        routes = re.findall(r'<(?:[a-zA-Z0-9]+:)?rte>.*?</(?:[a-zA-Z0-9]+:)?rte>', file_content, re.DOTALL | re.IGNORECASE)

        clean_waypoints = [re.sub(r'(</?)[a-zA-Z0-9]+:', r'\1', wpt) for wpt in waypoints]
        clean_tracks = [re.sub(r'(</?)[a-zA-Z0-9]+:', r'\1', trk) for trk in tracks]
        clean_routes = [re.sub(r'(</?)[a-zA-Z0-9]+:', r'\1', rte) for rte in routes]

        # --- 3. 檢查是否需要進入深度救援模式 ---
        if not (clean_waypoints or clean_tracks or clean_routes):
            st.warning(f"'{original_filename}' 標準格式解析失敗，啟用深度救援模式...")
            
            salvaged_waypoints = []
            salvaged_trkpts = []

            point_chunks = re.split(r'(<(?:/)?(?:[a-zA-Z0-9]+:)?(?:wpt|trkpt))', file_content, flags=re.IGNORECASE)
            
            for i in range(1, len(point_chunks), 2):
                tag = point_chunks[i]
                data_chunk = point_chunks[i+1]

                lat_match = re.search(r'lat="([^"]+)"', data_chunk)
                lon_match = re.search(r'lon="([^"]+)"', data_chunk)

                if not lat_match or not lon_match:
                    continue
                
                lat, lon = lat_match.group(1), lon_match.group(1)
                
                ele_match = re.search(r'</ele>([^<]+)</ele>', data_chunk, re.IGNORECASE)
                time_match = re.search(r'</time>([^<]+)</time>', data_chunk, re.IGNORECASE)
                name_match = re.search(r'</name>([^<]+)</name>', data_chunk, re.IGNORECASE)

                if 'wpt' in tag.lower() or name_match:
                    clean_wpt = f'<wpt lat="{lat}" lon="{lon}">'
                    if name_match:
                        clean_wpt += f'<name><![CDATA[{name_match.group(1).strip()}]]></name>'
                    if ele_match:
                        clean_wpt += f'<ele>{ele_match.group(1).strip()}</ele>'
                    if time_match:
                        clean_wpt += f'<time>{time_match.group(1).strip()}</time>'
                    clean_wpt += '</wpt>'
                    salvaged_waypoints.append(clean_wpt)
                elif 'trkpt' in tag.lower():
                    clean_trkpt = f'<trkpt lat="{lat}" lon="{lon}">'
                    if ele_match:
                        clean_trkpt += f'<ele>{ele_match.group(1).strip()}</ele>'
                    if time_match:
                        clean_trkpt += f'<time>{time_match.group(1).strip()}</time>'
                    clean_trkpt += '</trkpt>'
                    salvaged_trkpts.append(clean_trkpt)

            if not (salvaged_waypoints or salvaged_trkpts):
                st.error(f"錯誤：在 '{original_filename}' 中仍然找不到任何有效的座標資料。檔案可能已嚴重損毀。")
                return None, None
            
            clean_waypoints = salvaged_waypoints
            clean_tracks = []
            if salvaged_trkpts:
                track_content = '<trk>'
                track_content += f'<name><![CDATA[{output_filename}]]></name>'
                track_content += '<trkseg>'
                track_content += '\n'.join(salvaged_trkpts)
                track_content += '</trkseg>'
                track_content += '</trk>'
                clean_tracks.append(track_content)

        # --- 4. 建立全新的、乾淨的 GPX 檔案內容 ---
        new_gpx_content_list = [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<gpx version="1.1" creator="Streamlit GPX Cleaner" xmlns="http://www.topografix.com/GPX/1/1" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd">',
            f'  <metadata>',
            f'    <name>{output_filename}</name>',
            f'  </metadata>'
        ]

        if clean_waypoints:
            new_gpx_content_list.extend(clean_waypoints)
        if clean_routes:
            new_gpx_content_list.extend(clean_routes)
        if clean_tracks:
            new_gpx_content_list.extend(clean_tracks)

        new_gpx_content_list.append('</gpx>')
        
        final_gpx_content = '\n'.join(new_gpx_content_list)
        final_filename = f"{output_filename}.gpx"
        
        return final_filename, final_gpx_content

    except Exception as e:
        st.error(f"處理檔案 '{original_filename}' 時發生未預期的嚴重錯誤: {e}")
        return None, None

# --- Streamlit UI 介面 ---

st.set_page_config(page_title="GPX 檔案修復工具", page_icon="🗺️")

st.title('🗺️ GPX 檔案修復與標準化工具')

st.info('**請注意：** 這個工具會嘗試讀取您上傳的 GPX 檔案，並將其轉換為標準的 GPX 1.1 格式。轉換過程中，**原始檔案的檔名將會被用作新檔案內部軌跡的名稱**。')

uploaded_files = st.file_uploader(
    "選擇一個或多個 GPX 檔案", 
    type=['gpx'], 
    accept_multiple_files=True,
    help="您可以一次拖放多個檔案到這裡。"
)

if uploaded_files:
    st.header("處理結果")
    with st.spinner('正在處理檔案中，請稍候...'):
        for uploaded_file in uploaded_files:
            # 讀取上傳檔案的內容
            stringio = StringIO(uploaded_file.getvalue().decode("utf-8"))
            content = stringio.read()
            
            st.markdown(f"---")
            st.write(f"正在處理檔案：`{uploaded_file.name}`")

            # 呼叫核心函式進行處理
            new_filename, new_content = process_gpx_content(content, uploaded_file.name)

            if new_filename and new_content:
                st.success(f"檔案 `{uploaded_file.name}` 已成功轉換！")
                
                # 提供下載按鈕
                st.download_button(
                    label=f"下載修復後的檔案：`{new_filename}`",
                    data=new_content,
                    file_name=new_filename,
                    mime='application/gpx+xml'
                )