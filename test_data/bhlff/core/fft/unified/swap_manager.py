"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Transparent swap manager for large 7D arrays with pickle-based serialization.

This module provides transparent swap functionality for large 7D phase field
arrays, automatically managing memory-mapped files and pickle-based serialization
for fast save/load operations.

Physical Meaning:
    Provides transparent memory management for large 7D phase field arrays
    that exceed available RAM, using disk-based swap with efficient serialization
    to maintain computational performance.

Mathematical Foundation:
    Manages swap files for 7D arrays in space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ,
    ensuring transparent access while maintaining 7D structure and properties.
"""

import numpy as np
import pickle
import tempfile
from pathlib import Path
from typing import Optional, Union, Tuple
import logging

logger = logging.getLogger(__name__)


class SwapManager:
    """
    Transparent swap manager for large 7D arrays.
    
    Physical Meaning:
        Manages disk-based swap for large 7D phase field arrays, providing
        transparent access while automatically handling memory-mapped files
        and pickle-based serialization for fast operations.
        
    Attributes:
        swap_dir (Path): Directory for swap files.
        _swap_files (dict): Dictionary mapping array IDs to swap file paths.
    """
    
    def __init__(self, swap_dir: Optional[Union[str, Path]] = None):
        """
        Initialize swap manager.
        
        Physical Meaning:
            Sets up the swap manager with a directory for swap files,
            creating it if necessary.
            
        Args:
            swap_dir (Optional[Union[str, Path]]): Directory for swap files.
                If None, uses project root / output / swap.
        """
        if swap_dir is None:
            # Get project root (assuming we're in bhlff/core/fft/unified/)
            # Go up: bhlff/core/fft/unified/ -> bhlff/core/fft/ -> bhlff/core/ -> bhlff/ -> project root
            project_root = Path(__file__).parent.parent.parent.parent.parent
            swap_dir = project_root / "output" / "swap"
        
        self.swap_dir = Path(swap_dir)
        self.swap_dir.mkdir(parents=True, exist_ok=True)
        self._swap_files = {}
        logger.info(f"SwapManager initialized with directory: {self.swap_dir}")
    
    def create_swap_array(
        self,
        shape: Tuple[int, ...],
        dtype: np.dtype = np.complex128,
        array_id: Optional[str] = None,
    ) -> np.memmap:
        """
        Create a memory-mapped swap array.
        
        Physical Meaning:
            Creates a memory-mapped array for transparent swap operations,
            allowing large 7D arrays to be stored on disk while maintaining
            transparent access.
            
        Args:
            shape (Tuple[int, ...]): Array shape.
            dtype (np.dtype): Array data type.
            array_id (Optional[str]): Optional array identifier for tracking.
            
        Returns:
            np.memmap: Memory-mapped array for swap.
        """
        import uuid
        
        if array_id is None:
            array_id = uuid.uuid4().hex
        
        swap_file = self.swap_dir / f"swap_{array_id}.dat"
        
        # Create memory-mapped array
        arr = np.memmap(
            str(swap_file),
            dtype=dtype,
            mode='w+',
            shape=shape
        )
        
        self._swap_files[array_id] = swap_file
        logger.debug(f"Created swap array: {array_id}, shape={shape}, file={swap_file.name}")
        
        return arr
    
    def save_to_pickle(
        self,
        array: np.ndarray,
        array_id: Optional[str] = None,
    ) -> Path:
        """
        Save array to pickle file for fast loading.
        
        Physical Meaning:
            Saves array to pickle file for fast serialization/deserialization,
            useful for checkpointing and fast save/load operations.
            
        Args:
            array (np.ndarray): Array to save.
            array_id (Optional[str]): Optional array identifier.
            
        Returns:
            Path: Path to saved pickle file.
        """
        import uuid
        
        if array_id is None:
            array_id = uuid.uuid4().hex
        
        pickle_file = self.swap_dir / f"pickle_{array_id}.pkl"
        
        # Save to pickle
        with open(pickle_file, 'wb') as f:
            pickle.dump(array, f, protocol=pickle.HIGHEST_PROTOCOL)
        
        logger.debug(f"Saved array to pickle: {array_id}, shape={array.shape}, file={pickle_file.name}")
        
        return pickle_file
    
    def load_from_pickle(
        self,
        pickle_file: Union[str, Path],
    ) -> np.ndarray:
        """
        Load array from pickle file.
        
        Physical Meaning:
            Loads array from pickle file for fast deserialization,
            restoring array state from checkpoint.
            
        Args:
            pickle_file (Union[str, Path]): Path to pickle file.
            
        Returns:
            np.ndarray: Loaded array.
        """
        pickle_path = Path(pickle_file)
        
        with open(pickle_path, 'rb') as f:
            array = pickle.load(f)
        
        logger.debug(f"Loaded array from pickle: {pickle_path.name}, shape={array.shape}")
        
        return array
    
    def cleanup(self, array_id: Optional[str] = None) -> None:
        """
        Clean up swap files.
        
        Physical Meaning:
            Removes swap files to free disk space, either for a specific
            array or all arrays.
            
        Args:
            array_id (Optional[str]): Array identifier to clean up.
                If None, cleans up all swap files.
        """
        if array_id is None:
            # Clean up all swap files
            for swap_file in self.swap_dir.glob("swap_*.dat"):
                try:
                    swap_file.unlink()
                    logger.debug(f"Cleaned up swap file: {swap_file.name}")
                except Exception as e:
                    logger.warning(f"Failed to clean up {swap_file.name}: {e}")
            
            for pickle_file in self.swap_dir.glob("pickle_*.pkl"):
                try:
                    pickle_file.unlink()
                    logger.debug(f"Cleaned up pickle file: {pickle_file.name}")
                except Exception as e:
                    logger.warning(f"Failed to clean up {pickle_file.name}: {e}")
            
            self._swap_files.clear()
        else:
            # Clean up specific array
            if array_id in self._swap_files:
                swap_file = self._swap_files[array_id]
                try:
                    if swap_file.exists():
                        swap_file.unlink()
                    del self._swap_files[array_id]
                    logger.debug(f"Cleaned up swap file for {array_id}")
                except Exception as e:
                    logger.warning(f"Failed to clean up {array_id}: {e}")


# Global swap manager instance
_global_swap_manager: Optional[SwapManager] = None


def get_swap_manager() -> SwapManager:
    """
    Get global swap manager instance.
    
    Physical Meaning:
        Returns the global swap manager instance for transparent swap
        operations throughout the framework.
        
    Returns:
        SwapManager: Global swap manager instance.
    """
    global _global_swap_manager
    if _global_swap_manager is None:
        _global_swap_manager = SwapManager()
    return _global_swap_manager

