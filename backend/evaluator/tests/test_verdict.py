import pytest

from evaluator.signals import OK, RISK, UNKNOWN, WATCH, Signal, decide_verdict


def signal(signal_id: str, status: str) -> Signal:
    return Signal(signal_id, signal_id, status, "", "", "")


@pytest.mark.parametrize(
    "statuses, level",
    [
        ({"activity": OK, "releases": OK}, "low"),
        ({"releases": WATCH}, "low"),
        ({"releases": WATCH, "bus_factor": WATCH}, "medium"),
        ({"activity": RISK}, "medium"),
        ({"activity": RISK, "issues": RISK}, "high"),
        ({"status": RISK}, "high"),
        ({"license": RISK}, "high"),
        ({"bus_factor": RISK}, "high"),
        ({"activity": UNKNOWN, "issues": UNKNOWN, "bus_factor": UNKNOWN}, "low"),
    ],
)
def test_verdict_levels(statuses, level):
    verdict = decide_verdict([signal(signal_id, status) for signal_id, status in statuses.items()])
    assert verdict.level == level


def test_reasons_list_risks_before_watches_in_signal_order():
    verdict = decide_verdict([signal("license", WATCH), signal("activity", RISK), signal("releases", WATCH)])
    assert verdict.reasons == ["activity", "license", "releases"]
    assert verdict.headline == "Medium regret risk"


def test_low_verdict_headline():
    assert decide_verdict([signal("activity", OK)]).headline == "Low regret risk"


def test_high_verdict_headline():
    assert decide_verdict([signal("status", RISK)]).headline == "High regret risk"
