# modules/data_exporter.py

import pandas as pd
from io import BytesIO
from datetime import datetime
import xlsxwriter # xlsxwriter 임포트 (Pandas의 to_excel 엔진으로 사용)

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
    기사 DataFrame을 XLSX(Excel) 형식의 BytesIO 객체로 변환하고 스타일링을 적용합니다.
    Args:
        articles_df (pd.DataFrame): 기사 데이터프레임.
        sheet_name (str): 엑셀 시트 이름.
    Returns:
        BytesIO: XLSX 파일 내용이 담긴 BytesIO 객체.
    """
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        articles_df.to_excel(writer, index=False, sheet_name=sheet_name)

        workbook = writer.book
        worksheet = writer.sheets[sheet_name]

        # 헤더 포맷 정의
        header_format = workbook.add_format({
            'bold': True,
            'text_wrap': True,
            'valign': 'vcenter',
            'fg_color': '#D7E4BC', # 연한 녹색 배경
            'border': 1
        })

        # 데이터 행 포맷 (선택적: 홀수/짝수 행 배경색)
        even_row_format = workbook.add_format({'fg_color': '#F2F2F2', 'border': 1}) # 연한 회색
        odd_row_format = workbook.add_format({'border': 1}) # 기본 배경

        # 헤더 적용
        for col_num, value in enumerate(articles_df.columns.values):
            worksheet.write(0, col_num, value, header_format)

        # 열 너비 자동 조정 및 데이터 행 포맷 적용
        for col_num, col_name in enumerate(articles_df.columns):
            max_len = 0
            # 헤더 길이와 데이터 길이 중 최대값 계산
            max_len = max(max_len, len(str(col_name)))
            if not articles_df.empty:
                max_len = max(max_len, articles_df[col_name].astype(str).map(len).max())
            
            # 특정 열은 너비를 제한하거나 더 넓게 설정
            if col_name == '제목':
                worksheet.set_column(col_num, col_num, 50) # 제목 열은 고정 너비
            elif col_name == '내용':
                worksheet.set_column(col_num, col_num, 80) # 내용 열은 고정 너비
            elif col_name == '링크' or col_name == 'url': # 링크 열도 적절히
                worksheet.set_column(col_num, col_num, 40)
            else:
                worksheet.set_column(col_num, col_num, min(max_len + 2, 50)) # 최대 50으로 제한

            # 데이터 행 포맷 적용
            for row_num in range(len(articles_df)):
                cell_format = even_row_format if (row_num + 1) % 2 == 0 else odd_row_format
                for col_idx in range(len(articles_df.columns)):
                    worksheet.write(row_num + 1, col_idx, articles_df.iloc[row_num, col_idx], cell_format)


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
