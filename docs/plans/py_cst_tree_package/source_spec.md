# Source Specification — `py_cst_tree` package

## Purpose

{74yi} The project needs a standalone Python package that represents Python source code as a tree of immutable nodes where every node carries a stable identity that never changes across mutations. The package wraps LibCST: LibCST is used only to parse Python text into a tree and to render a tree back into Python text, while all node identity, persistence, mutation, and query logic belongs to this package.

{aokx} The package must be publishable to PyPI as an independent distribution. It lives in its own subdirectory inside the code analysis server repository, has its own packaging metadata, and declares LibCST as its only runtime dependency. It must not import anything from the code analysis server, so that it can be extracted and released without carrying server code with it.

{71mf} The package exists to solve one concrete failure of the current approach: when a node is moved, replaced, inserted, or deleted, the identity of unrelated nodes must remain intact, and the identity of the affected node and all of its descendants must be preserved when the node merely changes position. The current LibCST-based layer cannot guarantee this because LibCST nodes have no place to store an identity, so identity is reconstructed from line and column positions, which change on every mutation.

## Data model

{cdb1} The tree mirrors the structure of a LibCST tree exactly. Every node in the package corresponds one-to-one to a LibCST node of the same type, with the same fields and the same children in the same order. The package does not invent new node types and does not collapse or split LibCST node types. A round trip from LibCST to the package tree and back to LibCST yields a structurally identical tree.

{704c} Each node carries a stable identity called `stable_id`. The `stable_id` is a value stored as an attribute of the node itself, analogous to an attribute on an XML element, not stored in the rendered Python text and not stored only in an external lookup map. The `stable_id` is assigned once when the node first enters a tree and is never regenerated for that node afterward, regardless of how the tree is mutated.

{b1sc} Identity as a node attribute is realized by representing each package node as a direct subclass of its corresponding LibCST node type, adding a single `stable_id` field while inheriting all original fields and behavior. There is one such subclass per concrete LibCST node type, and the full set of subclasses is generated mechanically rather than hand-written, so that no node type is omitted and the set tracks the LibCST node type list. These subclasses are defined statically in the package source so that they can be serialized and deserialized by reference.

{we5g} The `stable_id` is unique within one tree. Two distinct nodes in the same tree never share a `stable_id`. When a node is duplicated, the copy receives a fresh `stable_id`; the original keeps its own.

{crwt} Every node type receives a `stable_id` without exception. This includes statement-level nodes such as function definitions, class definitions, and conditionals; expression-level nodes such as names, calls, and attributes; structural nodes such as parameters, arguments, and decorators; and formatting and comment nodes. There are no node types that are excluded from carrying identity.

## Tree object and indexes

{s3ig} The tree is a self-contained object that owns the root node together with all machinery required to query it. The object encapsulates the indexes and the lookup operations; callers interact with the object rather than walking raw nodes. The indexes are part of the object's state and travel with it through serialization.

{wk0n} The tree provides a fast lookup from `stable_id` to node. Given a `stable_id`, the corresponding node is retrieved without traversing the whole tree. This lookup is the primary way external code addresses a node for a mutation.

{ln31} The tree maintains additional indexes that map node attributes used by queries — such as node type, node kind, simple name, and qualified name — to the nodes that have them, so that a query selecting nodes by such an attribute resolves against an index rather than by scanning every node. The tree also maintains a parent relation that lets a query move from a node to its parent or ancestors without rescanning the tree.

{k9h7} All indexes are built once when the tree is created or loaded, and after any mutation they are updated to reflect the change so that they remain consistent with the current structure. A query never triggers a full rescan of the tree to answer.

## Query interface

{goki} The package exposes a single query interface over one tree that covers the kinds of in-tree lookups the rest of the project needs: retrieving a node by `stable_id`, selecting nodes by attributes such as type, kind, name, and qualified name, and evaluating path-style selectors that combine an attribute match with structural relations such as child, descendant, and sibling. The selector evaluation resolves its first, broadest step against an index and then narrows through the parent relation, rather than scanning all nodes for every step.

{f6io} The query interface is the intended foundation for the project's existing in-tree search operations. Operations in the project that search within a single file's syntax tree — selecting a node by identity, locating entities by name or type, and evaluating path-style selectors — are expected to become thin wrappers that delegate to this interface. Cross-project search that ranges over many files and relies on the project's database is out of scope for this package and is not delegated to it.

## Conversion to and from LibCST

{ij84} The package converts a LibCST tree into a package tree. Each LibCST node becomes a package node of the corresponding subclass type. During this conversion every package node is assigned a `stable_id`. When the source carries previously persisted identities, those identities are reused; when it does not, fresh identities are generated.

{v1hk} The package converts a package tree back into a LibCST tree. The resulting LibCST tree contains no trace of the `stable_id` attributes; it is a clean LibCST tree that renders to ordinary Python source with no identity markers. The identity attributes are removed during this conversion, not before and not after.

{lm9g} The typical lifecycle is a fixed sequence. Python text is parsed by LibCST into a LibCST tree. The LibCST tree is converted into a package tree, assigning identities. The package tree is written to a file with identities preserved. The package tree is read back from the file with identities intact. The package tree is mutated by insert, replace, delete, and move operations. The mutated package tree is written to a file. The package tree is read back from the file. The identities are stripped and the package tree is converted back into a LibCST tree. LibCST renders the LibCST tree back into Python text.

## Persistence

{m6si} The package writes a tree object to a file in a format that preserves the full node structure, every node's `stable_id`, and the tree's indexes. The written form is the package's own serialization, not Python source code and not a LibCST artifact.

{6par} The package reads a tree object back from its serialized file. The reconstructed tree is identical to the tree that was written: same structure, same node types, same fields, the same `stable_id` on every node, and indexes ready for query without a rebuild pass.

{dmv8} A write followed by a read is lossless with respect to identity and structure. No `stable_id` is lost, altered, or regenerated by a serialization round trip, and the rendered Python source is unchanged.

{1ba4} Serialization is optimized for fast load and save, because the tree object is read from and written to disk repeatedly across a working session and load latency directly affects every operation that begins from a stored tree. The serialized form keeps the indexes so that a loaded tree is immediately queryable.

## Mutation operations

{j8m6} The package provides an insert operation. Insert places a new node, or a subtree, at a specified position relative to a target node or inside a target parent. The inserted nodes receive fresh `stable_id` values. Every node that already existed in the tree keeps its `stable_id` unchanged after the insert.

{z0lu} The package provides a delete operation. Delete removes a target node and its entire subtree from the tree. Every node that remains in the tree keeps its `stable_id` unchanged after the delete. The identities of the removed nodes are gone with them.

{lqg8} The package provides a replace operation. Replace substitutes a target node with a new node or subtree. The new nodes receive fresh `stable_id` values. Every other node in the tree keeps its `stable_id` unchanged after the replace.

{hevj} The package provides a move operation. Move relocates a target node and its entire subtree to a new position relative to another node or inside another parent. The moved node and every descendant of the moved node keep their `stable_id` values unchanged; only their position in the tree changes. Every node that was not part of the moved subtree also keeps its `stable_id` unchanged.

{m5zg} The move operation is the central reason the package exists, and its identity guarantee is the strictest. Moving a subtree must never regenerate the identity of any node inside that subtree, no matter how deeply nested, and no matter what node types the subtree contains.

{8niu} All mutation operations address nodes by `stable_id`. A mutation names the target node, and where applicable the destination parent or sibling node, by their `stable_id` values rather than by position.

{prib} All mutation operations keep the tree's indexes consistent with the mutated structure: after any single operation no index entry points at a removed node and every surviving node is reachable through the indexes that apply to it.

## Constraints

{0268} The package depends on LibCST and on nothing else at runtime. It must not depend on the code analysis server, on its database, or on any of its internal modules.

{ylqj} The package preserves the exact textual fidelity that LibCST guarantees. Whitespace, comments, string quoting, and formatting that survive a LibCST parse-and-render round trip must equally survive a parse, convert, mutate-nothing, convert-back, render round trip through the package.
