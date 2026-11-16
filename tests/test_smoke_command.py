import io
import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


@pytest.mark.django_db
def test_smoke_demo_succeeds_without_model_or_network(settings):
    settings.P24_MODE = "demo"
    output = io.StringIO()
    call_command("smoke_test", stdout=output)
    result = json.loads(output.getvalue())
    assert result["ok"]
    assert "distinct_requests_same_session" in result["checks"]
    assert not result["real_payment_attempted"] and not result["real_otp_sent"]


def test_smoke_does_not_send_demo_data_to_live(settings):
    settings.P24_MODE = "live"
    with pytest.raises(CommandError, match="Expected demo"):
        call_command("smoke_test", stdout=io.StringIO())
