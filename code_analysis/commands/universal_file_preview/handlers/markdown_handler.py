"""MarkdownFileHandler — FileHandler for .md files (C-017 extension).

Builds a section tree from the Markdown AST via markdown-it-py.
Root NodeKind is 'mapping' (document root).
Each heading creates a section Node whose children are nested
sub-sections and scalar blocks for paragraphs, code fences, etc.

node_ref format: dot-separated slug path from root,
e.g. '2.etapy-pajplajjna.2-3-vektorizacija'.
Document root has node_ref ''.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com"""