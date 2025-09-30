# This file makes the Campaign2 directory a Python package
from .tabung_warisan import TabungWarisanCampaign, tabung_warisan_campaign, tabung_warisan_campaign_instance

# Re-export the campaign instance and class
__all__ = [
    'TabungWarisanCampaign',
    'tabung_warisan_campaign',
    'tabung_warisan_campaign_instance'
]
