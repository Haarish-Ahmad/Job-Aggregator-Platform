import pytest

from scraper.skills import SKILLS, extract_skills


def test_finds_the_technologies_a_requirement_sentence_names():
    text = "Strong knowledge of Python, SQL and cloud platforms such as Azure. Experience with Docker is a plus."
    assert extract_skills(text) == ["python", "sql", "azure", "docker"]


def test_matching_is_case_insensitive_and_each_skill_appears_once():
    assert extract_skills("PYTHON, python and Python") == ["python"]


def test_aliases_map_to_one_name():
    assert extract_skills("One year of programming experience in an object-oriented language") == ["oop"]
    assert extract_skills("Kubernetes (k8s) on Amazon Web Services, Node.js and nodejs, Postgres") == [
        "node.js", "postgresql", "aws", "kubernetes",
    ]


@pytest.mark.parametrize("text, absent", [
    ("We write JavaScript daily", "java"),            # "java" is not inside "javascript"
    ("Good communication, go-getter attitude", "golang"),  # everyday words are not skills
    ("The rest of the team sits in Pune", "rest api"),
    ("Spring semester internship, express delivery", "spring boot"),
    ("Needs a C grade or better", "c++"),
    ("Strong in React and learning", "r"),
    ("Worked at Oracle Corporation", "oracle database"),
])
def test_ordinary_words_and_longer_names_are_not_mistaken_for_skills(text, absent):
    assert absent not in extract_skills(text)


def test_symbol_names_are_matched_whole():
    assert extract_skills("C++/Java and C# on .NET, plus ci/cd") == ["java", "c++", "c#", ".net", "ci/cd"]
    assert extract_skills("javascript only") == ["javascript"]


def test_empty_text_has_no_skills():
    assert extract_skills("") == []
    assert extract_skills("We value teamwork and curiosity.") == []


def test_every_name_is_lower_case_and_fits_the_backend_skill_length():
    for name in SKILLS:
        assert name == name.lower() and len(name) <= 40
