from paperpilot_ops.classify import UNCLEAR, RuleClassifier


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
