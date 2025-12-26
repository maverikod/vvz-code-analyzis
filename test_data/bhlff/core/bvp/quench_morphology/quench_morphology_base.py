"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base initialization for quench morphology operations.
"""

try:
    from scipy.ndimage import binary_opening, binary_closing, label

    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None


class QuenchMorphologyBase:
    """
    Base class for quench morphology operations initialization.

    Physical Meaning:
        Provides base initialization for morphological operations
        used in quench detection, setting up dependencies and
        availability checks.
    """

    def __init__(self):
        """Initialize morphological operations processor."""
        self.scipy_available = SCIPY_AVAILABLE
        self.cuda_available = CUDA_AVAILABLE

