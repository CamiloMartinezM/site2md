"""The rule for which text is a TeX formula, shared by the converter and by extraction."""

from __future__ import annotations

import re

# The rule of pandoc's tex_math_dollars for $…$, plus $$…$$, \(…\) and \[…\]. A delimiter that a backslash
# escapes opens nothing. The bodies of $…$, \(…\) and \[…\] never hold their own delimiters, so a delimiter
# without its partner ends the search at the next one, and a page full of them can't make the search quadratic.
FORMULA = re.compile(
    r"""
    (?<!\\)
    (?:
        \$\$.+?\$\$
      | \\\([^\\]*(?:\\(?![()])[^\\]*)*\\\)
      | \\\[[^\\]*(?:\\(?![\[\]])[^\\]*)*\\\]
      | \$(?![\s$])[^$\\]*(?:\\.[^$\\]*)*(?<!\s)\$(?!\d)
    )
    """,
    re.DOTALL | re.VERBOSE,
)
