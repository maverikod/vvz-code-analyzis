"""
CLI interface for code refactoring commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import click
import logging
from pathlib import Path

from ..core.database import CodeDatabase
from ..commands import RefactorCommand

# Use logger from adapter (configured by adapter)
logger = logging.getLogger(__name__)


@click.group()
def refactor() -> None:
    """Code refactoring commands."""
    pass


@refactor.command()
@click.option(
    "--root-dir",
    "-r",
    required=True,
    help="Root directory of the project",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
)
@click.option(
    "--file",
    "-f",
    required=True,
    help="Python file to refactor (relative to root-dir or absolute)",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--config",
    "-c",
    required=True,
    help="JSON configuration file for class splitting",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--db-path",
    "-d",
    help="Path to SQLite database (default: root_dir/code_analysis/code_analysis.db)",
    type=click.Path(path_type=Path),
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be done without making changes",
)
def split_class(
    root_dir: Path, file: Path, config: Path, db_path: Path | None, dry_run: bool
) -> None:
    """
    Split a class into multiple smaller classes.

    Configuration file format (JSON):
    {
        "src_class": "ClassName",
        "dst_classes": {
            "DstClassName1": {
                "props": ["prop1", "prop2"],
                "methods": ["method1", "method2"]
            },
            "DstClassName2": {
                "props": ["prop3"],
                "methods": ["method3"]
            }
        }
    }
    """
    try:
        # Load configuration
        with open(config, "r", encoding="utf-8") as f:
            split_config = json.load(f)

        click.echo(f"📄 File: {file.absolute()}")
        click.echo(f"⚙️  Config: {config.absolute()}")
        click.echo()

        root_dir = root_dir.resolve()
        if not db_path:
            db_path = root_dir / "code_analysis" / "code_analysis.db"

        db = CodeDatabase(db_path)
        try:
            project_id = db.get_or_create_project(str(root_dir), name=root_dir.name)
            refactor_cmd = RefactorCommand(project_id)

            if dry_run:
                click.echo("🔍 Dry run mode - no changes will be made")
                click.echo()
                # Just validate - use direct import for validation
                from ..core.refactorer import ClassSplitter

                splitter = ClassSplitter(file)
                splitter.load_file()
                src_class_name = split_config.get("src_class")
                if not src_class_name:
                    click.echo("❌ Error: Source class name not specified")
                    raise click.Abort()

                src_class = splitter.find_class(src_class_name)
                if not src_class:
                    click.echo(f"❌ Error: Class '{src_class_name}' not found")
                    raise click.Abort()

                is_valid, errors = splitter.validate_split_config(
                    src_class, split_config
                )
                if is_valid:
                    click.echo("✅ Configuration is valid")
                    click.echo("✅ All properties and methods are accounted for")
                else:
                    click.echo("❌ Configuration validation failed:")
                    for error in errors:
                        click.echo(f"   - {error}")
                    raise click.Abort()
            else:
                # Perform split
                result = refactor_cmd.split_class(
                    str(root_dir), str(file), split_config
                )

                if result["success"]:
                    click.echo("✅ Split completed successfully!")
                    click.echo(f"   {result['message']}")
                else:
                    click.echo("❌ Split failed!")
                    click.echo(f"   {result['message']}")
                    raise click.Abort()
        finally:
            db.close()

    except FileNotFoundError as e:
        click.echo(f"❌ File not found: {e}", err=True)
        raise click.Abort()
    except json.JSONDecodeError as e:
        click.echo(f"❌ Invalid JSON in config file: {e}", err=True)
        raise click.Abort()
    except Exception as e:
        logger.error(f"Error during refactoring: {e}")
        click.echo(f"❌ Error: {e}", err=True)
        raise click.Abort()


@refactor.command()
@click.option(
    "--root-dir",
    "-r",
    required=True,
    help="Root directory of the project",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
)
@click.option(
    "--file",
    "-f",
    required=True,
    help="Python file to refactor (relative to root-dir or absolute)",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--config",
    "-c",
    required=True,
    help="JSON configuration file for superclass extraction",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--db-path",
    "-d",
    help="Path to SQLite database (default: root_dir/code_analysis/code_analysis.db)",
    type=click.Path(path_type=Path),
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be done without making changes",
)
def extract_superclass(
    root_dir: Path, file: Path, config: Path, db_path: Path | None, dry_run: bool
) -> None:
    """
    Extract common functionality into base class.

    Configuration file format (JSON):
    {
        "base_class": "BaseClassName",
        "child_classes": ["ChildClass1", "ChildClass2"],
        "abstract_methods": ["method1", "method2"],
        "extract_from": {
            "ChildClass1": {
                "properties": ["prop1"],
                "methods": ["method1"]
            },
            "ChildClass2": {
                "properties": ["prop2"],
                "methods": ["method2"]
            }
        }
    }
    """
    try:
        # Load configuration
        with open(config, "r", encoding="utf-8") as f:
            extract_config = json.load(f)

        click.echo(f"📄 File: {file.absolute()}")
        click.echo(f"⚙️  Config: {config.absolute()}")
        click.echo()

        root_dir = root_dir.resolve()
        if not db_path:
            db_path = root_dir / "code_analysis" / "code_analysis.db"

        db = CodeDatabase(db_path)
        try:
            project_id = db.get_or_create_project(str(root_dir), name=root_dir.name)
            refactor_cmd = RefactorCommand(project_id)

            if dry_run:
                click.echo("🔍 Dry run mode - no changes will be made")
                click.echo()
                # Just validate
                from ..core.refactorer import SuperclassExtractor

                extractor = SuperclassExtractor(file)
                extractor.load_file()

                is_valid, errors = extractor.validate_config(extract_config)
                if not is_valid:
                    click.echo("❌ Configuration validation failed:")
                    for error in errors:
                        click.echo(f"   - {error}")
                    raise click.Abort()

                base_class = extract_config.get("base_class")
                child_classes = extract_config.get("child_classes", [])

                is_safe, conflict_error = (
                    extractor.check_multiple_inheritance_conflicts(
                        child_classes, base_class
                    )
                )
                if not is_safe:
                    click.echo(f"❌ Multiple inheritance conflict: {conflict_error}")
                    raise click.Abort()

                click.echo("✅ Configuration is valid")
                click.echo("✅ No multiple inheritance conflicts detected")
            else:
                # Perform extraction
                result = refactor_cmd.extract_superclass(
                    str(root_dir), str(file), extract_config
                )

                if result["success"]:
                    click.echo("✅ Superclass extraction completed successfully!")
                    click.echo(f"   {result['message']}")
                else:
                    click.echo("❌ Extraction failed!")
                    click.echo(f"   {result['message']}")
                    raise click.Abort()
        finally:
            db.close()

    except FileNotFoundError as e:
        click.echo(f"❌ File not found: {e}", err=True)
        raise click.Abort()
    except json.JSONDecodeError as e:
        click.echo(f"❌ Invalid JSON in config file: {e}", err=True)
        raise click.Abort()
    except Exception as e:
        logger.error(f"Error during extraction: {e}")
        click.echo(f"❌ Error: {e}", err=True)
        raise click.Abort()


@refactor.command()
@click.option(
    "--root-dir",
    "-r",
    required=True,
    help="Root directory of the project",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
)
@click.option(
    "--file",
    "-f",
    required=True,
    help="Python file to refactor (relative to root-dir or absolute)",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--config",
    "-c",
    required=True,
    help="JSON configuration file for class merging",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--db-path",
    "-d",
    help="Path to SQLite database (default: root_dir/code_analysis/code_analysis.db)",
    type=click.Path(path_type=Path),
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be done without making changes",
)
def merge_classes(
    root_dir: Path, file: Path, config: Path, db_path: Path | None, dry_run: bool
) -> None:
    """
    Merge multiple classes into a single base class.

    Configuration file format (JSON):
    {
        "base_class": "MergedClassName",
        "source_classes": ["Class1", "Class2", "Class3"],
        "merge_methods": ["method1", "method2"],  // optional
        "merge_props": ["prop1", "prop2"]  // optional
    }
    """
    try:
        # Load configuration
        with open(config, "r", encoding="utf-8") as f:
            merge_config = json.load(f)

        click.echo(f"📄 File: {file.absolute()}")
        click.echo(f"⚙️  Config: {config.absolute()}")
        click.echo()

        root_dir = root_dir.resolve()
        if not db_path:
            db_path = root_dir / "code_analysis" / "code_analysis.db"

        db = CodeDatabase(db_path)
        try:
            project_id = db.get_or_create_project(str(root_dir), name=root_dir.name)
            refactor_cmd = RefactorCommand(project_id)

            if dry_run:
                click.echo("🔍 Dry run mode - no changes will be made")
                click.echo()
                # Just validate
                from ..core.refactorer import ClassMerger

                merger = ClassMerger(file)
                merger.load_file()

                is_valid, errors = merger.validate_config(merge_config)
                if not is_valid:
                    click.echo("❌ Configuration validation failed:")
                    for error in errors:
                        click.echo(f"   - {error}")
                    raise click.Abort()

                click.echo("✅ Configuration is valid")
                click.echo("✅ All source classes found")
            else:
                # Perform merge
                result = refactor_cmd.merge_classes(
                    str(root_dir), str(file), merge_config
                )

                if result["success"]:
                    click.echo("✅ Class merge completed successfully!")
                    click.echo(f"   {result['message']}")
                else:
                    click.echo("❌ Merge failed!")
                    click.echo(f"   {result['message']}")
                    raise click.Abort()
        finally:
            db.close()

    except FileNotFoundError as e:
        click.echo(f"❌ File not found: {e}", err=True)
        raise click.Abort()
    except json.JSONDecodeError as e:
        click.echo(f"❌ Invalid JSON in config file: {e}", err=True)
        raise click.Abort()
    except Exception as e:
        logger.error(f"Error during merge: {e}")
        click.echo(f"❌ Error: {e}", err=True)
        raise click.Abort()


if __name__ == "__main__":
    refactor()
