import inspect
import re
from dataclasses import dataclass, field
from typing import Any, Iterator, List, Optional, Tuple

from mkapi.core import annotation

SECTIONS = [
    "Args",
    "Attributes",
    "Example",
    "Examples",
    "Note",
    "Notes",
    "Returns",
    "Raises",
    "References",
    "See Also",
    "Warning",
    "Warnings",
    "Warns",
    "Yield",
    "Yields",
    "Todo",
]


def get_indent(line: str) -> int:
    indent = 0
    for x in line:
        if x != " ":
            return indent
            print(line, indent)
        indent += 1
    return -1


def join(lines):
    indent = get_indent(lines[0])
    return "\n".join(line[indent:] for line in lines)


def split_section(doc: str) -> Iterator[Tuple[str, str]]:
    """Yields section name and its contents."""
    lines = [x.rstrip() for x in doc.split("\n")]
    name = "Default"
    start = indent = 0
    for stop, line in enumerate(lines, 1):
        if stop == len(lines):
            next_indent = -1
        else:
            next_indent = get_indent(lines[stop])
        if not line and next_indent < indent:
            yield name, join(lines[start : stop - 1])
            start = stop
            name = "Default"
        elif line.endswith(":") and line[:-1] in SECTIONS:
            if start < stop - 1:
                yield name, join(lines[start : stop - 1])
            name = line[:-1]
            start = stop
            indent = next_indent
    if start < len(lines):
        yield name, join(lines[start:])


def split_parameter(doc: str) -> Iterator[List[str]]:
    """Yields list of parameter string."""
    lines = [x.rstrip() for x in doc.split("\n")]
    start = stop = 0
    for stop, line in enumerate(lines, 1):
        if stop == len(lines):
            next_indent = 0
        else:
            next_indent = get_indent(lines[stop])
        if next_indent == 0:
            yield lines[start:stop]
            start = stop


def parse_parameter(lines: List[str]) -> Tuple[str, str, str]:
    """Yields (name, type, markdown)."""
    name, line = lines[0].split(":")
    name = name.strip()
    line = line.strip()
    parsed = [line]
    if len(lines) > 1:
        indent = get_indent(lines[1])
        for line in lines[1:]:
            parsed.append(line[indent:])
    m = re.match(r"(.*?)\s*?\((.*?)\)", name)
    if m:
        name, type = m.group(1), m.group(2)
    else:
        type = ""
    return name, type, "\n".join(parsed)


def parse_parameters(doc: str) -> List[Tuple[str, str, str]]:
    """Returns list of (name, type, markdown)."""
    return [parse_parameter(lines) for lines in split_parameter(doc)]


def parse_returns(doc: str) -> Tuple[str, str]:
    """Returns (type, markdown)."""
    lines = doc.split("\n")
    if ":" in lines[0]:
        type, lines[0] = lines[0].split(":")
        type = type.strip()
        lines[0] = lines[0].strip()
    else:
        type = ""
    return type, "\n".join(lines)


def parse_raise(lines: List[str]) -> Tuple[str, str]:
    """Returns (type, markdown)."""
    type, _, markdown = parse_parameter(lines)
    return type, markdown


def parse_raises(doc: str) -> List[Tuple[str, str]]:
    return [parse_raise(lines) for lines in split_parameter(doc)]


@dataclass
class Item:
    name: str
    type: str
    markdown: str
    html: str = ""

    def __post_init__(self):
        self.markdown = self.markdown.strip()


@dataclass
class Section:
    name: str
    items: List[Item]

    def __getitem__(self, index):
        return self.items[index]

    def __len__(self):
        return len(self.items)

    def __getattr__(self, name):
        for item in self.items:
            if item.name == name:
                return item


@dataclass
class Docstring:
    obj: Optional[Any] = field(repr=False)
    sections: List[Section]

    def __getattr__(self, name):
        for section in self.sections:
            if section.name == name:
                return section

    def __getitem__(self, name):
        return getattr(self, name)


def create_section(name: str, doc: str) -> Section:
    if name in ["Args", "Attributes"]:
        items = [Item(n, t, m) for n, t, m in parse_parameters(doc)]
    elif name == "Raises":
        items = [Item("", t, m) for t, m in parse_raises(doc)]
    elif name in ["Returns", "Yields"]:
        items = [Item("", t, m) for t, m in [parse_returns(doc)]]
    else:
        items = [Item("", "", doc)]
    return Section(name.lower(), items)


def postprocess(doc: Docstring, obj: Any):
    if isinstance(obj, property):
        item = doc.sections[0].items[0]
        line = item.markdown.split("\n")[0]
        if ":" in line:
            index = line.index(":")
            item.type = line[:index].strip()
            item.markdown = item.markdown[index + 1 :].strip()

    if not callable(obj):
        return

    annotations = annotation.to_string(obj)
    if doc.args:
        for item in doc.args:
            if item.type == "" and item.name in annotations[0]:
                item.type = annotations[0][item.name]

    for k, section in enumerate(["returns", "yields"], 1):
        if doc[section]:
            item = doc[section].items[0]
            if item.type == "":
                item.type = annotations[k]  # type:ignore


def parse_docstring(obj: Any) -> Docstring:
    doc = inspect.getdoc(obj)
    if not doc:
        return Docstring(obj, [])
    sections = []
    for section in split_section(doc):
        sections.append(create_section(*section))
    docstring = Docstring(obj, sections)
    postprocess(docstring, obj)
    return docstring