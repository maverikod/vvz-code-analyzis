# Vector Commands — Detailed Descriptions

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

**rebuild_faiss:** `commands/vector_commands/rebuild_faiss.py`. **revectorize:** `commands/vector_commands/revectorize.py`. Schema from `get_schema()`; metadata from `metadata()`.

---

## rebuild_faiss — RebuildFaissCommand

**Description:** Rebuild the FAISS index from current vectors in the database.

**Behavior:** Accepts project_id or root_dir; reads all vectorized chunks from DB, builds new FAISS index, and replaces the on-disk index; ensures index and DB are in sync.

---

## revectorize — RevectorizeCommand

**Description:** Recompute embeddings for chunks that are not yet vectorized (or force re-vectorize).

**Behavior:** Finds chunks with null vector_id (or all if forced), computes embeddings via embedding service, updates DB and FAISS index.
