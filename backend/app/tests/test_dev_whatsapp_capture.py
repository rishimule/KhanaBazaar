# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
import app.models as models
from app.models.dev_whatsapp import DevWhatsApp


def test_dev_whatsapp_is_registered():
    assert "DevWhatsApp" in models.__all__
    assert DevWhatsApp.__tablename__ == "dev_whatsapp"


def test_dev_whatsapp_fields():
    row = DevWhatsApp(to_phone="+918888888888", body="hi")
    assert row.provider == "console"
    assert row.template is None
    assert row.category is None
