# modules/database_manager.py

import sqlite3
from datetime import datetime
import streamlit as st # Streamlit의 st.session_state, st.success, st.error 등을 사용하기 위해 임시로 import.
                        # 실제 프로덕션에서는 이 로깅 부분을 다른 방식으로 처리하는 것이 좋습니다.

DB_FILE = 'news_data.db'

def init_db():
    """데이터베이스를 초기화하고 테이블을 생성합니다."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            link TEXT UNIQUE NOT NULL,
            date TEXT NOT NULL,
            content TEXT,
            crawl_timestamp TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def insert_article(article: dict):
    """기사 데이터를 데이터베이스에 삽입합니다. 중복 링크는 건너뛰거나 업데이트합니다."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        # 링크가 이미 존재하면 업데이트, 없으면 삽입
        c.execute("INSERT OR REPLACE INTO articles (link, title, date, content, crawl_timestamp) VALUES (?, ?, ?, ?, ?)",
                  (article['링크'], article['제목'], article['날짜'], article['내용'], datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
    except Exception as e:
        print(f"오류: 데이터베이스 삽입/업데이트 실패 - {e} (링크: {article['링크']})")
    finally:
        conn.close()

def get_all_articles():
    """데이터베이스의 모든 기사 데이터를 가져옵니다."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT title, link, date, content, crawl_timestamp FROM articles ORDER BY date DESC, crawl_timestamp DESC")
    articles = c.fetchall()
    conn.close()
    return articles

def clear_db_content():
    """데이터베이스의 모든 기사 기록을 삭제합니다."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("DELETE FROM articles")
        conn.commit()
        # Streamlit session_state를 직접 업데이트하는 대신, 반환 값으로 상태를 전달하거나
        # 별도의 로깅/메시징 시스템을 사용하는 것이 더 모듈화된 방식이지만,
        # 현재 Streamlit 앱과의 통합을 위해 임시로 유지합니다.
        st.session_state['db_status_message'] = "데이터베이스의 모든 기록이 성공적으로 삭제되었습니다."
        st.session_state['db_status_type'] = "success"
    except Exception as e:
        st.session_state['db_status_message'] = f"데이터베이스 초기화 중 오류 발생: {e}"
        st.session_state['db_status_type'] = "error"
    finally:
        conn.close()
