import os
import logging
from typing import List
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ---------------- Logging Setup ----------------
logger = logging.getLogger("chatbot")
logger.setLevel(logging.INFO)
if not logger.hasHandlers():
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# ---------------- Google Sheets Setup ----------------
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "credential.json")
SPREADSHEET_ID = os.getenv("GOOGLE_SHEET_ID", "109fc5EkBwdHc4pZYEzYMTqknxw0ImGGiI3kgmIo95Vc")
SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "Sheet1")

credentials = None
service = None


def init_sheets_service():
    """Inisialisasi Google Sheets API service dengan Service Account credentials."""
    global credentials, service
    if service is not None:
        return service

    try:
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        service = build("sheets", "v4", credentials=credentials)
        logger.info("✅ Google Sheets service initialized successfully")
        return service
    except Exception as e:
        logger.error(f"❌ Failed to initialize Google Sheets service: {e}")
        raise


def append_row_to_sheet(row: List[str]) -> None:
    """
    Menambahkan satu baris data ke Google Sheet di baris kosong berikutnya.

    Args:
        row (List[str]): Data yang akan ditambahkan.
    """
    try:
        if not row or not isinstance(row, list):
            raise ValueError("Row must be a non-empty list of strings")

        if not service:
            init_sheets_service()

        sheet = service.spreadsheets()
        body = {"values": [row]}

        result = sheet.values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{SHEET_NAME}!A:A2",   # selalu tambah di baris kosong paling bawah
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body,
        ).execute()

        updates = result.get("updates", {})
        updated_rows = updates.get("updatedRows", 0)
        logger.info(
            f"✅ Appended {updated_rows} row(s) to sheet '{SHEET_NAME}' "
            f"in spreadsheet '{SPREADSHEET_ID}'. Data: {row}"
        )
    except HttpError as http_err:
        logger.error(f"❌ HTTP error while appending row: {http_err}")
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error while appending row: {e}")
        raise


# ---------------- Example Usage ----------------
if __name__ == "__main__":
    try:
        test_row = ["Ely", "ChatBot", "Hello World!", "2025-09-19"]
        append_row_to_sheet(test_row)
    except Exception as err:
        logger.error(f"Error in main: {err}")
