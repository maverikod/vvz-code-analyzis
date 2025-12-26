"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base initialization for Level B visualization.
"""

import matplotlib.pyplot as plt


class LevelBVisualizerBase:
    """
    Base class for Level B visualization initialization.

    Physical Meaning:
        Provides base initialization for visualization tools
        with matplotlib style and colors.
    """

    def __init__(self, style: str = "seaborn-v0_8"):
        """
        Initialize Level B visualizer.

        Args:
            style (str): Matplotlib style for plots
        """
        plt.style.use(style)
        self.colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]

