# Paginated Search and Universal Tree Query Source Specification

## 1. Purpose and Scope

This plan defines changes to project search so that indexed search, direct file search, structural XPath-like filtering, paginated result storage, and preview integration use one consistent model.

The same search paging mechanism must support full-text search, semantic search, direct grep/text search, structural grep, project cross-search, and future XPath-like tree search.

## 2. Indexed and Dynamic Search Sources

The search system must support two paths for forming the initial result set. The first path uses the database/index when a file is already indexed and has not changed since indexing. The second path uses direct processing of project files when a file is missing from the database, stale in the database, newer on disk than in the index, or when the database/index is unavailable.

Before executing a search, the system must build the list of files known to the database and the list of files present on disk. The intersection of those lists, after freshness validation, is the set of files that can be processed through the database/index. The difference between the disk file list and the fresh indexed set is the dynamic file set that must be processed directly from disk or from a draft session.

Freshness validation must use checksums and/or modification metadata. If a file is present in the database but its indexed checksum or modification state does not match the current file, that file must be removed from the indexed set and processed dynamically.

Files processed through the database must not be rescanned directly when their indexed state is current. Direct scanning exists to cover missing, stale, unindexed, draft, or unavailable-index cases. This prevents grep/direct search from duplicating full-text database search for unchanged indexed files.

## 3. Search Job Paging Model

Search result generation must not return one large unbounded response. Results must be written into page files in a job result directory associated with a search job identifier (job_id). The `search_start` command blocks until the first two page files are written to disk, then returns the job_id and a URL reference to page 1.

Each page file is a JSON object containing a bounded list of result records, a `next` field, and a `done` field. The `next` field holds the URL of the next page when that page has been written to disk, or null when the next page is not yet available. The `done` field is false for all intermediate pages and must be true only on the last page of a completed or terminated job. When a new page N is written to disk, page N-1 must be updated to set its `next` field to the URL of page N. Both the initial page write and the subsequent `next` field update must be performed atomically using a temporary file and rename.

After `search_start` returns, remaining result generation continues in the background. The client follows the `next` chain to retrieve subsequent pages. When the client reaches a page where `next` is null and `done` is false, the job is still running and that page is the last written page so far; the client must poll by re-requesting the same page URL until `next` becomes non-null or `done` becomes true.

Tree-query results must participate in the same paging mechanism as other search sources. XPath-like search over a large set of files may produce early pages while the remaining tree validation and node filtering continue in the background.

## 4. Search Response Lifetime and Configuration

Each temporary response directory must contain a service metadata file recording the last access time. Reading any page, status, or manifest for that search must update this last access time.

The system configuration must include a search response TTL setting that controls how long temporary response directories live after last access. A code constant must provide the default TTL value. The configuration generator must include this setting, and the configuration validator must reject missing, invalid, non-integer, zero, negative, or out-of-range TTL values according to the declared policy.

## 5. Universal Tree Representation

File formats are divided into tree formats and text formats. Tree formats include JSON, YAML, Python CST, Markdown structure, and any other format represented as a tree. Text files must also be represented uniformly as trees: a text file is a set of paragraphs, and each paragraph is a set of lines.

For every supported file, the system must create and maintain a tree file or tree sidecar that contains stable node identifiers comparable to the stable identifiers used by Python CST sidecars. The tree representation must be available for JSON, YAML, Python CST, Markdown, and text files.

Before any structural processing, the system must check whether the file tree exists and whether it is valid for the current file content. Tree validity must be checked using checksums, following the same principle used by CST sidecar validation. If the tree file does not exist or is not valid, it must be recreated before structural analysis proceeds.

The system must preserve stable node identity across indexer, database-backed search, dynamic search, and preview. If stable node identity cannot be guaranteed for a result, that result must not expose an unstable node identifier as preview-compatible.

## 6. XPath-like Filtering Across Sources

XPath-like analysis must operate on the validated tree representation, not on ad-hoc text. After the tree is validated or recreated, the XPath-like engine filters the list of tree nodes and returns only matching nodes.

XPath-like filtering is a universal structural filter, not a separate implementation per source. The same code must work with different sources: indexed database structural data, in-memory structures created by the indexer, dynamically created trees for files not yet processed by the indexer, and draft-session content.

For files that are already in the database and still current, XPath-like filtering must be applied to the database-backed structural representation. For files that are stale or absent from the database, the same filtering code must be applied to the dynamically created tree. For files currently being processed by the indexer, the same filtering code must be usable with the indexer's in-memory structure before vectorization or database persistence.

The indexer must use the same tree construction and XPath-like filtering code as runtime search. The source of the tree may differ, but the structure model, node identifiers, and selector semantics must remain consistent.

Dynamic file processing must use the same tree construction path as the indexer, excluding vectorization. Vectorization is a separate downstream phase and must not be required for tree creation, XPath filtering, direct dynamic search, or preview generation.

## 7. Preview-Compatible Result Nodes

Each node returned by XPath-like filtering must be representable through universal_file_preview. A result node must include enough information to call universal_file_preview with the relevant file path and node identifier or selector. For draft-session results, the preview reference must also include the session identifier.

The universal_file_preview command is the canonical presentation mechanism for search result nodes. Search results should not invent a separate display model for nodes. They must return preview-compatible references and allow the client to inspect the node through universal_file_preview.

Structural grep and XPath-like search must share the same tree model. Text grep may still exist as a standalone line search mode, but when grep participates in project cross-search as structural evidence, it must return nodes or blocks from the validated tree representation.

## 8. Dynamic Scanning Policy

By default, direct dynamic processing must scan only known supported formats. Broad CLI-like scanning of arbitrary files must be opt-in and must not include logs, virtual environments, build directories, or binary-like files unless explicitly allowed by policy.

fs_grep must support two explicit operating modes. The first mode is classic line grep, which returns line-oriented text matches and is suitable for direct standalone inspection. The second mode uses universal_file_preview-compatible structural representation: it validates or creates the file tree, maps matches to tree nodes or blocks, and returns preview-compatible node references or selectors. The preview-compatible structural mode must be the default mode. Classic line grep must be opt-in and must not be used as structural evidence inside project cross-search unless its results are converted to validated preview-compatible nodes.

## 9. Search Status, Timeout, and Cancellation

Search status must expose whether generation is running, completed, failed, cancelled, or timed out. It must also expose the current phase, such as indexed search, dynamic file discovery, tree validation, tree reconstruction, XPath filtering, page writing, or completion.

Hard timeout and cancellation rules must apply to dynamic scanning, tree reconstruction, XPath filtering, structural enrichment, and page generation. A timed-out dynamic or structural phase must not contribute partial invalid structural evidence.


## 10. Session Manifest, Process Identity, and Cleanup

## 10. Job Directory, Process Identity, and Cleanup

When a model or client starts a search, the server must immediately create a dedicated job result directory before search execution begins. The directory stores the job manifest, page files, and service metadata for that search job.
Search session manifest data must include progress metrics derived from the running search context, such as produced result count, written page count, scanned file count, warning count, and error count.

Job manifest data must include progress metrics derived from the running search context, such as produced result count, written page count, scanned file count, warning count, and error count.

Search result records are written progressively into page files by the running search process. Clients retrieve ready pages through ordinary HTTP requests to the job result endpoint; the implementation must not require streaming transport for normal result inspection.

Every successful HTTP access to a job page, status, or manifest must refresh the job last-access timestamp. This timestamp controls inactivity-based TTL cleanup and is separate from the writer heartbeat timestamp.

The session manifest must include the identity of the main server process that owns the session. At minimum this identity includes main_pid and process_start_time; host and instance_id may also be stored when available. If the main_pid no longer exists, or if the process_start_time does not match because the PID was reused, the session is dead or orphaned.

The job manifest must include the identity of the main server process that owns the job. At minimum this identity includes main_pid and process_start_time; host and instance_id may also be stored when available. If the main_pid no longer exists, or if the process_start_time does not match because the PID was reused, the job is dead or orphaned.

A running search must update a heartbeat timestamp in the job manifest. A running job whose heartbeat is older than the hard timeout must be treated as timed out or orphaned even if its last-access timestamp was recently refreshed.

A background job cleaner must periodically inspect job result directories and remove jobs that are expired, closed, completed beyond TTL, failed beyond TTL, cancelled beyond TTL, timed out beyond policy, or dead/orphaned by process identity and heartbeat checks. The cleaner must not delete a live running job whose process identity and heartbeat are valid.

The plan must extend existing working search behavior instead of replacing it.

Current behavior remains the default for existing callers.

Paginated job-backed behavior is opt-in or exposed through compatible bridge commands.

Migration must preserve current validation, schemas, queue behavior, timeouts, direct payloads, structural results, and preview references.

The implementation plan must mark each behavior as existing or new and must avoid duplicating working search logic.
