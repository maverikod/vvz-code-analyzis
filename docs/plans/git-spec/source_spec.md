# Source Specification — git / github command blocks + commit-on-write

<!-- non-binding -->

This source specification is the level-1 artifact for the `git-spec` plan. It
describes WHAT the system must be: the concepts and behaviours of three command
blocks added to the Code Analysis Server — project-scoped git commands, GitHub
API commands, and a commit-on-write behaviour on the existing file-write path.
Implementation detail (files, modules, functions) is deliberately absent; it
belongs to levels 3–5. Derived from TZ-CA-GIT-COMMANDS-002.

Each binding paragraph below carries a stable four-character label in curly
braces. Lower levels bind to these labels, never to line numbers.
<!-- /non-binding -->

## 1. Scope and layers

{a1b2} The system adds three independent capability blocks to the server: a
project-scoped git command block operating on a registered project's working
tree, a GitHub command block operating on the GitHub HTTP API, and a
commit-on-write behaviour attached to the existing project file write path.
The three blocks are separable: each can be configured, enabled, and fail
independently of the others.

{c3d4} The git command block operates only on the filesystem working tree of a
registered project via subprocess git. The GitHub command block operates only
on the GitHub remote HTTP API. Neither block touches the server's internal
command-to-driver-to-database chain.

## 2. Locks are opaque to the writer

{e5f6} The server does not interpret why a file is locked. Its responsibility on
a write is to receive the file content and persist it. Whether that write also
produces a commit is determined solely by the parameters of the write call, not
by any lock state or lock semantics.

{g7h8} A file write may occur with or without an accompanying commit, and may
occur with or without releasing a lock. The commit decision and the unlock
decision are independent of each other; neither implies the other.

## 3. Commit-on-write behaviour

{i9j0} A file write carries an explicit commit-intent flag. When the flag is
set, the write produces a commit after the content is persisted, provided the
content actually changed. When the flag is absent or unset, the write never
produces a commit.

{k1l2} When commit-intent is set, a commit message is mandatory. The message
must be a text value and must be non-empty after surrounding whitespace is
removed. A commit-intent write lacking a valid message is rejected before any
content is written, leaving the target file untouched.

{m3n4} A commit message supplied without commit-intent is rejected. The system
provides exactly one path to a commit on write — the explicit commit-intent flag
together with a valid message — and no implicit path exists.

{o5p6} When commit-intent is set with a valid message but the written content is
identical to the previous content, the write succeeds and no commit is produced.
This outcome is not an error; it is reported as a successful write that produced
no commit because nothing changed.

{q7r8} A commit produced by a write never pushes to a remote. Propagation of
commits to a remote is exclusively a manual operation requested separately.

{s9t0} The identity recorded as the author of a commit-on-write commit is taken
from the git configuration of the project, not from the writer or the lock
holder.

## 4. Project-scoped git — read operations

{u1v2} The git block provides read-only inspection of a project's repository:
working-tree status, commit history, differences between revisions or the index,
branch enumeration, single-commit inspection, remote enumeration, and per-line
attribution of a file's contents to commits.

{w3x4} Every git operation resolves the project's repository root before acting,
confirms the root is a git repository, and reports a distinct clear outcome when
git is unavailable or the root is not a repository. Paths exchanged with git
operations are project-relative.

{j3k4} The repository root is never taken as a free absolute path from the caller.
It is always resolved relative to a watched directory: the caller identifies the
project by the pair (watched-directory id, project id), and the root is derived
as the project's folder under that watched directory's absolute path. A bare
absolute root path is accepted only as a legacy form. When resolution yields an
empty or ambiguous root, the operation refuses rather than acting on a guessed
location. The same resolved root governs both git operations and any commit
produced on write.

## 5. Project-scoped git — local mutating operations

{y5z6} The git block provides local mutating operations that do not contact a
remote: staging changes, creating commits, switching and creating and deleting
branches, restoring working-tree or staged files, stashing, resetting,
merging branches, applying individual commits from elsewhere, reverting commits
by creating inverse commits, and managing tags.

{a7b8} A hard reset is destructive and is gated: it requires an explicit
destructive-mode selection together with an explicit confirmation. Absent the
confirmation, the operation only reports what it would change without moving the
repository state.

{c9d0} Merge and individual-commit-application operations are local and are not
subject to the protected-branch restriction. Their only route to a remote is a
separate, separately-restricted push operation.

{e1f2} Reverting a commit produces a new inverse commit rather than rewriting
history, making it safe to apply on branches whose history must be preserved.

## 6. Project-scoped git — remote operations

{g3h4} The git block provides remote operations: fetching, pulling, and pushing.
Remote operations require the git block to be configured for remote access;
when that configuration is absent, remote operations fail fast with a distinct
outcome while local and read operations continue to function.

{i5j6} A pull defaults to a fast-forward-only merge. When a rebase pull is
requested, the fast-forward-only constraint does not also apply; the two
settings are not combined. A pull that cannot complete cleanly leaves the
working tree in a clean state and reports a conflict outcome.

{k7l8} A push to a branch designated as protected is rejected unless the request
carries an explicit protected-branch override and policy permits it. A
force-push is rejected unless force is both permitted by configuration and
explicitly requested. A dry-run push performs no remote write.

## 7. Project-scoped git — authentication

{m9n0} Remote git operations authenticate over SSH using a per-operation SSH
invocation that names exactly one configured private key, pins the set of known
hosts, and enforces strict host-key checking. No global git or SSH configuration
is mutated and no key agent is required.

{o1p2} The private key material lives in a protected secrets location referenced
only by path in configuration; the configuration never stores key bytes. The
key path, the known-hosts path, the commit identity, the set of protected
branches, and the remote permissions are all configuration of the git block.

## 8. GitHub command block

{q3r4} The GitHub block provides repository inspection, pull-request listing and
inspection and creation and merging, issue listing and creation and commenting,
and release creation, all over the GitHub HTTP API. The set is the minimal
sufficient set for an operator's cycle and excludes second-tier capabilities
until a demonstrated need arises.

{s5t6} Merging a pull request is a remote mutation that bypasses the local git
protected-branch restriction. It is therefore independently gated: it requires
an explicit configuration permission, and a merge targeting a protected base
branch is rejected unless an explicit override is present and policy permits it.

{u7v8} The GitHub block authenticates with a personal access token. The token
material lives in a protected secrets location referenced only by path in
configuration; the configuration never stores the token bytes. When the GitHub
block is not configured, its commands fail fast with a distinct outcome.

## 9. Ownership and safety invariants

{w9x0} All git and write operations run as the unprivileged server user, never
as a privileged user, so that every created or updated file and every repository
object retains the server user's ownership without any post-hoc ownership
change.

{y1z2} Every path parameter accepted by any git operation is confined to the
project root: a path that resolves outside the root is rejected. Revision
identifiers, which are not paths, are not subject to path confinement.

{a3b4} Remote git and GitHub operations are bounded by a configured timeout;
exceeding it yields a distinct timeout outcome with no in-operation retry.


{d7e8} A write performed by any command, including a commit produced on write, is
subject to the server's existing write-protection of special locations: writes
under a project's virtual-environment directory or under installed-package
directories are rejected. The git block does not bypass this protection.

{f9g0} The project-scoped git block is distinct from the pre-existing
edit-session git facility, which operates on a temporary per-edit-session
repository identified by an edit session. The new block operates on the
registered project's own working tree. The two are parallel and independent; the
new block neither replaces nor alters the edit-session facility.

{h1i2} Every command in the project-scoped git block is named under a reserved
prefix that keeps it disjoint from the edit-session git commands, so that no name
or routing collision arises between the two facilities.

## 10. Migration

{c5d6} Introducing the explicit commit-intent flag removes a prior implicit
behaviour in which supplying a commit message alone triggered a commit. After
the change, a message without the flag is rejected rather than silently
committing, so any existing caller that relied on the implicit behaviour fails
loudly and must adopt the explicit flag.
