"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Dashboard creation for Level B visualization.
"""

import matplotlib.pyplot as plt
from typing import Dict, Any
from pathlib import Path


class LevelBVisualizerDashboard:
    """
    Dashboard creation for Level B visualization.

    Physical Meaning:
        Creates summary dashboard for all Level B analysis results,
        providing an overview of test results and quality metrics.
    """

    def create_summary_dashboard(
        self, results: Dict[str, Any], output_path: Path
    ) -> None:
        """Create summary dashboard for all results."""
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))

        # Plot 1: Test results overview
        test_names = list(results.keys())
        test_passed = [results[name].get("passed", False) for name in test_names]

        colors = ["green" if passed else "red" for passed in test_passed]
        ax1.bar(range(len(test_names)), test_passed, color=colors, alpha=0.7)
        ax1.set_xticks(range(len(test_names)))
        ax1.set_xticklabels(
            [name.replace("test_", "") for name in test_names], rotation=45
        )
        ax1.set_ylabel("Pass/Fail")
        ax1.set_title("Level B Test Results Overview")
        ax1.grid(True, alpha=0.3)

        # Plot 2: Power law analysis summary
        if "test_B1_power_law_tail" in results and results[
            "test_B1_power_law_tail"
        ].get("passed"):
            analysis = results["test_B1_power_law_tail"].get("analysis_result", {})
            ax2.bar(
                ["R²", "Error < 5%", "Range > 1.5"],
                [
                    analysis.get("r_squared", 0),
                    analysis.get("relative_error", 1) < 0.05,
                    analysis.get("log_range", 0) > 1.5,
                ],
                color=["blue", "green", "orange"],
                alpha=0.7,
            )
            ax2.set_ylabel("Value")
            ax2.set_title("Power Law Analysis")
            ax2.set_ylim(0, 1)

        # Plot 3: Node analysis summary
        if "test_B2_no_spherical_nodes" in results and results[
            "test_B2_no_spherical_nodes"
        ].get("passed"):
            analysis = results["test_B2_no_spherical_nodes"].get("analysis_result", {})
            ax3.bar(
                ["Sign Changes ≤ 1", "No Periodic Zeros", "Monotonic"],
                [
                    analysis.get("sign_changes", 1) <= 1,
                    not analysis.get("periodic_zeros", True),
                    analysis.get("is_monotonic", False),
                ],
                color=["red", "blue", "green"],
                alpha=0.7,
            )
            ax3.set_ylabel("Pass/Fail")
            ax3.set_title("Node Analysis")
            ax3.set_ylim(0, 1)

        # Plot 4: Overall quality assessment
        total_tests = len(results)
        passed_tests = sum(
            1 for result in results.values() if result.get("passed", False)
        )
        success_rate = passed_tests / total_tests if total_tests > 0 else 0

        ax4.pie(
            [passed_tests, total_tests - passed_tests],
            labels=["Passed", "Failed"],
            colors=["green", "red"],
            autopct="%1.1f%%",
        )
        ax4.set_title(f"Overall Success Rate: {success_rate:.1%}")

        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()

