from datetime import datetime
from hrd_py.client import HRDClient
from hrd_py.models import Domain


def test_client_list_domains(mocker):
    client = HRDClient("login", "pass", "deadbeef")

    mock_api = mocker.patch.object(client, "api")

    # Mock domain_list responses (pagination)
    mock_api.domain_list.side_effect = [["domain1.pl", "domain2.pl"], []]

    # Mock domain_info responses
    mock_api.domain_info.side_effect = [
        {"status": "registered", "exDate": "2026-06-30"},
        {"status": "expired", "exDate": "2026-05-01"},
    ]

    domains = client.list_domains()

    assert len(domains) == 2
    assert domains[0].name == "domain1.pl"
    assert domains[0].status == "registered"
    assert domains[0].expiry_date == datetime(2026, 6, 30)
    assert domains[1].name == "domain2.pl"
    assert domains[1].status == "expired"


def test_domain_is_expiring_soon():
    import datetime as dt

    now = datetime.now()

    d_soon = Domain(name="soon.pl", status="ok", expiry_date=now + dt.timedelta(days=5))
    d_far = Domain(name="far.pl", status="ok", expiry_date=now + dt.timedelta(days=40))

    assert d_soon.is_expiring_soon() is True
    assert d_far.is_expiring_soon() is False
