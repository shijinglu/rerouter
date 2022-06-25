import asyncio
import inspect
import re
import shlex

from typing import (
    Union,
    Callable,
    Any,
    List,
    Pattern,
    Optional,
    Tuple,
    Match,
    AnyStr,
    Set,
)


class RegExRouteError(RuntimeError):
    """Error in setting up the router."""

    pass


class RegExParseError(RuntimeError):
    """Error in parsing commands"""

    pass


class RegExRouteMatch:
    """Keeping route matching data."""

    __slots__ = "grammar", "target", "conclusion", "matches"

    def __init__(
        self,
        conclusion: bool,
        matches: List[Optional[Match]],
        grammar: str,
        target: Any = None,
    ):
        self.conclusion = conclusion
        self.matches = matches
        self.grammar = grammar
        self.target = target

    def __bool__(self):
        return self.conclusion

    def __repr__(self):
        return (
            f"<Match:{self.grammar} --> {self.target}>"
            if self.conclusion
            else "No match"
        )

    def positional_x(self, i: int) -> Optional[Match]:
        """Get the regex match object that matched argument at position i"""
        if not (0 <= i < len(self.matches)):
            raise IndexError(
                f"Out of boundary, 0<=idx<{len(self.matches)} is required."
            )
        return self.matches[i]

    def positional(self, idx: int) -> Union[None, str, Tuple[str]]:
        """
         Get matched positional arguments.

        For example, given grammar: '<sb> [<verb>:<sub>]+' and sentence "alice play:chess go:shopping"
        The matching result will return following positional arguments:
        - positional(0) -> 'alice'
        - positional(1) -> ('play', 'chess')
        - positional(2) -> ('go', 'shopping')

        :param idx: which position to look at
        :return:
        """
        m = self.positional_x(idx)
        # for optional arguments, match can be empty
        if not m:
            return None
        if len(m.groups()) == 1:
            return m.group(1)
        return m.groups()  # noqa

    def named(
        self, name: str, flat: bool = True, null_error: bool = False
    ) -> Union[None, str, List[str]]:
        """
        Get matched named arguments.

        For example, given grammar: '[<verb>:<sub>]+' and sentence "play:chess go:shopping"
        The matching result will return following named arguments:
        - 'verb': ['play', 'go']
        - 'sub': ['chess', 'shopping']
        - 'play': 'chess'
        - 'go': 'shopping'
        :param name: argument name
        :param flat: if flat the return list, in the above example, the result will be
        'play': ['chess'] if flag is False or 'play': 'chess' otherwise.
        :param null_error: raise KeyError if no matching named argument can be found
        :return:
        """
        opts: List[str] = []
        named_args: List[str] = []
        for m in self.matches:
            if not m:
                continue
            if name in m.groupdict():
                named_args.append(m.group(name))
            if len(m.groups()) == 2 and m.group(1) == name:
                opts.append(m.group(2))
        # option overrides named arguments
        if opts:
            return opts[0] if len(opts) == 1 and flat else opts
        if not named_args and null_error:
            raise KeyError(f"Matching result not found for {name}")
        return named_args[0] if len(named_args) == 1 and flat else named_args

    def names(self) -> Set[str]:
        res: Set[str] = set()
        for m in self.matches:
            if not m:
                continue
            if m.groupdict():
                res.update(m.groupdict().keys())
            if len(m.groups()) == 2:
                res.add(m.group(1))
        return res


class RegExRoutePattern:
    __slots__ = "ext", "pat"

    # match plain text: settings, create-jira, foo.bar, +label
    META_PAT_LITERAL = re.compile(r"^[\w.+-]+$")
    # anonymous filter: (set|get|delete|help)
    META_PAT_FILTER_ANON = re.compile(r"^\([\w|]+\)$")
    # named argument: <rid>
    META_PAT_NAMED_ARG = re.compile(r"^<(\w+)>$")
    # named argument with filter: <verb(set|get|delete|help)>
    META_PAT_NAMED_ARG_FILTER = re.compile(r"^<(\w+)\(([\w|]+)\)>$")
    # optional option: [jira.board:<>] or [<option>:<value>]
    # one or more options: [jira.board:<jira_board>]+ or [<option>:<value>]+
    # zero, one or more options: [jira.board:<jira_board>]* or [<option>:<value>]*
    META_PAT_OPTIONAL_OPT = re.compile(r"^\[([^\[\] ]+)]([*+]?)$")

    """Match a space separated segment"""

    def __init__(self, pat: Pattern, ext: Optional[str]):
        self.pat = pat
        self.ext = ext

    def match(self, arg: str) -> Optional[Match[AnyStr]]:
        return self.pat.match(arg)

    @classmethod
    def from_meta_pattern(cls, rule: str) -> "RegExRoutePattern":
        """
        Get RoutePatten from meta pattens.

        A meta pattern is a pattern of pattern. For example '[<verb(set|get|delete)>]+"
        is a meta pattern, and it can be translated to:
        -> RoutePattern(re.compile(r'(?P<verb>set|get|delete)', '+'))
        """
        # match literal
        m = cls.META_PAT_LITERAL.match(rule)
        if m:
            return RegExRoutePattern(re.compile(f"^({rule})$", re.I), None)
        # anonymous filter: (set|get|delete|help)
        m = cls.META_PAT_FILTER_ANON.match(rule)
        if m:
            return RegExRoutePattern(re.compile(f"^{rule}$", re.I), None)
        # named argument without filter: <rid>
        m = cls.META_PAT_NAMED_ARG.match(rule)
        if m:
            key = m.group(1)
            return RegExRoutePattern(re.compile(f"^(?P<{key}>[^:]+)$", re.I), None)
        # named argument with filter: <verb(set|get|delete|help)>
        m = cls.META_PAT_NAMED_ARG_FILTER.match(rule)
        if m:
            key, f = m.groups()
            return RegExRoutePattern(re.compile(f"^(?P<{key}>{f})$", re.I), None)
        # optional options: [...], [...]*, [...]+
        m = cls.META_PAT_OPTIONAL_OPT.match(rule)
        if m:
            sub_rule, ext = m.groups()
            p_sub = RegExRoutePattern.from_meta_pattern(sub_rule)
            if p_sub.ext:
                raise SyntaxError(
                    f"illegal routing syntax, {rule}:"
                    f" '{p_sub.ext}' is not allowed inside an optional option"
                )
            return RegExRoutePattern(p_sub.pat, ext or "?")
        # colon option like: <option>:<value>, jira.board:<jira_board>
        splits = rule.split(":")
        if len(splits) != 2:
            raise SyntaxError(f"illegal routing syntax: {rule}")
        left, right = splits
        lp = cls.from_meta_pattern(left)
        rp = cls.from_meta_pattern(right)
        if lp.ext or rp.ext:
            raise SyntaxError(
                f"illegal routing syntax: {rule}: nested options are not allowed"
            )
        return RegExRoutePattern(
            re.compile(lp.pat.pattern[:-1] + ":" + rp.pat.pattern[1:], re.I), None
        )


class RegExRoute:
    """Match router grammar to target."""

    __slots__ = "patterns", "target", "grammar"

    def __init__(
        self,
        target: Any = None,
        grammar: str = None,
        patterns: List[RegExRoutePattern] = None,
    ):
        self.target = target
        self.patterns: List[RegExRoutePattern] = []
        if patterns:
            self.patterns = patterns
            self.grammar = " ".join(
                p.pat.pattern + f"/{p.ext}" if p.ext else "" for p in patterns
            )
        elif grammar:
            self.grammar = grammar
            self.patterns = [
                RegExRoutePattern.from_meta_pattern(meta_rule)
                for meta_rule in shlex.split(grammar)
            ]
        else:
            raise RegExRouteError("Cannot build route without any grammar or patterns")

    def match(self, sentence: str) -> RegExRouteMatch:
        splits = shlex.split(sentence)
        ns, np = len(splits), len(self.patterns)
        matches: List[Optional[Match]] = [None] * ns
        dp: List[List[Optional[Match]]] = [[None] * (np + 1) for _ in range(ns + 1)]
        em: Match = re.match("", "")
        dp[0][0] = em
        for pi in range(np):
            dp[0][pi + 1] = (
                em if dp[0][pi] == em and self.patterns[pi].ext in {"?", "*"} else None
            )
        for si in range(ns):
            dp[si + 1][0] = None
            for pi in range(np):
                pat, ext = self.patterns[pi].pat, self.patterns[pi].ext
                m = pat.match(splits[si])
                if m:
                    # diagonal match
                    if dp[si][pi]:
                        matches[si] = m
                        dp[si + 1][pi + 1] = m
                        continue
                    # top down match
                    if dp[si][pi + 1] == em and ext in {"?", "*"}:
                        matches[si] = m
                        dp[si + 1][pi + 1] = m
                        continue
                    # top down match
                    if dp[si][pi + 1] and dp[si][pi + 1] != em and ext in {"*", "+"}:
                        matches[si] = m
                        dp[si + 1][pi + 1] = m
                        continue
                    # left right match, 'b* c*' matches 'c' case
                    if dp[si + 1][pi] == em and ext in {"?", "*"}:
                        matches[si] = m
                        dp[si + 1][pi + 1] = m
                        continue
                else:
                    if dp[si + 1][pi] and ext in {"?", "*"}:
                        if dp[si + 1][pi] != em:
                            matches[si] = dp[si + 1][pi]
                        dp[si + 1][pi + 1] = em
        if dp[-1][-1] is None or any([m is None or m == em for m in matches]):
            return RegExRouteMatch(False, matches, self.grammar, self.target)
        return RegExRouteMatch(True, matches, self.grammar, self.target)


class RegExRouter:
    __slots__ = "routes"

    def __init__(self):
        self.routes: List[RegExRoute] = []

    def route(self, grammar: str) -> Callable:
        """Register a route with grammar, i.e. space separated meta patterns."""

        def decorator(target):
            if not grammar:
                raise RegExRouteError("Grammar is required to build a route")
            self.routes.append(RegExRoute(target, grammar=grammar))
            return target

        return decorator

    def routex(self, *patterns: Tuple[str, str]):
        """Register a route with raw regex pattern and extension."""

        def decorator(target):
            if not patterns:
                raise RegExRouteError("Patterns are required to build a route")
            self.routes.append(
                RegExRoute(
                    target,
                    patterns=[
                        RegExRoutePattern(re.compile(pat), ext) for pat, ext in patterns
                    ],
                )
            )
            return target

        return decorator

    def match(self, cmd: str) -> RegExRouteMatch:
        matched = []
        for r in self.routes:
            m = r.match(cmd)
            # multiple grammars for one handler and more than one matches are found,
            # use the first match
            if m and not any([m.target == x.target for x in matched]):
                matched.append(m)
        if not matched:
            raise RegExParseError(f"No route found for {cmd}")
        if len(matched) > 1:
            raise RegExRouteError(f"Cmd '{cmd}' matches to multiple targets: {matched}")
        return matched[0]

    def route_to(self, cmd: str, *args, **kwargs) -> Any:
        m = self.match(cmd)
        if inspect.iscoroutinefunction(m.target):
            return asyncio.run(m.target(m, *args, **kwargs))
        return m.target(m, *args, **kwargs)
