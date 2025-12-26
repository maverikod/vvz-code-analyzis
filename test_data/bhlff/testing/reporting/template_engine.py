"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Template engine for report generation.

This module provides template-based report generation with physics-aware
templates that provide appropriate context for different audiences.

Theoretical Background:
    The template engine generates formatted reports with physics
    interpretation and technical details appropriate for different
    audiences (physicists, engineers, managers).

Example:
    >>> engine = TemplateEngine(template_dir)
    >>> report_html = engine.render_daily_report(report, "physicists")
"""

import logging
from pathlib import Path
from typing import Dict, Any

try:
    import jinja2
except ImportError:
    jinja2 = None

from .base import DailyReport, WeeklyReport, MonthlyReport


class TemplateEngine:
    """
    Template engine for report generation.

    Physical Meaning:
        Generates formatted reports with physics-aware templates
        that provide appropriate context for different audiences.
    """

    def __init__(self, template_dir: str = "templates"):
        """
        Initialize template engine.

        Physical Meaning:
            Sets up template engine with physics-aware templates
            for different report types and audiences.

        Args:
            template_dir (str): Directory containing report templates.
        """
        self.template_dir = Path(template_dir)
        if jinja2 is not None:
            self.jinja_env = jinja2.Environment(
                loader=jinja2.FileSystemLoader(self.template_dir),
                autoescape=jinja2.select_autoescape(["html", "xml"]),
            )
        else:
            self.jinja_env = None
        self.logger = logging.getLogger(__name__)

    def render_daily_report(self, report: DailyReport, role: str = "physicists") -> str:
        """
        Render daily report for specific role.

        Physical Meaning:
            Generates role-appropriate daily report with physics
            interpretation and technical details as needed.

        Args:
            report (DailyReport): Daily report data.
            role (str): Target audience role.

        Returns:
            str: Rendered report content.
        """
        if self.jinja_env is not None:
            template_name = f"daily_{role}_report.html"
            template = self.jinja_env.get_template(template_name)

            return template.render(
                report=report, physics_context=self._get_physics_context(), role=role
            )
        else:
            # Fallback to simple text rendering
            return f"Daily Report for {role}\nDate: {report.date}\nPhysics Summary: {report.physics_summary}"

    def render_weekly_report(
        self, report: WeeklyReport, role: str = "physicists"
    ) -> str:
        """Render weekly report for specific role."""
        if self.jinja_env is not None:
            template_name = f"weekly_{role}_report.html"
            template = self.jinja_env.get_template(template_name)

            return template.render(
                report=report, physics_context=self._get_physics_context(), role=role
            )
        else:
            # Fallback to simple text rendering
            return f"Weekly Report for {role}\nWeek: {report.week_start} - {report.week_end}\nPhysics Trends: {report.physics_trends}"

    def render_monthly_report(
        self, report: MonthlyReport, role: str = "physicists"
    ) -> str:
        """Render monthly report for specific role."""
        if self.jinja_env is not None:
            template_name = f"monthly_{role}_report.html"
            template = self.jinja_env.get_template(template_name)

            return template.render(
                report=report, physics_context=self._get_physics_context(), role=role
            )
        else:
            # Fallback to simple text rendering
            return f"Monthly Report for {role}\nMonth: {report.month_start} - {report.month_end}\nPhysics Validation: {report.physics_validation}"

    def _get_physics_context(self) -> Dict[str, Any]:
        """Get physics context for templates."""
        return {
            "theory_name": "7D Phase Field Theory",
            "space_time": "M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ",
            "key_principles": [
                "Energy Conservation: dE/dt = 0",
                "Virial Conditions: dE/dλ|λ=1 = 0",
                "Topological Charge: dB/dt = 0",
                "Passivity: Re Y(ω) ≥ 0",
            ],
            "mathematical_foundation": "Fractional Laplacian: (-Δ)^β",
            "physical_meaning": "Phase field dynamics in 7D space-time",
        }
