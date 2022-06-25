#  Copyright (c) 2021 Two Sigma Investments, LP.
#  All Rights Reserved
#
#  THIS IS UNPUBLISHED PROPRIETARY SOURCE CODE OF
#  Two Sigma Investments, LP.
#
#  The copyright notice above does not evidence any
#  actual or intended publication of such source code.

import unittest
from typing import List, Tuple, Dict
import re

from rerouter import (
    RegExRouter,
    RegExRoute,
    RegExRoutePattern,
    RegExParseError,
)

router = RegExRouter()


@router.route("settings (set|get|delete) jira.project:<jira_project>")
def f_settings(rns, *args, **kwargs):
    return "f_settings", rns


@router.route("<rid> create-jira [<option(summary|project)>:<value>]+")
def f_create_jira(rns, *args, **kwargs):
    return "f_create_jira", rns


@router.route("jira <jira_id> set <option>:<value>")
def f_jira_set(rns, *args, **kwargs):
    return "f_jira_set", rns


@router.route("list [<options(author|statusCode)>:<value>]*")
def f_list(rns):
    return "f_list", rns


@router.routex(
    ("(subscribe)", ""),
    ("(?P<feature>reviews|pushes|checks)", ""),
    (
        "(?P<filter_name>[+-]path|[+-]fork|[+-]branch|[+-]reviewer):(?P<filter_value>[^:]+)",  # noqa
        "+",
    ),
)
def f_subscribe(rns):
    return "f_subscribe", rns


@router.route("unsubscribe <feature> [<filter_name>:<filter_value>]+")
def f_unsubscribe(rns):
    return "f_unsubscribe", rns


class TestRouter(unittest.TestCase):
    def batch_test(self, test_data: List[Tuple[str, str, bool, List, Dict]]):
        for row in test_data:
            cmd, f_expected, has_exc, poses, named = row
            try:
                f, m = router.route_to(cmd)
                self.assertEqual(f_expected, f)
                for idx, px in poses:
                    self.assertEqual(px, m.positional(idx))
                for k in named.keys():
                    self.assertEqual(named[k], m.named(k))
            except RegExParseError:
                self.assertTrue(has_exc, f"{cmd} should fail")

    def test_router(self):
        f, m = router.route_to(
            "unsubscribe reviews +path:ts/sdlc/* -fork:main/sdlc +path:ts/vats/*"  # noqa
        )
        print(f, m)
        expect_parse_error, expect_no_parse_error = True, False
        self.batch_test(
            [
                # subscribe <feature> [<option>:<value>]+
                (
                    "subscribe reviews +path:ts/sdlc/* -fork:main/sdlc +path:ts/vats/*",  # noqa
                    "f_subscribe",
                    expect_no_parse_error,
                    [
                        (0, "subscribe"),
                        (1, "reviews"),
                        (2, ("+path", "ts/sdlc/*")),
                        (3, ("-fork", "main/sdlc")),
                        (4, ("+path", "ts/vats/*")),
                    ],
                    {
                        "filter_name": ["+path", "-fork", "+path"],
                        "+path": ["ts/sdlc/*", "ts/vats/*"],
                        "-fork": "main/sdlc",
                    },
                ),
                # settings (set|get|delete) jira.project:<jira_project>
                (
                    "settings set jira.project:TEST-PROJ",
                    "f_settings",
                    expect_no_parse_error,
                    [(1, "set")],
                    {"jira_project": "TEST-PROJ"},
                ),
                ("settings help jira.project:TEST-PROJ", "", True, [], {}),
                # <rid> create-jira [<option(summary|project)>:<value>]+
                (
                    '123 create-jira summary:"jira title" project:NOWHERE',
                    "f_create_jira",
                    expect_no_parse_error,
                    [(0, "123"), (1, "create-jira")],
                    {
                        "option": ["summary", "project"],
                        "value": ["jira title", "NOWHERE"],
                        "summary": "jira title",
                        "project": "NOWHERE",
                    },
                ),
                (
                    "123 create-jira not-a-name:not-a-value",
                    "f_create_jira",
                    expect_parse_error,
                    [],
                    {},
                ),
                # jira <jira_id> set <option>:<value>
                (
                    "jira none-123 set jira.board:tools",
                    "f_jira_set",
                    expect_no_parse_error,
                    [(0, "jira"), (1, "none-123"), (2, "set")],
                    {"option": "jira.board", "value": "tools"},
                ),
                # list [<options>:<value>]*
                (
                    "list author:abc statusCode:BEACHED statusCode:FAILED statusCode:PAUSED",  # noqa
                    "f_list",
                    expect_no_parse_error,
                    [],
                    {
                        "options": [
                            "author",
                            "statusCode",
                            "statusCode",
                            "statusCode",
                        ],
                        "author": "abc",
                        "statusCode": ["BEACHED", "FAILED", "PAUSED"],
                    },
                ),
            ]
        )

    def _test_regex_route(self, p: str, s: str, match: bool):
        route = RegExRoute(
            patterns=[
                RegExRoutePattern(
                    re.compile(f"^{x[0]}$"),
                    x[1] if len(x) == 2 else "",
                )
                for x in p.split()
            ]
        )
        self.assertEqual(
            match,
            route.match(" ".join(s)).conclusion,
            f"pattern: '{p}', string: '{s}', expect: {match}",
        )

    def test_regex_route_batch(self):
        match, not_match = True, False
        self._test_regex_route("a?", "", match)
        test_data = [
            ("a", "", not_match),
            ("a", "a", match),
            ("a", "b", not_match),
            ("a", "aa", not_match),
            ("a", "ab", not_match),
            ("a*", "", match),
            ("a*", "a", match),
            ("a*", "b", not_match),
            ("a*", "aa", match),
            ("a*", "ab", not_match),
            ("a*", "aaa", match),
            ("a*", "aab", not_match),
            ("a?", "", match),
            ("a?", "a", match),
            ("a?", "b", not_match),
            ("a?", "aa", not_match),
            ("a?", "ab", not_match),
            ("a?", "aaa", not_match),
            ("a?", "aab", not_match),
            ("a+", "", not_match),
            ("a+", "a", match),
            ("a+", "b", not_match),
            ("a+", "aa", match),
            ("a+", "ab", not_match),
            ("a+", "aaa", match),
            ("a+", "aab", not_match),
            ("a b", "", not_match),
            ("a b", "a", not_match),
            ("a b", "b", not_match),
            ("a b", "aa", not_match),
            ("a b", "ab", match),
            ("a b", "aaa", not_match),
            ("a b", "aab", not_match),
            ("a* b", "", not_match),
            ("a* b", "a", not_match),
            ("a* b", "b", match),
            ("a* b", "aa", not_match),
            ("a* b", "ab", match),
            ("a* b", "aaa", not_match),
            ("a* b", "aab", match),
            ("a? b", "", not_match),
            ("a? b", "a", not_match),
            ("a? b", "b", match),
            ("a? b", "aa", not_match),
            ("a? b", "ab", match),
            ("a? b", "aaa", not_match),
            ("a? b", "aab", not_match),
            ("a+ b", "", not_match),
            ("a+ b", "a", not_match),
            ("a+ b", "b", not_match),
            ("a+ b", "aa", not_match),
            ("a+ b", "ab", match),
            ("a+ b", "aaa", not_match),
            ("a+ b", "aab", match),
            ("a* c* b", "aab", match),
            ("a* c* b", "acb", match),
        ]
        for p, s, m in test_data:
            self._test_regex_route(p, s, m)
