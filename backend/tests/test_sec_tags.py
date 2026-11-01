from app.services.sec_tags import tag_resolver


def test_sec_tag_maps_primary_tag():
    value, tag = tag_resolver.extract_metric({"us-gaap:NetIncomeLoss": 125.0}, "net_income")
    assert value == 125.0
    assert tag == "us-gaap:NetIncomeLoss"


def test_sec_tag_unknown_metric_returns_none():
    value, tag = tag_resolver.extract_metric({"us-gaap:SomeOtherTag": 1.0}, "not_a_real_metric")
    assert value is None
    assert tag is None


def test_sec_tag_custom_tag_lookup():
    tag_resolver.add_custom_tag("custom_metric", "us-gaap:CustomThing")
    value, tag = tag_resolver.extract_metric({"us-gaap:CustomThing": 7.0}, "custom_metric")
    assert value == 7.0
    assert tag == "us-gaap:CustomThing"
