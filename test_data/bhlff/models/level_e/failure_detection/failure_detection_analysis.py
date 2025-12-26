"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Analysis mixin for failure detector.

This module provides analysis methods for orchestrating failure detection
workflows and summarizing overall failure assessments.
"""

from typing import Any, Dict


class FailureDetectorAnalysisMixin:
    """Mixin providing analysis workflow methods."""
    
    def detect_failures(self) -> Dict[str, Any]:
        """
        Detect all types of failures in the system.
        
        Physical Meaning:
            Comprehensive analysis of system failures including
            passivity violations, singular modes, energy conservation
            violations, and numerical instabilities.
        
        Returns:
            Dictionary containing all detected failures
        """
        failures: Dict[str, Any] = {}
        
        for failure_type, check_function in self.failure_criteria.items():
            try:
                result = check_function()
                failures[failure_type] = result
                
                if result["detected"]:
                    self.logger.warning(f"Failure detected: {failure_type}")
                else:
                    self.logger.info(f"No failure detected: {failure_type}")
            except Exception as exc:
                self.logger.error(f"Error checking {failure_type}: {exc}")
                failures[failure_type] = {
                    "detected": True,
                    "error": str(exc),
                    "type": "check_error",
                }
        
        # Overall failure assessment
        overall_assessment = self._assess_overall_failures(failures)
        failures["overall_assessment"] = overall_assessment
        
        return failures
    
    def _assess_overall_failures(self, failures: Dict[str, Any]) -> Dict[str, Any]:
        """Assess overall failure status."""
        detected_failures = [
            name
            for name, result in failures.items()
            if isinstance(result, dict) and result.get("detected", False)
        ]
        
        failure_count = len(detected_failures)
        
        if failure_count == 0:
            status = "healthy"
            severity = "none"
        elif failure_count == 1:
            status = "warning"
            severity = "low"
        elif failure_count <= 3:
            status = "critical"
            severity = "medium"
        else:
            status = "failed"
            severity = "high"
        
        return {
            "status": status,
            "severity": severity,
            "failure_count": failure_count,
            "detected_failures": detected_failures,
        }
