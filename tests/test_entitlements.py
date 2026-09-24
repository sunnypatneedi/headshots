"""Who is on the free plan, and who has premium. No network, no Stripe secret."""
import json

from headshots import entitlements
from headshots.cli import main


def test_nothing_set_is_free(tmp_path):
    assert entitlements.plan(environ={}, receipt_path=tmp_path / "missing.json") == "free"
    assert entitlements.allows("decide.jev", environ={}, receipt_path=tmp_path / "missing.json") is False


def test_the_environment_can_say_free_over_a_receipt(tmp_path):
    path = tmp_path / "receipt.json"
    entitlements.save_receipt(path)
    assert entitlements.plan(environ={"HEADSHOTS_PLAN": "free"}, receipt_path=path) == "free"


def test_a_premium_environment_wins_over_a_broken_receipt(tmp_path):
    path = tmp_path / "receipt.json"
    path.write_text("{")
    assert entitlements.plan(environ={"HEADSHOTS_PLAN": "Premium"}, receipt_path=path) == "premium"


def test_an_unknown_plan_name_is_free(tmp_path):
    path = tmp_path / "receipt.json"
    entitlements.save_receipt(path)
    assert entitlements.plan(environ={"HEADSHOTS_PLAN": "gold"}, receipt_path=path) == "free"


def test_a_saved_receipt_makes_premium(tmp_path):
    path = tmp_path / "receipt.json"
    written = entitlements.save_receipt(path)
    assert written == path
    assert json.loads(path.read_text()) == {"version": 1, "plan": "premium"}
    assert entitlements.plan(environ={}, receipt_path=path) == "premium"
    assert entitlements.allows("decide.jev", environ={}, receipt_path=path) is True


def test_a_broken_receipt_is_free(tmp_path):
    path = tmp_path / "receipt.json"
    path.write_text("{")
    assert entitlements.plan(environ={}, receipt_path=path) == "free"
    path.write_text(json.dumps({"plan": "premium"}))
    assert entitlements.plan(environ={}, receipt_path=path) == "free"
    path.write_text(json.dumps({"version": 2, "plan": "premium"}))
    assert entitlements.plan(environ={}, receipt_path=path) == "free"
    path.write_text(json.dumps({"version": 1, "plan": "gold"}))
    assert entitlements.plan(environ={}, receipt_path=path) == "free"


def test_premium_includes_jev_and_the_remote_placeholder(tmp_path):
    missing = tmp_path / "missing.json"
    assert entitlements.PLANS["premium"] == frozenset(entitlements.FEATURES)
    assert entitlements.allows("decide.jev", environ={"HEADSHOTS_PLAN": "premium"}, receipt_path=missing)
    assert entitlements.allows("decide.remote", environ={"HEADSHOTS_PLAN": "premium"}, receipt_path=missing)
    assert not entitlements.allows("decide.remote", environ={}, receipt_path=missing)


def test_upgrade_writes_a_receipt_and_names_the_checkout_link(tmp_path):
    path = tmp_path / "sub" / "receipt.json"
    text = entitlements.upgrade(
        receipt_path=path,
        environ={"HEADSHOTS_CHECKOUT_URL": "https://buy.stripe.com/test_abc"},
    )
    assert "https://buy.stripe.com/test_abc" in text
    assert json.loads(path.read_text()) == {"version": 1, "plan": "premium"}
    assert "sk_" not in text
    assert "sk_" not in path.read_text()


def test_upgrade_without_a_link_still_writes_the_receipt(tmp_path):
    path = tmp_path / "receipt.json"
    text = entitlements.upgrade(receipt_path=path, environ={})
    assert "HEADSHOTS_CHECKOUT_URL" in text
    assert json.loads(path.read_text())["plan"] == "premium"
    assert entitlements.checkout_url(environ={}) is None


def test_upgrade_does_not_open_a_network_connection(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("upgrade tried the network")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    entitlements.upgrade(receipt_path=tmp_path / "receipt.json", environ={
        "STRIPE_SECRET_KEY": "sk_live_should_not_appear",
        "HEADSHOTS_CHECKOUT_URL": "https://buy.stripe.com/test_abc",
    })
    assert "sk_live_should_not_appear" not in (tmp_path / "receipt.json").read_text()


def test_the_upgrade_command_prints_the_link(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HEADSHOTS_CHECKOUT_URL", "https://buy.stripe.com/test_abc")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_should_not_appear")
    path = tmp_path / "receipt.json"
    assert main(["upgrade", "--receipt", str(path)]) == 0
    out = capsys.readouterr().out
    assert "https://buy.stripe.com/test_abc" in out
    assert "sk_live_should_not_appear" not in out
    assert json.loads(path.read_text()) == {"version": 1, "plan": "premium"}


def test_upgrade_without_a_flag_writes_the_config_receipt(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("HEADSHOTS_CHECKOUT_URL", raising=False)
    assert main(["upgrade"]) == 0
    path = tmp_path / ".config" / "headshots" / "receipt.json"
    assert json.loads(path.read_text()) == {"version": 1, "plan": "premium"}
    assert path == entitlements.receipt_file(environ={})
    assert "HEADSHOTS_CHECKOUT_URL" in capsys.readouterr().out
