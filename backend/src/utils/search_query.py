"""Kibana-like query parser for OCR text search.

Supported syntax::

    invoice                      # substring match
    invoice total                # implicit AND
    invoice AND total
    invoice OR receipt
    invoice AND NOT cancelled
    (invoice OR receipt) AND "total amount"
    "annual report"              # exact phrase
    inv*                         # wildcard (* = any chars, ? = one char)

Operators are case-insensitive.  Terms without an explicit operator are
combined with AND, which matches the default behaviour of Kibana's KQL.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class QuerySyntaxError(ValueError):
    """Raised when an OCR query cannot be parsed."""


class _TokenType(Enum):
    WORD = auto()
    PHRASE = auto()
    AND = auto()
    OR = auto()
    NOT = auto()
    LPAREN = auto()
    RPAREN = auto()
    EOF = auto()


@dataclass(frozen=True)
class _Token:
    type: _TokenType
    value: str
    position: int


class _Node:
    pass


@dataclass(frozen=True)
class Term(_Node):
    value: str
    wildcard: bool = False


@dataclass(frozen=True)
class And(_Node):
    left: _Node
    right: _Node


@dataclass(frozen=True)
class Or(_Node):
    left: _Node
    right: _Node


@dataclass(frozen=True)
class Not(_Node):
    operand: _Node


_OPERATORS = {
    "AND": _TokenType.AND,
    "OR": _TokenType.OR,
    "NOT": _TokenType.NOT,
}


def _tokenize(query: str) -> list[_Token]:
    tokens: list[_Token] = []
    i = 0
    length = len(query)

    while i < length:
        char = query[i]

        if char.isspace():
            i += 1
            continue

        if char == "(":
            tokens.append(_Token(_TokenType.LPAREN, char, i))
            i += 1
            continue

        if char == ")":
            tokens.append(_Token(_TokenType.RPAREN, char, i))
            i += 1
            continue

        if char == '"':
            start = i
            i += 1
            chars: list[str] = []
            while i < length and query[i] != '"':
                if query[i] == "\\" and i + 1 < length:
                    i += 1
                chars.append(query[i])
                i += 1
            if i >= length:
                raise QuerySyntaxError(
                    f"Unterminated quoted phrase starting at position {start}"
                )
            i += 1  # closing quote
            tokens.append(_Token(_TokenType.PHRASE, "".join(chars), start))
            continue

        start = i
        while i < length and not query[i].isspace() and query[i] not in ("(", ")", '"'):
            i += 1

        word = query[start:i]
        token_type = _OPERATORS.get(word.upper(), _TokenType.WORD)
        tokens.append(_Token(token_type, word, start))

    tokens.append(_Token(_TokenType.EOF, "", length))
    return tokens


class _Parser:
    def __init__(self, tokens: list[_Token]):
        self._tokens = tokens
        self._index = 0

    @property
    def _current(self) -> _Token:
        return self._tokens[self._index]

    def _advance(self) -> _Token:
        token = self._current
        self._index += 1
        return token

    def parse(self) -> _Node:
        if self._current.type is _TokenType.EOF:
            raise QuerySyntaxError("Query is empty")

        node = self._parse_or()

        if self._current.type is not _TokenType.EOF:
            raise QuerySyntaxError(
                f"Unexpected token {self._current.value!r} "
                f"at position {self._current.position}"
            )
        return node

    def _parse_or(self) -> _Node:
        node = self._parse_and()
        while self._current.type is _TokenType.OR:
            self._advance()
            node = Or(left=node, right=self._parse_and())
        return node

    def _parse_and(self) -> _Node:
        node = self._parse_unary()
        while True:
            token_type = self._current.type
            if token_type is _TokenType.AND:
                self._advance()
                node = And(left=node, right=self._parse_unary())
            elif token_type in (
                _TokenType.WORD,
                _TokenType.PHRASE,
                _TokenType.NOT,
                _TokenType.LPAREN,
            ):
                # Implicit AND: "invoice total" == "invoice AND total".
                node = And(left=node, right=self._parse_unary())
            else:
                return node

    def _parse_unary(self) -> _Node:
        if self._current.type is _TokenType.NOT:
            self._advance()
            return Not(operand=self._parse_unary())
        return self._parse_primary()

    def _parse_primary(self) -> _Node:
        token = self._current

        if token.type is _TokenType.LPAREN:
            self._advance()
            if self._current.type is _TokenType.RPAREN:
                raise QuerySyntaxError(
                    f"Empty parentheses at position {token.position}"
                )
            node = self._parse_or()
            if self._current.type is not _TokenType.RPAREN:
                raise QuerySyntaxError(
                    f"Missing closing parenthesis for '(' at position {token.position}"
                )
            self._advance()
            return node

        if token.type is _TokenType.WORD:
            self._advance()
            return Term(
                value=token.value, wildcard="*" in token.value or "?" in token.value
            )

        if token.type is _TokenType.PHRASE:
            self._advance()
            return Term(value=token.value)

        if token.type is _TokenType.EOF:
            raise QuerySyntaxError("Query ended unexpectedly")

        raise QuerySyntaxError(
            f"Unexpected token {token.value!r} at position {token.position}"
        )


def parse_query(query: str) -> _Node:
    """Parse a query string into an AST."""
    return _Parser(_tokenize(query)).parse()


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _like_pattern(term: Term) -> str:
    escaped = _escape_like(term.value)
    if term.wildcard:
        # Keep SQL wildcards where the user explicitly asked for them.  The
        # pattern is still matched as a substring, like plain terms.
        escaped = escaped.replace("*", "%").replace("?", "_")
    return f"%{escaped}%"


def _compile(node: _Node, column: str) -> tuple[str, list[str]]:
    if isinstance(node, Term):
        return f"{column} ILIKE %s ESCAPE '\\'", [_like_pattern(node)]

    if isinstance(node, And):
        left_sql, left_params = _compile(node.left, column)
        right_sql, right_params = _compile(node.right, column)
        return f"({left_sql} AND {right_sql})", left_params + right_params

    if isinstance(node, Or):
        left_sql, left_params = _compile(node.left, column)
        right_sql, right_params = _compile(node.right, column)
        return f"({left_sql} OR {right_sql})", left_params + right_params

    if isinstance(node, Not):
        operand_sql, operand_params = _compile(node.operand, column)
        return f"(NOT {operand_sql})", operand_params

    raise TypeError(f"Unsupported query node: {type(node)!r}")


def compile_ocr_filter(query: str, column: str = "ocr_text") -> tuple[str, list[str]]:
    """Compile a query to a SQL predicate and its parameters.

    ``column`` must be a trusted identifier (it is interpolated into SQL), while
    all user-provided text is passed as query parameters.
    """
    return _compile(parse_query(query), column)
