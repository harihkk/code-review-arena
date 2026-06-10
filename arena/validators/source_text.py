"""Comment handling so structural validators match code, not prose.

A patch must not satisfy a validator by stating the right words in a comment.
Validators therefore match against comment-stripped source. String literals
are intentionally kept: several fixtures carry their behavior in strings (SQL
text, prompt templates), and the executable tests remain the primary gate.
"""

from __future__ import annotations

import io
import re
import tokenize

_JS_LIKE_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".java")
_JS_COMMENT = re.compile(r"//[^\n]*|/\*.*?\*/", re.DOTALL)
_SQL_COMMENT = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)
_PY_COMMENT_FALLBACK = re.compile(r"(?m)#.*$")


def _strip_python_comments(text: str) -> str:
    try:
        tokens = [
            token
            for token in tokenize.generate_tokens(io.StringIO(text).readline)
            if token.type != tokenize.COMMENT
        ]
        return tokenize.untokenize(tokens)
    except (tokenize.TokenError, SyntaxError, IndentationError, ValueError):
        return _PY_COMMENT_FALLBACK.sub("", text)


def stripped_source(path: str, text: str) -> str:
    """Return source with comments removed, by file type."""
    if path.endswith(".py"):
        return _strip_python_comments(text)
    if path.endswith(_JS_LIKE_SUFFIXES):
        return _JS_COMMENT.sub("", text)
    if path.endswith(".sql"):
        return _SQL_COMMENT.sub("", text)
    return text


def extract_comments(path: str, text: str) -> list[str]:
    """Return the comment text of a source file, for contamination scanning."""
    if path.endswith(".py"):
        try:
            return [
                token.string
                for token in tokenize.generate_tokens(io.StringIO(text).readline)
                if token.type == tokenize.COMMENT
            ]
        except (tokenize.TokenError, SyntaxError, IndentationError, ValueError):
            return _PY_COMMENT_FALLBACK.findall(text)
    if path.endswith(_JS_LIKE_SUFFIXES):
        return _JS_COMMENT.findall(text)
    if path.endswith(".sql"):
        return _SQL_COMMENT.findall(text)
    return []
