from backend.app.analysis import topics as T


def test_components_are_bounded_and_monotonic():
    assert T.outlier_evidence([]) == 0.0
    a, b = T.outlier_evidence([2.0]), T.outlier_evidence([8.0, 8.0, 8.0])
    assert 0 < a < b <= 1.0
    assert T.outlier_evidence([10_000.0] * 5) == 1.0
    assert T.stickman_fit(1) == 0.0 and T.stickman_fit(5) == 1.0
    assert 0 <= T.gap_score([1000], 0, 100) <= 1
    assert T.gap_score([5000], 0, 1000) > T.gap_score([5000], 3, 1000), "crowded topics score lower"


def test_score_uses_weights():
    comp = {"outlier_evidence": 1.0, "gap": 0.0, "stickman_fit": 0.0, "niche_fit": 0.0}
    assert T.score(comp) == 0.35
    assert T.score(comp, {"outlier_evidence": 1, "gap": 0, "stickman_fit": 0, "niche_fit": 0}) == 1.0


def test_ranking_and_evidence_rows():
    swipe = [{"title": "Your brain thinks future you is a stranger", "multiple": 9.0, "views": 90000},
             {"title": "Future you and saving money", "multiple": 4.0, "views": 40000},
             {"title": "Unrelated cooking video", "multiple": 20.0, "views": 200000}]
    cands = [{"id": "a", "title": "Why your brain treats future you like a stranger", "angle": "present bias",
              "keywords": ["future", "brain", "stranger"], "stickman_fit": 5},
             {"id": "b", "title": "Best pasta sauces", "angle": "cooking", "stickman_fit": 2}]
    ranked = T.score_candidates(cands, swipe, "personal finance psychology future saving")
    assert ranked[0]["id"] == "a" and ranked[0]["rank"] == 1
    assert ranked[0]["evidence"] and all("cooking" not in e["title"].lower() for e in ranked[0]["evidence"])
    assert set(ranked[0]["components"]) == {"outlier_evidence", "gap", "stickman_fit", "niche_fit"}
