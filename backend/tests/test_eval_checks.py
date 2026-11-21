"""The tutor reference check: real files and line ranges pass, invented ones are counted."""
from app.services.eval_checks import check_references, find_references, hallucinated_reference_rate


def test_references_in_the_formats_the_tutor_is_asked_to_use(sample_repo):
    reply = "See `app/models.py` lines 1-3 and also app/models.py:2. The class is in app/models.py line 4."
    refs = find_references(reply)
    assert {(r["path"], r["start"], r["end"]) for r in refs} == {("app/models.py", 1, 3), ("app/models.py", 2, 2), ("app/models.py", 4, 4)}


def test_real_file_and_real_lines_are_valid(sample_repo):
    total = len((sample_repo / "app" / "models.py").read_text().splitlines())
    result = check_references(sample_repo, f"The check is in `app/models.py` lines 1-{total}.")
    assert result == {"cited": 1, "valid": 1, "bad": []}


def test_an_invented_file_is_counted(sample_repo):
    result = check_references(sample_repo, "It happens in `app/ghost.py` lines 3-9.")
    assert result["cited"] == 1 and result["valid"] == 0
    assert result["bad"][0]["why"] == "no such file in the repository"


def test_lines_past_the_end_of_a_real_file_are_counted(sample_repo):
    total = len((sample_repo / "app" / "models.py").read_text().splitlines())
    result = check_references(sample_repo, f"Look at app/models.py lines {total + 5}-{total + 9}.")
    assert result["valid"] == 0 and "outside the file" in result["bad"][0]["why"]


def test_a_backwards_or_zero_range_is_invalid(sample_repo):
    assert check_references(sample_repo, "app/models.py lines 4-2")["valid"] == 0
    assert check_references(sample_repo, "app/models.py lines 0-2")["valid"] == 0


def test_a_file_named_without_lines_only_needs_to_exist(sample_repo):
    assert check_references(sample_repo, "Open `app/models.py` first.") == {"cited": 1, "valid": 1, "bad": []}
    assert check_references(sample_repo, "Open `app/nothing.py` first.")["valid"] == 0


def test_a_path_that_climbs_out_of_the_repo_is_never_valid(sample_repo):
    result = check_references(sample_repo, "Read `../../etc/passwd.txt` lines 1-2.")
    assert result["valid"] == 0


def test_no_references_means_nothing_to_check(sample_repo):
    assert check_references(sample_repo, "It validates the name before saving.") == {"cited": 0, "valid": 0, "bad": []}


def test_rate_across_many_replies(sample_repo):
    results = [check_references(sample_repo, "`app/models.py` lines 1-2"), check_references(sample_repo, "`app/ghost.py` lines 1-2 and `app/models.py` lines 1-2")]
    assert hallucinated_reference_rate(results) == round(1 / 3, 3)
    assert hallucinated_reference_rate([check_references(sample_repo, "no refs")]) is None
