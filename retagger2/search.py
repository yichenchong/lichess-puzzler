from typing import List, Union, Tuple

Tag = str


def parse_tags(s: str) -> List[List[Tag]]:
    movetags = s.split("/")
    movetags = [move.split(" ") for move in movetags]
    return movetags


def tag_distance(a: Tag, b: Tag) -> float:
    if a == b:
        return 0
    a = a.split(":")
    b = b.split(":")
    if len(a) == 0 and len(b) == 0:
        return 0
    if len(a) == 0 or len(b) == 0:
        return 1
    if a[0] != b[0]:
        return 1
    return tag_distance(":".join(a[1:]), ":".join(b[1:])) / 2


def taglist_distance(a: List[Tag], b: List[Tag]) -> float:
    if len(a) == 0:
        return len(b)
    if len(b) == 0:
        return len(a)
    return min(
        tag_distance(a[0], b[0]) + taglist_distance(a[1:], b[1:]),
        1 + taglist_distance(a[1:], b),
        1 + taglist_distance(a, b[1:]),
    )


def unordered_distance(a: List[List[Tag]], b: List[List[Tag]]) -> float:
    a = list(set(sorted(sum(a, []))))
    b = list(set(sorted(sum(b, []))))
    return taglist_distance(a, b)


def ordered_distance(a: List[List[Tag]], b: List[List[Tag]]) -> float:
    if len(a) == 0:
        return len(b)
    if len(b) == 0:
        return len(a)
    return min(
        taglist_distance(a[0], b[0]) + ordered_distance(a[1:], b[1:]),
        1 + ordered_distance(a[1:], b),
        1 + ordered_distance(a, b[1:]),
    )


def distance(a: List[List[Tag]], b: List[List[Tag]]) -> float:
    return unordered_distance(a, b) + ordered_distance(a[:-1], b[:-1])

print(distance(parse_tags("a b:s c/d e f"), parse_tags("a b:x c/d e f")))