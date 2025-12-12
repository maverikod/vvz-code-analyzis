"""
Reporter for the code mapper.

This module contains reporting functionality with SQLite database support.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import yaml
import json
from pathlib import Path
from typing import Dict, List, Any

from .database import CodeDatabase


class CodeReporter:
    """Code reporting functionality with SQLite database."""

    def __init__(self, output_dir: Path, use_sqlite: bool = True):
        """Initialize code reporter."""
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.use_sqlite = use_sqlite

        if use_sqlite:
            db_path = self.output_dir / "code_analysis.db"
            self.db = CodeDatabase(db_path)
        else:
            self.db = None

    def generate_code_map(self, code_map: Dict[str, Any]) -> None:
        """Generate code map (SQLite or YAML)."""
        if self.use_sqlite and self.db:
            # Data is already in database from analyzer
            print(f"INFO:__main__:База данных SQLite сохранена: {self.db.db_path}")
        else:
            # Fallback to YAML
            yaml_file = self.output_dir / "code_map.yaml"
            with open(yaml_file, "w", encoding="utf-8") as f:
                yaml.dump(code_map, f, default_flow_style=False, allow_unicode=True)
            print(f"INFO:__main__:YAML карта кода сохранена в файл: {yaml_file}")

    def generate_issues_report(self, issues: Dict[str, List[Any]]) -> None:
        """Generate issues report (SQLite or YAML)."""
        if self.use_sqlite and self.db:
            # Issues are already in database from analyzer
            print("INFO:__main__:Проблемы сохранены в базу данных SQLite")
        else:
            # Fallback to YAML
            yaml_file = self.output_dir / "code_issues.yaml"
            with open(yaml_file, "w", encoding="utf-8") as f:
                yaml.dump(
                    {"issues": issues}, f, default_flow_style=False, allow_unicode=True
                )
            print(f"INFO:__main__:YAML отчет о проблемах сохранен в файл: {yaml_file}")

    def generate_method_index(self, code_map: Dict[str, Any]) -> None:
        """Generate method index (SQLite or YAML)."""
        if self.use_sqlite and self.db:
            # Method index can be queried from database
            print("INFO:__main__:Индекс методов доступен в базе данных SQLite")
        else:
            # Fallback to YAML
            method_index: Dict[str, List[str]] = {}

            # Index methods by class
            for key, class_info in code_map.get("classes", {}).items():
                class_name = class_info["name"]
                if class_name not in method_index:
                    method_index[class_name] = []

                for method in class_info.get("methods", []):
                    method_index[class_name].append(method)

            yaml_file = self.output_dir / "method_index.yaml"
            with open(yaml_file, "w", encoding="utf-8") as f:
                yaml.dump(method_index, f, default_flow_style=False, allow_unicode=True)
            print(f"INFO:__main__:YAML индекс методов сохранен в файл: {yaml_file}")

    def print_summary(self, issues: Dict[str, List[Any]], max_lines: int) -> None:
        """Print analysis summary."""
        if self.use_sqlite and self.db:
            stats = self.db.get_statistics()
            total_issues = stats.get("total_issues", 0)

            print("Анализ завершен!")
            print(f"База данных SQLite сохранена: {self.db.db_path}")
            print(f"Лимит строк на файл: {max_lines}")
            print(f"Всего найдено проблем: {total_issues}")
            print(f"Файлов проанализировано: {stats.get('total_files', 0)}")
            print(f"Классов: {stats.get('total_classes', 0)}")
            print(f"Функций: {stats.get('total_functions', 0)}")
            print(f"Методов: {stats.get('total_methods', 0)}")

            # Files too large
            files_too_large = self.db.get_issues_by_type("files_too_large")
            if files_too_large:
                print(f"Файлов, превышающих лимит: {len(files_too_large)}")
                for issue in files_too_large:
                    metadata = (
                        json.loads(issue.get("metadata", "{}"))
                        if issue.get("metadata")
                        else {}
                    )
                    file_path = issue.get("file_path", "unknown")
                    lines = metadata.get("lines", 0)
                    exceeds = metadata.get("exceeds_limit", 0)
                    print(f"  - {file_path}: {lines} строк (превышение на {exceeds})")
        else:
            # YAML mode
            total_issues = sum(len(issue_list) for issue_list in issues.values())

            print("Анализ завершен!")
            print(f"Созданы YAML отчеты в каталоге: {self.output_dir}")
            print("- code_map.yaml - карта кода")
            print("- code_issues.yaml - проблемы в коде")
            print("- method_index.yaml - индекс методов")
            print(f"Лимит строк на файл: {max_lines}")
            print(f"Всего найдено проблем: {total_issues}")

            # Files too large
            files_too_large = issues.get("files_too_large", [])
            if files_too_large:
                print(f"Файлов, превышающих лимит: {len(files_too_large)}")
                for file_info in files_too_large:
                    print(
                        f"  - {file_info['file']}: {file_info['lines']} строк "
                        f"(превышение на {file_info['exceeds_limit']})"
                    )

            # Summary
            summary = {
                "any_type_usage": len(issues.get("any_type_usage", [])),
                "classes_without_docstrings": len(
                    issues.get("classes_without_docstrings", [])
                ),
                "files_too_large": len(issues.get("files_too_large", [])),
                "files_without_docstrings": len(
                    issues.get("files_without_docstrings", [])
                ),
                "generic_exception_usage": len(
                    issues.get("generic_exception_usage", [])
                ),
                "imports_in_middle": len(issues.get("imports_in_middle", [])),
                "invalid_imports": len(issues.get("invalid_imports", [])),
                "max_lines_limit": max_lines,
                "methods_with_pass": len(issues.get("methods_with_pass", [])),
                "methods_without_docstrings": len(
                    issues.get("methods_without_docstrings", [])
                ),
                "not_implemented_in_non_abstract": len(
                    issues.get("not_implemented_in_non_abstract", [])
                ),
                "total_issues": total_issues,
            }

            # Save summary to issues file
            issues_with_summary = {"issues": issues, "summary": summary}
            yaml_file = self.output_dir / "code_issues.yaml"
            with open(yaml_file, "w", encoding="utf-8") as f:
                yaml.dump(
                    issues_with_summary, f, default_flow_style=False, allow_unicode=True
                )

    def close(self) -> None:
        """Close database connection if using SQLite."""
        if self.db:
            self.db.close()
