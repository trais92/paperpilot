from datetime import datetime

import pytest

from paperpilot_ops.config import load_rules
from paperpilot_ops.models import Attachment, Mail


@pytest.fixture
def rules():
    return load_rules()


@pytest.fixture
def make_mail():
    def _make(subject="Test", body="", sender="Absender <info@firma.example>", date="2026-11-20T10:00", attachments=()):
        return Mail(
            id=f"t-{abs(hash((subject, body, date))) % 10**8}",
            date=datetime.fromisoformat(date),
            sender=sender,
            subject=subject,
            body=body,
            attachments=tuple(Attachment(n, c) for n, c in attachments),
        )

    return _make
