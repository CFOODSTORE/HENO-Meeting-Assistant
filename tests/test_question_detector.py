from heno.question import looks_like_question


def test_detects_question_mark():
    assert looks_like_question("Quel est le calendrier prévu ?")


def test_detects_polite_request():
    assert looks_like_question("Pouvez-vous préciser le budget de cette activité")


def test_ignores_statement():
    assert not looks_like_question("Le rapport sera envoyé demain matin.")
