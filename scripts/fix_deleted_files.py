"""
Script to fix deleted files - unmark files that actually exist.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from code_analysis.core.database import CodeDatabase


def fix_deleted_files(db_path: Path, project_id: str, root_dir: Path, dry_run: bool = False):
    """
    Fix deleted files - unmark files that actually exist.
    
    Args:
        db_path: Path to database file
        project_id: Project ID
        root_dir: Project root directory
        dry_run: If True, only show what would be fixed
    """
    db = CodeDatabase(db_path)
    
    # Get all deleted files
    deleted_files = db.get_deleted_files(project_id)
    print(f"Total deleted files: {len(deleted_files)}")
    
    # Check which files actually exist
    to_restore = []
    to_keep_deleted = []
    
    for f in deleted_files:
        original_path = f.get('original_path')
        current_path = f.get('path', '')
        file_id = f['id']
        
        # Check if original path exists
        if original_path:
            full_path = Path(original_path)
            if full_path.exists() and full_path.is_file():
                to_restore.append({
                    'id': file_id,
                    'current_path': current_path,
                    'original_path': original_path
                })
            else:
                to_keep_deleted.append({
                    'id': file_id,
                    'path': original_path or current_path
                })
        elif current_path.startswith(str(root_dir)):
            # File without original_path but path is in project
            full_path = Path(current_path)
            if full_path.exists() and full_path.is_file():
                to_restore.append({
                    'id': file_id,
                    'current_path': current_path,
                    'original_path': current_path
                })
            else:
                to_keep_deleted.append({
                    'id': file_id,
                    'path': current_path
                })
        else:
            # File is outside project or in version dir - keep as deleted
            to_keep_deleted.append({
                'id': file_id,
                'path': current_path
            })
    
    print(f"\nFiles that exist and will be restored: {len(to_restore)}")
    print(f"Files that are missing and will stay deleted: {len(to_keep_deleted)}")
    
    if dry_run:
        print("\n=== DRY RUN - No changes will be made ===")
        print("\nFirst 10 files to restore:")
        for f in to_restore[:10]:
            print(f"  {f['original_path']}")
        print("\nFirst 10 files to keep deleted:")
        for f in to_keep_deleted[:10]:
            print(f"  {f['path']}")
        return
    
    # Restore files that exist
    restored_count = 0
    with db._lock:
        cursor = db.conn.cursor()
        for f in to_restore:
            try:
                # Directly update database - set deleted=0, clear original_path and version_dir
                cursor.execute(
                    """
                    UPDATE files 
                    SET deleted = 0, 
                        original_path = NULL, 
                        version_dir = NULL, 
                        path = ?,
                        updated_at = julianday('now')
                    WHERE id = ?
                    """,
                    (f['original_path'], f['id']),
                )
                restored_count += 1
            except Exception as e:
                print(f"Error restoring file {f['original_path']}: {e}")
        
        db.conn.commit()
    
    print(f"\n✅ Restored {restored_count} files")
    print(f"✅ Kept {len(to_keep_deleted)} files as deleted")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Fix deleted files - unmark files that actually exist")
    parser.add_argument("--db-path", default="data/code_analysis.db", help="Path to database file")
    parser.add_argument("--project-id", default="cb113801-7887-429d-882f-855096277edd", help="Project ID")
    parser.add_argument("--root-dir", default="/home/vasilyvz/projects/tools/code_analysis", help="Project root directory")
    parser.add_argument("--dry-run", action="store_true", help="Dry run - only show what would be fixed")
    
    args = parser.parse_args()
    
    fix_deleted_files(
        db_path=Path(args.db_path),
        project_id=args.project_id,
        root_dir=Path(args.root_dir),
        dry_run=args.dry_run
    )

