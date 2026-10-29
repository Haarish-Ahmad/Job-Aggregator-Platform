from scraper.http import _parse_robots, _path_allowed

MICROSOFT_ROBOTS = "User-agent: *\nDisallow: /\nAllow: /$\nAllow: /careers\nAllow: /api/pcsx\n"


def test_longest_match_wins_even_when_disallow_comes_first():
    rules = _parse_robots(MICROSOFT_ROBOTS)
    assert _path_allowed(rules, "/api/pcsx/search")
    assert _path_allowed(rules, "/careers/job/1")
    assert _path_allowed(rules, "/")
    assert not _path_allowed(rules, "/private/page")


def test_no_rules_means_allowed():
    assert _path_allowed([], "/anything")


def test_wildcards_and_query_strings():
    rules = _parse_robots("User-agent: *\nDisallow: /*?*\nDisallow: /api/\nDisallow: /a/*/private\n")
    assert not _path_allowed(rules, "/internships/?q=1")
    assert not _path_allowed(rules, "/api/x")
    assert not _path_allowed(rules, "/a/1/private")
    assert _path_allowed(rules, "/internships/computer-science-internship/")
    assert _path_allowed(rules, "/a/1/public")
