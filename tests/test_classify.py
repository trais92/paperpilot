from personal_ops.classify import UNCLEAR, LLMClassifier, RuleClassifier


def test_invitation_beats_confirmation(rules, make_mail):
    m = make_mail("Einladung zum Interview", "Zu Ihrer Bewerbung als Projektmanager laden wir Sie ein.")
    assert RuleClassifier(rules).classify(m).label == "bewerbung/einladung"


def test_job_alert_is_advertising_even_with_job_words(rules, make_mail):
    m = make_mail(
        "Neue Jobs für dich", "Stelle als Projektmanager. Job-Alert abbestellen.", sender="<jobalert@portal.example>"
    )
    assert RuleClassifier(rules).classify(m).label == "werbung"


def test_private_category(rules, make_mail):
    m = make_mail("Ihr Versicherungsschein", "Anbei die Police.")
    assert RuleClassifier(rules).classify(m).label == "privat/versicherungen"


def test_low_score_goes_to_human(rules, make_mail):
    c = RuleClassifier(rules).classify(make_mail("Hallo", "Wie geht's?"))
    assert c.label == UNCLEAR and c.confidence == 0.0


def test_group_without_subtype_is_sonstiges(rules, make_mail):
    m = make_mail("Ihre Bewerbung", "Wir haben eine Bitte zu Ihren Unterlagen.")
    assert RuleClassifier(rules).classify(m).label == "bewerbung/sonstiges"


class _FakeBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class _FakeResponse:
    def __init__(self, text, stop_reason="end_turn"):
        self.content = [_FakeBlock(text)]
        self.stop_reason = stop_reason


class _FakeClient:
    def __init__(self, response):
        self.calls = []
        outer = self

        class _Messages:
            def create(self, **kwargs):
                outer.calls.append(kwargs)
                return response

        class _Beta:
            messages = _Messages()

        self.beta = _Beta()


def test_llm_classifier_parses_structured_output(rules, make_mail):
    client = _FakeClient(_FakeResponse('{"label": "werbung", "confidence": 0.9, "reason": "Newsletter"}'))
    c = LLMClassifier(rules, client=client).classify(make_mail("Rabatt", "Newsletter"))
    assert c.label == "werbung"
    schema = client.calls[0]["output_config"]["format"]["schema"]
    assert "unklar" in schema["properties"]["label"]["enum"]


def test_llm_refusal_goes_to_human(rules, make_mail):
    client = _FakeClient(_FakeResponse("", stop_reason="refusal"))
    assert LLMClassifier(rules, client=client).classify(make_mail()).label == UNCLEAR
