from __future__ import annotations

import email as email_lib
import email.utils
import imaplib
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING, Optional

from langchain_core.tools import tool

if TYPE_CHECKING:
    from agent.config import AgentConfig

MAX_BODY_BYTES = 50 * 1024


def _imap_connect(config: "AgentConfig"):
    if not config.email_host or not config.email_user or not config.email_password:
        raise RuntimeError("Email not configured. Set EMAIL_HOST, EMAIL_USER, EMAIL_PASSWORD.")
    M = imaplib.IMAP4_SSL(config.email_host, config.email_port_imap)
    M.login(config.email_user, config.email_password)
    return M


def _smtp_connect(config: "AgentConfig"):
    if not config.email_host or not config.email_user or not config.email_password:
        raise RuntimeError("Email not configured. Set EMAIL_HOST, EMAIL_USER, EMAIL_PASSWORD.")
    S = smtplib.SMTP(config.email_host, config.email_port_smtp)
    S.ehlo()
    S.starttls()
    S.login(config.email_user, config.email_password)
    return S


def _decode_header(raw: str) -> str:
    parts = email_lib.header.decode_header(raw)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return "".join(decoded)


def _get_text_body(msg) -> str:
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition", ""))
            if ctype == "text/plain" and "attachment" not in disp:
                charset = part.get_content_charset() or "utf-8"
                body += part.get_payload(decode=True).decode(charset, errors="replace")
    else:
        charset = msg.get_content_charset() or "utf-8"
        body = msg.get_payload(decode=True).decode(charset, errors="replace")
    return body[:MAX_BODY_BYTES]


def create_email_tools(config: "AgentConfig") -> list:

    @tool
    def email_list(folder: str = "INBOX", limit: int = 20) -> str:
        """List recent emails in a folder.

        Returns sender, subject, date, and read/unread status for each message.

        Args:
            folder: Mailbox folder name (default: INBOX).
            limit: Maximum number of messages to return (default: 20).
        """
        try:
            M = _imap_connect(config)
            M.select(folder)
            _, data = M.search(None, "ALL")
            ids = data[0].split()
            ids = ids[-limit:]  # most recent
            results = []
            for uid in reversed(ids):
                _, msg_data = M.fetch(uid, "(RFC822.HEADER FLAGS)")
                raw = msg_data[0][1]
                msg = email_lib.message_from_bytes(raw)
                flags = str(msg_data[0])
                read = "\\Seen" in flags
                results.append(
                    f"ID:{uid.decode()} | {'READ' if read else 'UNREAD'} | "
                    f"From:{_decode_header(msg.get('From',''))} | "
                    f"Subject:{_decode_header(msg.get('Subject',''))} | "
                    f"Date:{msg.get('Date','')}"
                )
            M.logout()
            return "\n".join(results) if results else "No messages found."
        except Exception as exc:
            return f"Error: {exc}"

    @tool
    def email_read(email_id: str) -> str:
        """Read the full body of an email (excluding attachments). Output capped at 50 KB.

        Args:
            email_id: The numeric message ID as returned by email_list.
        """
        try:
            M = _imap_connect(config)
            M.select("INBOX")
            _, msg_data = M.fetch(email_id.encode(), "(RFC822)")
            raw = msg_data[0][1]
            msg = email_lib.message_from_bytes(raw)
            from_ = _decode_header(msg.get("From", ""))
            to_ = _decode_header(msg.get("To", ""))
            subject = _decode_header(msg.get("Subject", ""))
            date_ = msg.get("Date", "")
            body = _get_text_body(msg)
            M.logout()
            return (
                f"From: {from_}\nTo: {to_}\nSubject: {subject}\nDate: {date_}\n\n{body}"
            )
        except Exception as exc:
            return f"Error: {exc}"

    @tool
    def email_send(
        to: str,
        subject: str,
        body: str,
        cc: Optional[str] = None,
        confirm: bool = False,
    ) -> str:
        """Send an email. Uses two-phase confirmation for safety.

        Call first with confirm=False (default) to get a draft preview.
        After the user confirms, call again with confirm=True to actually send.

        Args:
            to: Recipient email address.
            subject: Email subject line.
            body: Plain-text email body.
            cc: Optional CC addresses (comma-separated).
            confirm: False returns a draft; True sends the email.
        """
        draft = {"to": to, "cc": cc or "", "subject": subject, "body": body}
        if not confirm:
            import json
            return json.dumps({"status": "pending_confirmation", "draft": draft})

        try:
            S = _smtp_connect(config)
            msg = MIMEMultipart()
            msg["From"] = config.email_user
            msg["To"] = to
            msg["Subject"] = subject
            if cc:
                msg["Cc"] = cc
            msg.attach(MIMEText(body, "plain", "utf-8"))
            recipients = [to] + ([cc] if cc else [])
            S.sendmail(config.email_user, recipients, msg.as_string())
            S.quit()
            return '{"status": "sent"}'
        except Exception as exc:
            return f"Error sending email: {exc}"

    @tool
    def email_reply(email_id: str, body: str, confirm: bool = False) -> str:
        """Reply to an email. Uses two-phase confirmation for safety.

        Call first with confirm=False to preview the reply draft.
        After user confirmation, call again with confirm=True to send.

        Args:
            email_id: The ID of the message to reply to.
            body: Reply body text.
            confirm: False returns a draft preview; True sends the reply.
        """
        try:
            M = _imap_connect(config)
            M.select("INBOX")
            _, msg_data = M.fetch(email_id.encode(), "(RFC822)")
            raw = msg_data[0][1]
            original = email_lib.message_from_bytes(raw)
            M.logout()
        except Exception as exc:
            return f"Error fetching original message: {exc}"

        reply_to = original.get("Reply-To") or original.get("From", "")
        orig_subject = _decode_header(original.get("Subject", ""))
        subject = orig_subject if orig_subject.startswith("Re:") else f"Re: {orig_subject}"

        import json
        draft = {"to": reply_to, "subject": subject, "body": body}
        if not confirm:
            return json.dumps({"status": "pending_confirmation", "draft": draft})

        try:
            S = _smtp_connect(config)
            msg = MIMEMultipart()
            msg["From"] = config.email_user
            msg["To"] = reply_to
            msg["Subject"] = subject
            msg["In-Reply-To"] = original.get("Message-ID", "")
            msg.attach(MIMEText(body, "plain", "utf-8"))
            S.sendmail(config.email_user, [reply_to], msg.as_string())
            S.quit()
            return '{"status": "sent"}'
        except Exception as exc:
            return f"Error sending reply: {exc}"

    @tool
    def email_search(query: str, folder: str = "INBOX") -> str:
        """Search emails by keyword, sender, or date range.

        Args:
            query: Search query string (e.g. "from:boss@example.com", "subject:report", or a keyword).
            folder: Mailbox folder to search (default: INBOX).
        """
        try:
            M = _imap_connect(config)
            M.select(folder)

            # Simple heuristic: parse common prefixes
            q = query.strip()
            if q.lower().startswith("from:"):
                criteria = f'FROM "{q[5:].strip()}"'
            elif q.lower().startswith("subject:"):
                criteria = f'SUBJECT "{q[8:].strip()}"'
            elif q.lower().startswith("since:"):
                criteria = f'SINCE "{q[6:].strip()}"'
            else:
                criteria = f'TEXT "{q}"'

            _, data = M.search(None, criteria)
            ids = data[0].split()
            results = []
            for uid in reversed(ids[-20:]):
                _, msg_data = M.fetch(uid, "(RFC822.HEADER)")
                raw = msg_data[0][1]
                msg = email_lib.message_from_bytes(raw)
                results.append(
                    f"ID:{uid.decode()} | "
                    f"From:{_decode_header(msg.get('From',''))} | "
                    f"Subject:{_decode_header(msg.get('Subject',''))} | "
                    f"Date:{msg.get('Date','')}"
                )
            M.logout()
            return "\n".join(results) if results else "No messages matched the query."
        except Exception as exc:
            return f"Error: {exc}"

    return [email_list, email_read, email_send, email_reply, email_search]
