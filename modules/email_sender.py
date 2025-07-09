# modules/email_sender.py

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from loguru import logger
import os

def send_email_with_report(
    sender_email: str,
    sender_password: str, # 또는 앱 비밀번호
    receiver_email: str,
    smtp_server: str,
    smtp_port: int,
    subject: str,
    body: str,
    attachment_data: bytes = None, # 첨부 파일 데이터 (BytesIO.getvalue() 결과)
    attachment_filename: str = None, # 첨부 파일 이름
    report_format: str = "markdown" # 본문 형식 (plain 또는 html)
):
    """
    이메일을 통해 보고서를 전송합니다.

    Args:
        sender_email (str): 발신자 이메일 주소.
        sender_password (str): 발신자 이메일 비밀번호 또는 앱 비밀번호.
        receiver_email (str): 수신자 이메일 주소.
        smtp_server (str): SMTP 서버 주소 (예: 'smtp.gmail.com').
        smtp_port (int): SMTP 포트 (예: 587).
        subject (str): 이메일 제목.
        body (str): 이메일 본문 내용.
        attachment_data (bytes, optional): 첨부할 파일의 바이너리 데이터. Defaults to None.
        attachment_filename (str, optional): 첨부 파일 이름. Defaults to None.
        report_format (str): 본문 형식. 'plain' 또는 'html' (마크다운은 'html'로 변환하여 사용).
    """
    try:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = receiver_email
        msg['Subject'] = subject

        # 본문 추가 (마크다운을 HTML로 변환하여 이메일 본문으로 사용)
        if report_format == "markdown":
            # 마크다운을 HTML로 변환하는 라이브러리 (예: markdown)가 필요할 수 있습니다.
            # 여기서는 간단하게 <pre> 태그를 사용하여 마크다운을 유지하는 형태로 예시를 작성합니다.
            # 실제로는 markdown 라이브러리 등을 사용하여 더 예쁘게 변환하는 것이 좋습니다.
            html_body = f"""\
            <html>
              <body>
                <p>안녕하세요!</p>
                <p>요청하신 뉴스 트렌드 분석 보고서입니다.</p>
                <pre>{body}</pre>
                <p>감사합니다.</p>
              </body>
            </html>
            """
            msg.attach(MIMEText(html_body, 'html'))
        else:
            msg.attach(MIMEText(body, 'plain'))

        # 첨부 파일 추가
        if attachment_data and attachment_filename:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(attachment_data)
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename= {attachment_filename}')
            msg.attach(part)

        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()  # TLS 보안 시작
        server.login(sender_email, sender_password)
        text = msg.as_string()
        server.sendmail(sender_email, receiver_email, text)
        server.quit()
        logger.info(f"이메일이 {receiver_email} (으)로 성공적으로 전송되었습니다.")
        return True
    except Exception as e:
        logger.error(f"이메일 전송 중 오류 발생: {e}")
        return False