# A RegEx based router

 **rerouter** routes string commands to annotated functions. 
For example, [github slack client](https://github.com/integrations/slack) supports slash commands like:

```shell
subscribe user/repo +label:"teams/designers" +label:"urgent"
subscribe user/repo commits:myBranch author:"hotfix"
close [issue link]
open [pull request link]
```

Suppose we want to build a router that routes various command to different handlers, we can do:

```python
router = RegExRouter()


@router.route("subscribe <user_repo> [<option(+label|commits|author)>:<value>]+")
def handle_subscribe(rns, *args, **kwargs):
    """Handle commands like:

    subscribe user/repo +label:"teams/designers" +label:"urgent"
    subscribe user/repo commits:myBranch author:"hotfix"    
    """
    pass


@router.route("(close|open) [link:<link_url>]+")
def handle_open_close(rns, *args, **kwargs):
    """Handle commands like:
    
    close [issue link]
    open [pull request link]    
    """
    pass

```

Behind the scene, rerouter translates the routing syntax into a list of regex patterns, aka:

|              |                                                                |
|--------------|----------------------------------------------------------------|
| grammar:     | `(close\|open) [link:<link_url>]+`                             |
| re patterns: | 1. `(close\|open)`; <br/>2. `(link):(^(?P<{link_url}>[^:]+)$)` |

In the callback function, the `rns` is a `RegExRouteMatch` object which has the following properties:
1. `conclusion: bool`: whether the grammar match the command. (for annotation use cases, this is always true)
2. `matches`: a list of RegEx match objects, for example, 
command: `close https://example.com` will be routed to `handle_open_close(...)`and the `matches` will be
   1. <re.Match object, match='close'>
   2. <re.Match object, match='http://example.com''>
3. `grammar`: the grammar which the command matches, in our example, its value is `(close|open) [link:<link_url>]+`

[packaging guide]: https://packaging.python.org
[distribution tutorial]: https://packaging.python.org/tutorials/packaging-projects/
[src]: https://github.com/shijinglu/rerouter
[rst]: http://docutils.sourceforge.net/rst.html
[md]: https://tools.ietf.org/html/rfc7764#section-3.5 "CommonMark variant"
[md use]: https://packaging.python.org/specifications/core-metadata/#description-content-type-optional
