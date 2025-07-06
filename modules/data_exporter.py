# modules/data_exporter.py

import pandas as pd
from io import BytesIO
from datetime import datetime

def export_articles_to_txt(articles_list: list[dict], file_prefix: str = "news_articles") -> str:
    """
    기사 목록을 텍스트 형식으로 변환합니다.
    Args:
        articles_list (list[dict]): 기사 데이터 목록.
        file_prefix (str): 파일 이름 접두사.
    Returns:
        str: 텍스트 파일 내용.
    """
    txt_data_lines = []
    for article in articles_list:
        txt_data_lines.append(f"제목: {article.get('제목', 'N/A')}")
        txt_data_lines.append(f"링크: {article.get('링크', 'N/A')}")
        txt_data_lines.append(f"날짜: {article.get('날짜', 'N/A')}")
        txt_data_lines.append(f"내용: {article.get('내용', 'N/A')}")
        if '수집_시간' in article: # 모든 수집 뉴스에만 있는 필드
            txt_data_lines.append(f"수집 시간: {article.get('수집_시간', 'N/A')}")
        txt_data_lines.append("-" * 50) # 구분선
    return "\n".join(txt_data_lines)

def export_articles_to_csv(articles_df: pd.DataFrame) -> BytesIO:
    """
    기사 DataFrame을 CSV 형식의 BytesIO 객체로 변환합니다.
    Args:
        articles_df (pd.DataFrame): 기사 데이터프레임.
    Returns:
        BytesIO: CSV 파일 내용이 담긴 BytesIO 객체.
    """
    output = BytesIO()
    # utf-8-sig는 엑셀에서 한글 깨짐 방지를 위해 BOM(Byte Order Mark)을 포함합니다.
    output.write(articles_df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig'))
    output.seek(0)
    return output

def export_articles_to_excel(articles_df: pd.DataFrame, sheet_name: str = "Sheet1") -> BytesIO:
    """
    기사 DataFrame을 XLSX(Excel) 형식의 BytesIO 객체로 변환합니다.
    Args:
        articles_df (pd.DataFrame): 기사 데이터프레임.
        sheet_name (str): 엑셀 시트 이름.
    Returns:
        BytesIO: XLSX 파일 내용이 담긴 BytesIO 객체.
    """
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        articles_df.to_excel(writer, index=False, sheet_name=sheet_name)
    output.seek(0)
    return output

def generate_filename(prefix: str, extension: str) -> str:
    """
    현재 시간을 기반으로 파일 이름을 생성합니다.
    Args:
        prefix (str): 파일 이름 접두사.
        extension (str): 파일 확장자 (예: 'txt', 'csv', 'xlsx').
    Returns:
        str: 생성된 파일 이름.
    """
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{extension}"
