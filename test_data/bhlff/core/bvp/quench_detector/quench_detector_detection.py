"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Main detection methods for quench detector.

This module provides main detection methods as a mixin class.
"""

import numpy as np
from typing import Dict, Any, List
import time
import gc

try:
    import cupy as cp
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None


class QuenchDetectorDetectionMixin:
    """Mixin providing main detection methods."""
    
    def _detect_quenches_blocked(self, envelope: np.ndarray) -> Dict[str, Any]:
        """Detect quenches using vectorized overlapped block processing (CPU/GPU)."""
        all_quenches: List[Dict[str, Any]] = []
        blocks = self._iter_block_slices(envelope.shape)
        total_blocks = len(blocks)
        self.logger.info(f"Total blocks: {total_blocks} for shape {envelope.shape}")
        
        start_time = time.time()
        
        def _gpu_mem_info() -> str:
            if self.cuda_available:
                try:
                    free_b, total_b = cp.cuda.runtime.memGetInfo()
                    used_b = total_b - free_b
                    return f"GPU mem used {used_b/1e9:.2f}GB / {total_b/1e9:.2f}GB"
                except Exception:
                    return "GPU mem n/a"
            return "CPU mode"
        
        # Process blocks in batches
        processed_blocks = 0
        for i in range(0, total_blocks, max(1, self.batch_size)):
            batch = blocks[i : i + self.batch_size]
            for blk_idx, blk in enumerate(batch):
                block_view = envelope[blk]
                blk_global_index = i + blk_idx + 1
                self.logger.info(
                    f"Start block {blk_global_index}/{total_blocks} slices={blk}"
                )
                blk_t0 = time.time()
                try:
                    if self.cuda_available:
                        # GPU path per block (single transfer)
                        block_gpu = cp.asarray(block_view)
                        amp_q = self._detect_amplitude_quenches_cuda(block_gpu)
                        self.logger.info(
                            f"  block {blk_global_index}: amplitude done (n={len(amp_q)}) | {_gpu_mem_info()}"
                        )
                        det_q = self._detect_detuning_quenches_cuda(block_gpu)
                        self.logger.info(
                            f"  block {blk_global_index}: detuning done (n={len(det_q)}) | {_gpu_mem_info()}"
                        )
                        grad_q = self._detect_gradient_quenches_cuda(block_gpu)
                        self.logger.info(
                            f"  block {blk_global_index}: gradient done (n={len(grad_q)}) | {_gpu_mem_info()}"
                        )
                        del block_gpu
                        cp.get_default_memory_pool().free_all_blocks()
                    else:
                        amp_q = self._detect_amplitude_quenches(block_view)
                        self.logger.info(
                            f"  block {blk_global_index}: amplitude done (n={len(amp_q)})"
                        )
                        det_q = self._detect_detuning_quenches(block_view)
                        self.logger.info(
                            f"  block {blk_global_index}: detuning done (n={len(det_q)})"
                        )
                        grad_q = self._detect_gradient_quenches(block_view)
                        self.logger.info(
                            f"  block {blk_global_index}: gradient done (n={len(grad_q)})"
                        )
                except Exception as e:
                    # Fallback to CPU for this block
                    self.logger.warning(
                        f"Block {i+blk_idx}: CUDA path failed ({e}); falling back to CPU"
                    )
                    amp_q = self._detect_amplitude_quenches(block_view)
                    det_q = self._detect_detuning_quenches(block_view)
                    grad_q = self._detect_gradient_quenches(block_view)
                
                # Offset block-local centers to global coordinates
                def _offset_events(
                    events: List[Dict[str, Any]],
                ) -> List[Dict[str, Any]]:
                    start_indices = [sl.start or 0 for sl in blk]
                    adjusted: List[Dict[str, Any]] = []
                    for ev in events:
                        loc = ev.get("location")
                        if loc is not None and len(loc) == len(start_indices):
                            loc = tuple(
                                float(loc[d]) + float(start_indices[d])
                                for d in range(len(start_indices))
                            )
                        ev2 = dict(ev)
                        ev2["location"] = loc
                        adjusted.append(ev2)
                    return adjusted
                
                all_quenches.extend(_offset_events(amp_q))
                all_quenches.extend(_offset_events(det_q))
                all_quenches.extend(_offset_events(grad_q))
                
                processed_blocks += 1
                blk_dt = time.time() - blk_t0
                self.logger.info(
                    f"End block {blk_global_index}: took {blk_dt:.2f}s, total events={len(amp_q)+len(det_q)+len(grad_q)}"
                )
                if (
                    processed_blocks % max(1, self.progress_interval) == 0
                    or processed_blocks == total_blocks
                ):
                    elapsed = time.time() - start_time
                    rate = processed_blocks / max(1e-6, elapsed)
                    eta = (total_blocks - processed_blocks) / max(1e-6, rate)
                    self.logger.info(
                        f"Progress: {processed_blocks}/{total_blocks} blocks | {rate:.2f} blk/s | ETA {eta:.1f}s | {_gpu_mem_info()}"
                    )
        
        quench_locations = [q.get("location") for q in all_quenches]
        quench_types = [q.get("type") for q in all_quenches]
        quench_strengths = [q.get("strength", 0.0) for q in all_quenches]
        
        return {
            "quenches_detected": len(all_quenches) > 0,
            "quench_locations": quench_locations,
            "quench_types": quench_types,
            "quench_strengths": quench_strengths,
            "amplitude_quenches": [
                q["location"] for q in all_quenches if q.get("type") == "amplitude"
            ],
            "detuning_quenches": [
                q["location"] for q in all_quenches if q.get("type") == "detuning"
            ],
            "gradient_quenches": [
                q["location"] for q in all_quenches if q.get("type") == "gradient"
            ],
            "total_quenches": len(all_quenches),
            "detection_method": (
                "blocked_cuda_7d" if self.cuda_available else "blocked_cpu_7d"
            ),
        }
    
    def _detect_quenches_cuda(self, envelope: np.ndarray) -> Dict[str, Any]:
        """Detect quenches using CUDA acceleration."""
        try:
            # Transfer envelope to GPU
            envelope_gpu = cp.asarray(envelope)
            
            # Detect different types of quenches on GPU
            amplitude_quenches = self._detect_amplitude_quenches_cuda(envelope_gpu)
            detuning_quenches = self._detect_detuning_quenches_cuda(envelope_gpu)
            gradient_quenches = self._detect_gradient_quenches_cuda(envelope_gpu)
            
            # Cleanup GPU memory
            del envelope_gpu
            cp.get_default_memory_pool().free_all_blocks()
            
            # Force garbage collection
            gc.collect()
            
            # Combine results
            all_quenches = amplitude_quenches + detuning_quenches + gradient_quenches
            quench_locations = [q["location"] for q in all_quenches]
            quench_types = [q["type"] for q in all_quenches]
            quench_strengths = [q["strength"] for q in all_quenches]
            
            return {
                "quenches_detected": len(all_quenches) > 0,
                "quench_locations": quench_locations,
                "quench_types": quench_types,
                "quench_strengths": quench_strengths,
                "amplitude_quenches": [q["location"] for q in amplitude_quenches],
                "detuning_quenches": [q["location"] for q in detuning_quenches],
                "gradient_quenches": [q["location"] for q in gradient_quenches],
                "total_quenches": len(all_quenches),
                "detection_method": "cuda_7d_bvp",
            }
            
        except Exception as e:
            self.logger.warning(
                f"CUDA quench detection failed: {e}, falling back to CPU"
            )
            import traceback
            
            self.logger.warning(f"CUDA error traceback: {traceback.format_exc()}")
            return self._detect_quenches_cpu(envelope)
    
    def _detect_quenches_cpu(self, envelope: np.ndarray) -> Dict[str, Any]:
        """Detect quenches using CPU processing."""
        # Detect different types of quenches
        amplitude_quenches = self._detect_amplitude_quenches(envelope)
        detuning_quenches = self._detect_detuning_quenches(envelope)
        gradient_quenches = self._detect_gradient_quenches(envelope)
        
        # Combine all quenches
        all_quenches = amplitude_quenches + detuning_quenches + gradient_quenches
        quench_locations = [q["location"] for q in all_quenches]
        quench_types = [q["type"] for q in all_quenches]
        quench_strengths = [q["strength"] for q in all_quenches]
        
        return {
            "quenches_detected": len(all_quenches) > 0,
            "quench_locations": quench_locations,
            "quench_types": quench_types,
            "quench_strengths": quench_strengths,
            "amplitude_quenches": [q["location"] for q in amplitude_quenches],
            "detuning_quenches": [q["location"] for q in detuning_quenches],
            "gradient_quenches": [q["location"] for q in gradient_quenches],
            "total_quenches": len(all_quenches),
        }

