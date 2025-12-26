"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Spectral coefficients setup methods for FFT solver 7D basic.

This module provides spectral coefficients setup methods as a mixin class.
"""

import numpy as np
import logging
import sys

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

logger = logging.getLogger(__name__)


class FFTSolver7DBasicCoefficientsMixin:
    """Mixin providing spectral coefficients setup methods."""
    
    def _setup_spectral_coefficients(self) -> None:
        """
        Setup spectral coefficients with memory checking.
        
        Physical Meaning:
            Determines whether to use pre-computed coefficients or lazy evaluation
            based on available memory, ensuring efficient memory usage for large 7D fields.
        """
        logger.info(f"[SOLVER SETUP] STEP 1: _setup_spectral_coefficients: START")
        sys.stdout.flush()
        sys.stderr.flush()
        
        # Check memory requirements
        logger.info(f"[SOLVER SETUP] STEP 2: Getting domain shape...")
        sys.stdout.flush()
        sys.stderr.flush()
        domain_shape = getattr(self.domain, "shape", None)
        if domain_shape is None:
            raise AttributeError("Domain must have shape attribute")
        logger.info(f"[SOLVER SETUP] STEP 2 COMPLETE: domain_shape={domain_shape}")
        sys.stdout.flush()
        sys.stderr.flush()
        
        # Estimate memory for full coefficient array (float64 = 8 bytes)
        logger.info(f"[SOLVER SETUP] STEP 3: Calculating coefficient memory...")
        sys.stdout.flush()
        sys.stderr.flush()
        coeff_memory_bytes = np.prod(domain_shape) * 8
        logger.info(
            f"[SOLVER SETUP] STEP 3 COMPLETE: Coefficient array would require {coeff_memory_bytes/1e9:.2f}GB"
        )
        sys.stdout.flush()
        sys.stderr.flush()
        
        # Check if we should use lazy evaluation
        logger.info(f"[SOLVER SETUP] STEP 4: Checking PSUTIL availability...")
        sys.stdout.flush()
        sys.stderr.flush()
        use_lazy = False
        if PSUTIL_AVAILABLE:
            logger.info(f"[SOLVER SETUP] STEP 4: PSUTIL available, getting memory info...")
            sys.stdout.flush()
            sys.stderr.flush()
            available_memory = psutil.virtual_memory().available
            logger.info(
                f"[SOLVER SETUP] STEP 4 COMPLETE: Available memory: {available_memory/1e9:.2f}GB"
            )
            sys.stdout.flush()
            sys.stderr.flush()
            # Use lazy evaluation if coefficient array would exceed 20% of available memory
            logger.info(f"[SOLVER SETUP] STEP 5: Comparing memory requirements...")
            sys.stdout.flush()
            sys.stderr.flush()
            if coeff_memory_bytes > 0.2 * available_memory:
                use_lazy = True
                logger.info(
                    f"[SOLVER SETUP] STEP 5 COMPLETE: Using lazy spectral coefficient evaluation: "
                    f"coefficient array would require {coeff_memory_bytes/1e9:.2f}GB, "
                    f"available memory {available_memory/1e9:.2f}GB"
                )
            else:
                logger.info(f"[SOLVER SETUP] STEP 5 COMPLETE: Using full coefficient array (fits in memory)")
            sys.stdout.flush()
            sys.stderr.flush()
        else:
            logger.info(f"[SOLVER SETUP] STEP 4: PSUTIL not available, using conservative estimate...")
            sys.stdout.flush()
            sys.stderr.flush()
            # Conservative estimate: use lazy for arrays > 1GB
            if coeff_memory_bytes > 1e9:
                use_lazy = True
                logger.info(
                    f"[SOLVER SETUP] STEP 4 COMPLETE: Using lazy spectral coefficient evaluation: "
                    f"coefficient array would require {coeff_memory_bytes/1e9:.2f}GB"
                )
            else:
                logger.info(f"[SOLVER SETUP] STEP 4 COMPLETE: Using full coefficient array (fits in memory)")
            sys.stdout.flush()
            sys.stderr.flush()
        
        logger.info(f"[SOLVER SETUP] STEP 6: Setting use_lazy={use_lazy}...")
        sys.stdout.flush()
        sys.stderr.flush()
        self._use_lazy_coeffs = use_lazy
        logger.info(f"[SOLVER SETUP] STEP 6 COMPLETE: use_lazy set")
        sys.stdout.flush()
        sys.stderr.flush()
        
        if use_lazy:
            # Setup lazy coefficient function
            logger.info(f"[SOLVER SETUP] STEP 7: Setting up lazy coefficient function...")
            sys.stdout.flush()
            sys.stderr.flush()
            self._setup_lazy_coefficient_function()
            logger.info(f"[SOLVER SETUP] STEP 7 COMPLETE: Lazy coefficient function setup complete")
            sys.stdout.flush()
            sys.stderr.flush()
        else:
            # Build full coefficient array
            logger.info(f"[SOLVER SETUP] STEP 7: Building full coefficient array...")
            sys.stdout.flush()
            sys.stderr.flush()
            self._build_spectral_coefficients()
            logger.info(f"[SOLVER SETUP] STEP 7 COMPLETE: Full coefficient array built")
            sys.stdout.flush()
            sys.stderr.flush()
        
        logger.info(f"[SOLVER SETUP] STEP 8: _setup_spectral_coefficients: COMPLETE")
        sys.stdout.flush()
        sys.stderr.flush()
    
    def _setup_lazy_coefficient_function(self) -> None:
        """
        Setup lazy coefficient computation function.
        
        Physical Meaning:
            Creates a function that computes spectral coefficients on-the-fly
            without storing the full 7D array, enabling memory-efficient processing.
        """
        logger.info(f"[SOLVER SETUP LAZY] STEP 1: _setup_lazy_coefficient_function: START")
        sys.stdout.flush()
        sys.stderr.flush()
        
        # Support both classic Domain (N, N_phi, N_t) and Domain7DBVP (N_spatial, N_phase, N_t)
        logger.info(f"[SOLVER SETUP LAZY] STEP 2: Getting domain parameters...")
        sys.stdout.flush()
        sys.stderr.flush()
        N = getattr(self.domain, "N", getattr(self.domain, "N_spatial", None))
        Np = getattr(self.domain, "N_phi", getattr(self.domain, "N_phase", None))
        Nt = getattr(self.domain, "N_t", None)
        if N is None or Np is None or Nt is None:
            raise AttributeError(
                "Domain must define (N or N_spatial), (N_phi or N_phase), and N_t"
            )
        logger.info(f"[SOLVER SETUP LAZY] STEP 2 COMPLETE: N={N}, Np={Np}, Nt={Nt}")
        sys.stdout.flush()
        sys.stderr.flush()
        
        # Physical wave numbers with proper spacing (cycles per unit)
        logger.info(f"[SOLVER SETUP LAZY] STEP 3: Getting spacing parameters...")
        sys.stdout.flush()
        sys.stderr.flush()
        dx = getattr(self.domain, "dx", 1.0)
        dphi = getattr(self.domain, "dphi", (2 * np.pi) / Np)
        dt = getattr(self.domain, "dt", 1.0)
        logger.info(f"[SOLVER SETUP LAZY] STEP 3 COMPLETE: dx={dx}, dphi={dphi}, dt={dt}")
        sys.stdout.flush()
        sys.stderr.flush()

        logger.info(f"[SOLVER SETUP LAZY] STEP 4: Computing fftfreq arrays...")
        sys.stdout.flush()
        sys.stderr.flush()
        # CRITICAL: fftfreq returns frequencies (cycles per unit), need to multiply by 2π to get wave numbers (radians per unit)
        # Wave number k = 2π * frequency
        kx = 2 * np.pi * np.fft.fftfreq(N, d=dx)
        logger.info(f"[SOLVER SETUP LAZY] STEP 4.1: kx computed, shape={kx.shape}")
        sys.stdout.flush()
        sys.stderr.flush()
        ky = 2 * np.pi * np.fft.fftfreq(N, d=dx)
        logger.info(f"[SOLVER SETUP LAZY] STEP 4.2: ky computed, shape={ky.shape}")
        sys.stdout.flush()
        sys.stderr.flush()
        kz = 2 * np.pi * np.fft.fftfreq(N, d=dx)
        logger.info(f"[SOLVER SETUP LAZY] STEP 4.3: kz computed, shape={kz.shape}")
        sys.stdout.flush()
        sys.stderr.flush()
        p = 2 * np.pi * np.fft.fftfreq(Np, d=dphi)
        logger.info(f"[SOLVER SETUP LAZY] STEP 4.4: p computed, shape={p.shape}")
        sys.stdout.flush()
        sys.stderr.flush()
        kt = 2 * np.pi * np.fft.fftfreq(Nt, d=dt)
        logger.info(f"[SOLVER SETUP LAZY] STEP 4.5: kt computed, shape={kt.shape}")
        sys.stdout.flush()
        sys.stderr.flush()
        logger.info(f"[SOLVER SETUP LAZY] STEP 4 COMPLETE: All fftfreq arrays computed")
        sys.stdout.flush()
        sys.stderr.flush()
        
        # Store wave number arrays for lazy computation
        logger.info(f"[SOLVER SETUP LAZY] STEP 5: Storing wave number arrays...")
        sys.stdout.flush()
        sys.stderr.flush()
        self._k_arrays = (kx, ky, kz, p, p, p, kt)  # type: ignore
        self._mu = self.mu
        self._beta = self.beta
        self._lambda = self.lmbda
        logger.info(f"[SOLVER SETUP LAZY] STEP 5 COMPLETE: Arrays stored, _setup_lazy_coefficient_function: COMPLETE")
        sys.stdout.flush()
        sys.stderr.flush()
    
    def _build_spectral_coefficients(self) -> None:
        """
        Build full spectral coefficient array (for small fields).
        
        Physical Meaning:
            Pre-computes spectral coefficients for efficient repeated use,
            only used when memory allows storing the full 7D array.
        """
        logger.info(f"[SOLVER SETUP BUILD] STEP 1: _build_spectral_coefficients: START")
        sys.stdout.flush()
        sys.stderr.flush()
        
        # Build coefficients on CPU (numpy) to avoid GPU OOM; ops layer handles device
        xp = np
        # Support both classic Domain (N, N_phi, N_t) and Domain7DBVP (N_spatial, N_phase, N_t)
        logger.info(f"[SOLVER SETUP BUILD] STEP 2: Getting domain parameters...")
        sys.stdout.flush()
        sys.stderr.flush()
        N = getattr(self.domain, "N", getattr(self.domain, "N_spatial", None))
        Np = getattr(self.domain, "N_phi", getattr(self.domain, "N_phase", None))
        Nt = getattr(self.domain, "N_t", None)
        if N is None or Np is None or Nt is None:
            raise AttributeError(
                "Domain must define (N or N_spatial), (N_phi or N_phase), and N_t"
            )
        logger.info(f"[SOLVER SETUP BUILD] STEP 2 COMPLETE: N={N}, Np={Np}, Nt={Nt}")
        sys.stdout.flush()
        sys.stderr.flush()
        
        # Physical wave numbers with proper spacing (cycles per unit)
        logger.info(f"[SOLVER SETUP BUILD] STEP 3: Getting spacing parameters...")
        sys.stdout.flush()
        sys.stderr.flush()
        dx = getattr(self.domain, "dx", 1.0)
        dphi = getattr(self.domain, "dphi", (2 * xp.pi) / Np)
        dt = getattr(self.domain, "dt", 1.0)
        logger.info(f"[SOLVER SETUP BUILD] STEP 3 COMPLETE: dx={dx}, dphi={dphi}, dt={dt}")
        sys.stdout.flush()
        sys.stderr.flush()

        logger.info(f"[SOLVER SETUP BUILD] STEP 4: Computing fftfreq arrays...")
        sys.stdout.flush()
        sys.stderr.flush()
        # CRITICAL: fftfreq returns frequencies (cycles per unit), need to multiply by 2π to get wave numbers (radians per unit)
        # Wave number k = 2π * frequency
        kx = 2 * xp.pi * xp.fft.fftfreq(N, d=dx)
        ky = 2 * xp.pi * xp.fft.fftfreq(N, d=dx)
        kz = 2 * xp.pi * xp.fft.fftfreq(N, d=dx)
        p = 2 * xp.pi * xp.fft.fftfreq(Np, d=dphi)
        kt = 2 * xp.pi * xp.fft.fftfreq(Nt, d=dt)
        logger.info(f"[SOLVER SETUP BUILD] STEP 4 COMPLETE: All fftfreq arrays computed")
        sys.stdout.flush()
        sys.stderr.flush()

        logger.info(f"[SOLVER SETUP BUILD] STEP 5: Creating meshgrids via broadcasting...")
        sys.stdout.flush()
        sys.stderr.flush()
        KX7 = kx[:, None, None, None, None, None, None]
        KY7 = ky[None, :, None, None, None, None, None]
        KZ7 = kz[None, None, :, None, None, None, None]
        P17 = p[None, None, None, :, None, None, None]
        P27 = p[None, None, None, None, :, None, None]
        P37 = p[None, None, None, None, None, :, None]
        KT7 = kt[None, None, None, None, None, None, :]
        logger.info(f"[SOLVER SETUP BUILD] STEP 5 COMPLETE: Meshgrids created")
        sys.stdout.flush()
        sys.stderr.flush()

        logger.info(f"[SOLVER SETUP BUILD] STEP 6: Computing k^2...")
        sys.stdout.flush()
        sys.stderr.flush()
        k2 = (
            KX7 * KX7
            + KY7 * KY7
            + KZ7 * KZ7
            + P17 * P17
            + P27 * P27
            + P37 * P37
            + KT7 * KT7
        )
        logger.info(f"[SOLVER SETUP BUILD] STEP 6 COMPLETE: k^2 computed, shape={k2.shape}")
        sys.stdout.flush()
        sys.stderr.flush()
        
        logger.info(f"[SOLVER SETUP BUILD] STEP 7: Computing abs_k_2beta...")
        sys.stdout.flush()
        sys.stderr.flush()
        abs_k_2beta = xp.power(k2 + 0.0, self.beta)
        logger.info(f"[SOLVER SETUP BUILD] STEP 7 COMPLETE: abs_k_2beta computed")
        sys.stdout.flush()
        sys.stderr.flush()
        
        logger.info(f"[SOLVER SETUP BUILD] STEP 8: Computing coefficients D...")
        sys.stdout.flush()
        sys.stderr.flush()
        D = self.mu * abs_k_2beta + self.lmbda
        if self.lmbda == 0.0:
            D[(k2 == 0)] = 1.0
        logger.info(f"[SOLVER SETUP BUILD] STEP 8 COMPLETE: D computed")
        sys.stdout.flush()
        sys.stderr.flush()
        
        logger.info(f"[SOLVER SETUP BUILD] STEP 9: Converting to float64...")
        sys.stdout.flush()
        sys.stderr.flush()
        self._coeffs = D.astype(np.float64)
        logger.info(f"[SOLVER SETUP BUILD] STEP 9 COMPLETE: _build_spectral_coefficients: COMPLETE")
        sys.stdout.flush()
        sys.stderr.flush()

