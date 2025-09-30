from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
import logging
import json
import asyncio
import time
from datetime import datetime
from Google_Sheet import append_row_to_sheet, update_row  # Your module
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

logger = logging.getLogger(__name__)

# ==============================
# SMTP SETTINGS
# ==============================
SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
SMTP_USERNAME = os.getenv('SMTP_USERNAME', '')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')

# ==============================
# EMAIL TEMPLATES (Malay)
# ==============================
EMAIL_TEMPLATES = {
    "Satu Gaji Satu Harapan": {
        "yes_subject": "Pengesahan Hubungan Ejensi - Satu Gaji Satu Harapan",
        "yes_body_template": """
Selamat {name},

Terima kasih kerana berminat dengan pelan '{campaign}'! Kami mengesahkan bahawa ejen kami akan menghubungi anda tidak lama lagi untuk membincangkan butiran lanjut.

Anggaran Premium Anda (Rujukan: {row_reference}):
• Pendapatan Tahunan: {annual_income}
• Umur: {age} tahun
• Tempoh Liputan: {years_of_coverage} tahun
• Liputan Disyorkan: {recommended_coverage}
• Premium Bulanan Anggaran: {monthly_premium}

Jika anda mempunyai sebarang soalan, sila balas email ini atau hubungi kami di [nombor telefon syarikat].

Terima kasih,
Pasukan {campaign}
[Emel Syarikat] | [Laman Web]
        """,
        "no_subject": "Terima Kasih atas Minat Anda - Satu Gaji Satu Harapan",
        "no_body_template": """
Selamat {name},

Terima kasih kerana meneroka pelan '{campaign}'! Walaupun anda tidak mahu dihubungi ejen buat masa ini, kami harap anda akan mempertimbangkannya lagi pada masa hadapan.

Ringkasan Anggaran Premium Anda (Rujukan: {row_reference}):
• Pendapatan Tahunan: {annual_income}
• Umur: {age} tahun
• Tempoh Liputan: {years_of_coverage} tahun
• Liputan Disyorkan: {recommended_coverage}
• Premium Bulanan Anggaran: {monthly_premium}

Hubungi kami bila-bila masa jika anda berubah fikiran!

Terima kasih,
Pasukan {campaign}
[Emel Syarikat] | [Laman Web]
        """
    }
}

def format_currency(amount: float) -> str:
    return f"RM {amount:,.2f}"

# ==============================
# EMAIL TRIGGER FUNCTION
# ==============================
async def trigger_agent_email(
    user_data: Dict[str, Any],
    decision: str,
    campaign_name: str,
    premium_info: Optional[Dict[str, Any]] = None,
    row_reference: Optional[str] = None,
    sheet_row_num: Optional[int] = None
) -> bool:
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        logger.warning("[EMAIL_TRIGGER] SMTP credentials not set. Skipping email.")
        return False

    email = user_data.get('email', '').strip()
    if not email or '@' not in email:
        logger.warning(f"[EMAIL_TRIGGER] Invalid or missing email: {email}")
        return False

    name = user_data.get('name', 'Pelanggan')
    if row_reference is None:
        row_reference = datetime.now().isoformat()[:19]

    template = EMAIL_TEMPLATES.get(campaign_name, EMAIL_TEMPLATES["Satu Gaji Satu Harapan"])
    if decision.lower() == 'yes':
        subject = template["yes_subject"]
        body_template = template["yes_body_template"]
    else:
        subject = template["no_subject"]
        body_template = template["no_body_template"]

    annual_income = format_currency(premium_info.get('annual_income', 0)) if premium_info else "N/A"
    age = str(premium_info.get('age', 'N/A')) if premium_info else "N/A"
    years_of_coverage = str(premium_info.get('years_of_coverage', 'N/A')) if premium_info else "N/A"
    recommended_coverage = format_currency(premium_info.get('recommended_coverage', 0)) if premium_info else "N/A"
    monthly_premium = format_currency(premium_info.get('monthly_premium', 0)) if premium_info else "N/A"

    body = body_template.format(
        name=name, campaign=campaign_name, row_reference=row_reference,
        annual_income=annual_income, age=age, years_of_coverage=years_of_coverage,
        recommended_coverage=recommended_coverage, monthly_premium=monthly_premium
    )

    sender = SMTP_USERNAME
    try:
        msg = MIMEMultipart()
        msg['From'] = sender
        msg['To'] = email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        def send_sync():
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.starttls()
            server.login(sender, SMTP_PASSWORD)
            server.sendmail(sender, email, msg.as_string())
            server.quit()
            return True

        success = await asyncio.to_thread(send_sync)
        if success:
            logger.info(f"[EMAIL_TRIGGER] Email sent to {email} for {campaign_name} (Decision: {decision})")
            if sheet_row_num:
                update_row(sheet_row_num, {
                    'email_status': 'Sent',
                    'email_timestamp': datetime.now().isoformat()
                })
            return True
    except Exception as e:
        logger.error(f"[EMAIL_TRIGGER] Failed: {e}")
        if sheet_row_num:
            update_row(sheet_row_num, {'email_status': 'Failed', 'error': str(e)})
        return False

# ==============================
# PREMIUM CALCULATOR
# ==============================
def calculate_premium_estimation(annual_income, years_of_coverage, age):
    recommended_coverage = annual_income * 10
    if age <= 30:
        rate = 1.20
    elif age <= 40:
        rate = 1.70
    elif age <= 50:
        rate = 2.80
    else:
        rate = 4.50

    units = recommended_coverage / 1000
    annual_premium = max(units * rate, 100)
    monthly_premium = annual_premium / 12

    return {
        'recommended_coverage': recommended_coverage,
        'annual_premium': round(annual_premium, 2),
        'monthly_premium': round(monthly_premium, 2),
        'premium_rate_per_thousand': rate,
        'age': age,
        'years_of_coverage': years_of_coverage,
        'annual_income': annual_income
    }

# ==============================
# STATE
# ==============================
@dataclass
class CampaignState:
    current_step: str = "welcome"
    user_data: Dict[str, Any] = field(default_factory=dict)
    premium_info: Dict[str, Any] = field(default_factory=dict)

    def reset(self):
        self.__init__()

