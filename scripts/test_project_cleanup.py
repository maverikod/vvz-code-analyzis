#!/usr/bin/env python3
"""
Test script for project cleanup functionality.

Tests that when a project is deleted, all related data is removed from the database.
"""

import asyncio
import os
import sys
import tempfile
import shutil
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from code_analysis.api import CodeAnalysisAPI
from code_analysis.core import CodeDatabase


async def test_project_cleanup():
    """Test that project deletion removes all data."""
    print("=" * 70)
    print("Testing Project Cleanup Functionality")
    print("=" * 70)
    
    # Create temporary directory for test
    test_dir = tempfile.mkdtemp(prefix="test_project_cleanup_")
    print(f"\n1. Created test directory: {test_dir}")
    
    try:
        # Create test files
        test_files = {
            "module1.py": '''"""Module 1 for testing."""

class TestClass1:
    """Test class 1."""
    
    def method1(self):
        """Method 1."""
        return "test1"
    
    def method2(self):
        """Method 2."""
        return "test2"


def function1():
    """Function 1."""
    return "func1"
''',
            "module2.py": '''"""Module 2 for testing."""

from module1 import TestClass1, function1

class TestClass2:
    """Test class 2."""
    
    def __init__(self):
        self.obj = TestClass1()
    
    def method3(self):
        """Method 3."""
        result = function1()
        return result


def function2():
    """Function 2."""
    return "func2"
''',
            "module3.py": '''"""Module 3 for testing."""

class TestClass3:
    """Test class 3."""
    
    def method4(self):
        """Method 4."""
        pass


def function3():
    """Function 3."""
    return "func3"
''',
        }
        
        for filename, content in test_files.items():
            file_path = Path(test_dir) / filename
            file_path.write_text(content)
        
        print(f"2. Created {len(test_files)} test files")
        
        # Analyze project
        print("\n3. Analyzing project...")
        api = CodeAnalysisAPI(test_dir, max_lines=400)
        try:
            result = await api.analyze_project(force=False)
            project_id = result.get("project_id")
            
            print(f"   Project ID: {project_id}")
            print(f"   Files analyzed: {result.get('files_analyzed', 0)}")
            print(f"   Classes: {result.get('classes', 0)}")
            print(f"   Functions: {result.get('functions', 0)}")
            print(f"   Issues: {result.get('issues', 0)}")
            
            # Verify data exists in database
            print("\n4. Verifying data in database...")
            db = CodeDatabase(api.db_path)
            
            files = db.get_project_files(project_id)
            print(f"   Files in database: {len(files)}")
            
            cursor = db.conn.cursor()
            
            # Check classes
            cursor.execute("""
                SELECT COUNT(*) FROM classes c 
                JOIN files f ON c.file_id = f.id 
                WHERE f.project_id = ?
            """, (project_id,))
            class_count = cursor.fetchone()[0]
            print(f"   Classes in database: {class_count}")
            
            # Check methods
            cursor.execute("""
                SELECT COUNT(*) FROM methods m 
                JOIN classes c ON m.class_id = c.id 
                JOIN files f ON c.file_id = f.id 
                WHERE f.project_id = ?
            """, (project_id,))
            method_count = cursor.fetchone()[0]
            print(f"   Methods in database: {method_count}")
            
            # Check functions
            cursor.execute("""
                SELECT COUNT(*) FROM functions fn 
                JOIN files f ON fn.file_id = f.id 
                WHERE f.project_id = ?
            """, (project_id,))
            func_count = cursor.fetchone()[0]
            print(f"   Functions in database: {func_count}")
            
            # Check AST trees
            cursor.execute("""
                SELECT COUNT(*) FROM ast_trees a 
                JOIN files f ON a.file_id = f.id 
                WHERE f.project_id = ?
            """, (project_id,))
            ast_count = cursor.fetchone()[0]
            print(f"   AST trees in database: {ast_count}")
            
            # Check issues
            cursor.execute("""
                SELECT COUNT(*) FROM issues i 
                WHERE i.project_id = ?
            """, (project_id,))
            issue_count = cursor.fetchone()[0]
            print(f"   Issues in database: {issue_count}")
            
            # Check dependencies
            cursor.execute("""
                SELECT COUNT(*) FROM dependencies d 
                JOIN files f1 ON d.source_file_id = f1.id 
                WHERE f1.project_id = ?
            """, (project_id,))
            dep_count = cursor.fetchone()[0]
            print(f"   Dependencies in database: {dep_count}")
            
            # Check vector index
            cursor.execute("""
                SELECT COUNT(*) FROM vector_index 
                WHERE project_id = ?
            """, (project_id,))
            vector_count = cursor.fetchone()[0]
            print(f"   Vector index entries: {vector_count}")
            
            # Verify project exists
            project = db.get_project(project_id)
            if project:
                print(f"   Project record exists: {project['name']}")
            else:
                print("   ERROR: Project record not found!")
                return False
            
            # Delete project
            print("\n5. Deleting project and all related data...")
            await db.clear_project_data(project_id)
            
            # Verify all data is deleted
            print("\n6. Verifying all data is deleted...")
            
            # Check project
            project_after = db.get_project(project_id)
            if project_after:
                print(f"   ERROR: Project record still exists!")
                return False
            else:
                print("   ✓ Project record deleted")
            
            # Check files
            files_after = db.get_project_files(project_id)
            if len(files_after) > 0:
                print(f"   ERROR: {len(files_after)} files still in database!")
                return False
            else:
                print("   ✓ All files deleted")
            
            # Check classes
            cursor.execute("""
                SELECT COUNT(*) FROM classes c 
                JOIN files f ON c.file_id = f.id 
                WHERE f.project_id = ?
            """, (project_id,))
            class_count_after = cursor.fetchone()[0]
            if class_count_after > 0:
                print(f"   ERROR: {class_count_after} classes still in database!")
                return False
            else:
                print("   ✓ All classes deleted")
            
            # Check methods
            cursor.execute("""
                SELECT COUNT(*) FROM methods m 
                JOIN classes c ON m.class_id = c.id 
                JOIN files f ON c.file_id = f.id 
                WHERE f.project_id = ?
            """, (project_id,))
            method_count_after = cursor.fetchone()[0]
            if method_count_after > 0:
                print(f"   ERROR: {method_count_after} methods still in database!")
                return False
            else:
                print("   ✓ All methods deleted")
            
            # Check functions
            cursor.execute("""
                SELECT COUNT(*) FROM functions fn 
                JOIN files f ON fn.file_id = f.id 
                WHERE f.project_id = ?
            """, (project_id,))
            func_count_after = cursor.fetchone()[0]
            if func_count_after > 0:
                print(f"   ERROR: {func_count_after} functions still in database!")
                return False
            else:
                print("   ✓ All functions deleted")
            
            # Check AST trees
            cursor.execute("""
                SELECT COUNT(*) FROM ast_trees a 
                JOIN files f ON a.file_id = f.id 
                WHERE f.project_id = ?
            """, (project_id,))
            ast_count_after = cursor.fetchone()[0]
            if ast_count_after > 0:
                print(f"   ERROR: {ast_count_after} AST trees still in database!")
                return False
            else:
                print("   ✓ All AST trees deleted")
            
            # Check issues
            cursor.execute("""
                SELECT COUNT(*) FROM issues i 
                WHERE i.project_id = ?
            """, (project_id,))
            issue_count_after = cursor.fetchone()[0]
            if issue_count_after > 0:
                print(f"   ERROR: {issue_count_after} issues still in database!")
                return False
            else:
                print("   ✓ All issues deleted")
            
            # Check dependencies
            cursor.execute("""
                SELECT COUNT(*) FROM dependencies d 
                JOIN files f1 ON d.source_file_id = f1.id 
                WHERE f1.project_id = ?
            """, (project_id,))
            dep_count_after = cursor.fetchone()[0]
            if dep_count_after > 0:
                print(f"   ERROR: {dep_count_after} dependencies still in database!")
                return False
            else:
                print("   ✓ All dependencies deleted")
            
            # Check vector index
            cursor.execute("""
                SELECT COUNT(*) FROM vector_index 
                WHERE project_id = ?
            """, (project_id,))
            vector_count_after = cursor.fetchone()[0]
            if vector_count_after > 0:
                print(f"   ERROR: {vector_count_after} vector index entries still in database!")
                return False
            else:
                print("   ✓ All vector index entries deleted")
            
            # Check if project ID exists anywhere
            cursor.execute("""
                SELECT COUNT(*) FROM projects WHERE id = ?
            """, (project_id,))
            project_exists = cursor.fetchone()[0]
            if project_exists > 0:
                print(f"   ERROR: Project ID still exists in projects table!")
                return False
            else:
                print("   ✓ Project ID completely removed from database")
            
            db.close()
            
            print("\n" + "=" * 70)
            print("✓ ALL TESTS PASSED - Project cleanup works correctly!")
            print("=" * 70)
            return True
            
        finally:
            api.close()
    
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # Cleanup test directory
        if os.path.exists(test_dir):
            print(f"\n7. Cleaning up test directory: {test_dir}")
            shutil.rmtree(test_dir)
            print("   ✓ Test directory removed")


async def test_missing_files_cleanup():
    """Test that missing files are removed during analysis."""
    print("\n" + "=" * 70)
    print("Testing Missing Files Cleanup During Analysis")
    print("=" * 70)
    
    test_dir = tempfile.mkdtemp(prefix="test_missing_files_")
    print(f"\n1. Created test directory: {test_dir}")
    
    try:
        # Create initial files
        files_to_create = {
            "file1.py": "class A: pass",
            "file2.py": "class B: pass",
            "file3.py": "class C: pass",
        }
        
        for filename, content in files_to_create.items():
            (Path(test_dir) / filename).write_text(content)
        
        print(f"2. Created {len(files_to_create)} test files")
        
        # Analyze project
        print("\n3. Initial analysis...")
        api = CodeAnalysisAPI(test_dir, max_lines=400)
        try:
            result = await api.analyze_project(force=False)
            project_id = result.get("project_id")
            print(f"   Files analyzed: {result.get('files_analyzed', 0)}")
            
            # Delete some files
            print("\n4. Deleting file2.py and file3.py...")
            (Path(test_dir) / "file2.py").unlink()
            (Path(test_dir) / "file3.py").unlink()
            
            # Re-analyze - should remove missing files
            print("\n5. Re-analyzing (should remove missing files)...")
            result2 = await api.analyze_project(force=False)
            print(f"   Files analyzed: {result2.get('files_analyzed', 0)}")
            
            # Verify only existing file remains
            db = CodeDatabase(api.db_path)
            files = db.get_project_files(project_id)
            print(f"\n6. Files in database: {len(files)}")
            
            for f in files:
                exists = os.path.exists(f['path'])
                status = "EXISTS" if exists else "MISSING"
                print(f"   - {f['path']} [{status}]")
            
            if len(files) == 1 and files[0]['path'].endswith('file1.py'):
                print("\n✓ Missing files were correctly removed!")
                return True
            else:
                print("\n❌ ERROR: Missing files were not removed correctly!")
                return False
            
        finally:
            api.close()
    
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)


async def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("PROJECT CLEANUP TEST SUITE")
    print("=" * 70)
    
    test1_passed = await test_project_cleanup()
    test2_passed = await test_missing_files_cleanup()
    
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Test 1 (Project deletion): {'PASSED' if test1_passed else 'FAILED'}")
    print(f"Test 2 (Missing files cleanup): {'PASSED' if test2_passed else 'FAILED'}")
    print("=" * 70)
    
    if test1_passed and test2_passed:
        print("\n✓ ALL TESTS PASSED!")
        return 0
    else:
        print("\n❌ SOME TESTS FAILED!")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

