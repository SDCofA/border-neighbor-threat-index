import borderneighboursthreatindex as bnti


def test_main_reports_no_publish_as_failure(monkeypatch):
    class Analyzer:
        def run(self):
            return False

    monkeypatch.setattr(bnti, "BNTIAnalyzer", Analyzer)
    assert bnti.main() == 2


def test_main_reports_success(monkeypatch):
    class Analyzer:
        def run(self):
            return True

    monkeypatch.setattr(bnti, "BNTIAnalyzer", Analyzer)
    assert bnti.main() == 0
