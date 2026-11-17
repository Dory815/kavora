# Celestial-disk transmittance fast path

This branch adds a conservative fast path to `airTransmittanceToLight`.
For small celestial emitters (`angularRadius <= 0.01 rad)), sufficiently elevated
light directions (`cosine >= 0.3`), and a disk wholly above the local horizon,
the four-node Gauss-Legendre disk integral is replaced by one central LUT
transmittance lookup. The original finite-disk quadrature remains active near
the horizon, for partially occulted disks, and for larger emitters.

The change does not replace path tracing, cloud transport, air extinction,
phase functions, or the finite-disk treatment where angular variation is
important. It only approximates the smooth angular average of the air
transmittance LUT in the bounded regime.

## CPU validation

Run:

```sh
python3 -m unittest kavora-runtime/tests/rtx/unit/test_air_disk_approximation.py -v
```

The test compares the candidate central-ray value against the existing
four-point disk quadrature. The LUT is replaced by an independently integrated
spherical atmosphere with Rayleigh and Mie exponential density profiles. It
covers six altitudes (0–40 km), 81 light cosines, and solar/lunar angular-radius
fixtures (0.00465 and 0.009 rad). It also asserts that horizon-adjacent,
partially visible, and larger-emitter cases do not enter the fast path.

The measured maximum error in the 972 fast-path cases is:

- Maximum absolute transmittance error: `3.762353e-05`
- Maximum relative transmittance error: `4.585272e-04` (0.0459%)

The numerical test is a model-based CPU bound, not a GPU shader execution or
full Minecraft image acceptance test. A CPU-rendered transmittance A/B preview
is generated separately for visual inspection. Native Slang compilation,
Vulkan readback, RTX frame timing, and full path-traced cloud/fog captures
remain required before claiming production acceptance.

## Expected work reduction

For every eligible active light sample, the transmittance texture lookups
inside the disk integral drop from four to one (75% fewer lookups for that
subroutine). The number of affected samples depends on sun elevation, emitter
configuration, and the actual distribution of air integration samples. This
does not imply a 75% reduction in total atmosphere cost or frame time.
