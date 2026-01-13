"""
Unified test pipeline for code analysis server.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import time
from pathlib import Path

from tests.pipeline.config import PipelineConfig
from tests.pipeline.reporting import TestReporter
from tests.pipeline.server_manager import ServerManager
from tests.pipeline.test_data_setup import TestDataSetup


class TestPipeline:
    """Unified test pipeline."""

    def __init__(self):
        """Initialize test pipeline."""
        self.config = PipelineConfig()
        self.reporter = TestReporter()
        self.server_manager = ServerManager(self.config)
        self.data_setup = TestDataSetup(self.config)

    def run_pipeline(self) -> None:
        """Run complete test pipeline."""
        self.reporter.start_pipeline()

        try:
            # 1. Setup test data
            self._test_data_setup()

            # 2. Start server
            self._test_server_startup()

            # 3. Test database operations
            self._test_database_operations()

            # 4. Test AST/CST operations
            self._test_ast_cst_operations()

            # 5. Test commands
            self._test_commands()

            # 6. Test workers
            self._test_workers()

            # 7. Test performance
            self._test_performance()

            # 8. Test error scenarios
            self._test_error_scenarios()

            # 9. Test concurrent operations
            self._test_concurrent_operations()

            # 10. Test end-to-end workflows
            self._test_end_to_end_workflows()

        finally:
            # 11. Stop server
            self._stop_server()

            # 12. Generate reports
            report = self.reporter.end_pipeline()
            self.reporter.print_summary(report)
            self.reporter.save_report(report, format="json")
            self.reporter.save_report(report, format="html")

    def _test_data_setup(self) -> None:
        """Test data setup."""
        self.reporter.start_suite("Test Data Setup")

        start_time = time.time()

        # Verify test data is available
        if not self.config.verify_test_data():
            self.reporter.add_test_result(
                "test_data_available",
                "skipped",
                0.0,
                message="test_data directory not found",
            )
            return

        self.reporter.add_test_result(
            "test_data_available",
            "passed",
            time.time() - start_time,
            message="test_data directory found",
        )

        # Setup test database
        start_time = time.time()
        try:
            db = self.data_setup.setup_test_database()
            self.reporter.add_test_result(
                "test_database_setup",
                "passed",
                time.time() - start_time,
                message="Test database created",
            )
        except Exception as e:
            self.reporter.add_test_result(
                "test_database_setup",
                "failed",
                time.time() - start_time,
                error=str(e),
            )
            return

        # Load test projects
        start_time = time.time()
        try:
            projects = self.data_setup.load_test_projects(db)
            self.reporter.add_test_result(
                "test_projects_load",
                "passed",
                time.time() - start_time,
                message=f"Loaded {len(projects)} projects",
            )
        except Exception as e:
            self.reporter.add_test_result(
                "test_projects_load",
                "failed",
                time.time() - start_time,
                error=str(e),
            )

        # Load test files
        start_time = time.time()
        try:
            total_files = 0
            for project in projects:
                project_path = Path(project["root_path"])
                file_count = self.data_setup.load_test_files(
                    db, project["project_id"], project_path
                )
                total_files += file_count

            self.reporter.add_test_result(
                "test_files_load",
                "passed",
                time.time() - start_time,
                message=f"Loaded {total_files} files",
            )
        except Exception as e:
            self.reporter.add_test_result(
                "test_files_load",
                "failed",
                time.time() - start_time,
                error=str(e),
            )

        self.reporter.end_suite()

    def _test_server_startup(self) -> None:
        """Test server startup."""
        self.reporter.start_suite("Server Startup")

        start_time = time.time()
        if self.server_manager.start_server():
            self.reporter.add_test_result(
                "server_start",
                "passed",
                time.time() - start_time,
                message="Server started successfully",
            )
        else:
            self.reporter.add_test_result(
                "server_start",
                "failed",
                time.time() - start_time,
                error="Failed to start server",
            )

        self.reporter.end_suite()

    def _test_database_operations(self) -> None:
        """Test database operations."""
        self.reporter.start_suite("Database Operations")

        # Placeholder for database operation tests
        # These will be implemented when new architecture is ready
        self.reporter.add_test_result(
            "database_operations",
            "skipped",
            0.0,
            message="Database operations tests - pending new architecture",
        )

        self.reporter.end_suite()

    def _test_ast_cst_operations(self) -> None:
        """Test AST/CST operations."""
        self.reporter.start_suite("AST/CST Operations")

        # Placeholder for AST/CST operation tests
        self.reporter.add_test_result(
            "ast_cst_operations",
            "skipped",
            0.0,
            message="AST/CST operations tests - pending new architecture",
        )

        self.reporter.end_suite()

    def _test_commands(self) -> None:
        """Test MCP commands."""
        self.reporter.start_suite("Commands")

        # Placeholder for command tests
        self.reporter.add_test_result(
            "commands",
            "skipped",
            0.0,
            message="Command tests - pending new architecture",
        )

        self.reporter.end_suite()

    def _test_workers(self) -> None:
        """Test workers."""
        self.reporter.start_suite("Workers")

        # Placeholder for worker tests
        self.reporter.add_test_result(
            "workers",
            "skipped",
            0.0,
            message="Worker tests - pending new architecture",
        )

        self.reporter.end_suite()

    def _test_performance(self) -> None:
        """Test performance."""
        self.reporter.start_suite("Performance")

        # Placeholder for performance tests
        self.reporter.add_test_result(
            "performance",
            "skipped",
            0.0,
            message="Performance tests - pending new architecture",
        )

        self.reporter.end_suite()

    def _test_error_scenarios(self) -> None:
        """Test error scenarios."""
        self.reporter.start_suite("Error Scenarios")

        # Placeholder for error scenario tests
        self.reporter.add_test_result(
            "error_scenarios",
            "skipped",
            0.0,
            message="Error scenario tests - pending new architecture",
        )

        self.reporter.end_suite()

    def _test_concurrent_operations(self) -> None:
        """Test concurrent operations."""
        self.reporter.start_suite("Concurrent Operations")

        # Placeholder for concurrent operation tests
        self.reporter.add_test_result(
            "concurrent_operations",
            "skipped",
            0.0,
            message="Concurrent operation tests - pending new architecture",
        )

        self.reporter.end_suite()

    def _test_end_to_end_workflows(self) -> None:
        """Test end-to-end workflows."""
        self.reporter.start_suite("End-to-End Workflows")

        # Placeholder for end-to-end workflow tests
        self.reporter.add_test_result(
            "end_to_end_workflows",
            "skipped",
            0.0,
            message="End-to-end workflow tests - pending new architecture",
        )

        self.reporter.end_suite()

    def _stop_server(self) -> None:
        """Stop test server."""
        self.server_manager.stop_server()
        self.data_setup.cleanup_test_database()


def test_pipeline():
    """Pytest test function for pipeline."""
    pipeline = TestPipeline()
    pipeline.run_pipeline()


if __name__ == "__main__":
    pipeline = TestPipeline()
    pipeline.run_pipeline()
